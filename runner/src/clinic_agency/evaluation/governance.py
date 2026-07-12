"""Langfuse dataset, experiment, and prompt-promotion governance boundaries."""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from langfuse import Evaluation

Score = Evaluation


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    input: dict[str, Any]
    expected: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.case_id.startswith("eval-"):
            raise ValueError("evaluation case_id must be synthetic and start with 'eval-'")
        if self.input.get("synthetic") is not True:
            raise ValueError("evaluation input must explicitly declare synthetic=true")
        forbidden = {
            "chat_id", "external_event_id", "patient_id", "phone", "telegram_id", "name"
        }

        def keys(value: Any) -> set[str]:
            if isinstance(value, dict):
                return {str(key).casefold() for key in value} | {
                    nested for item in value.values() for nested in keys(item)
                }
            if isinstance(value, (list, tuple)):
                return {nested for item in value for nested in keys(item)}
            return set()

        found = sorted(keys(self.input) & forbidden)
        if found:
            raise ValueError(f"patient identifier field forbidden: {', '.join(found)}")
        if re.search(r"(?<!\d)(?:\+?91[- ]?)?[6-9]\d{9}(?!\d)", repr((self.input, self.expected))):
            raise ValueError("phone-like value forbidden in evaluation case")


@dataclass(frozen=True)
class EvaluationReport:
    """Deprecated display-only report; never accepted by the publish gate."""

    dataset_name: str
    run_name: str
    scores: dict[str, float]


@dataclass(frozen=True)
class ExperimentProvenance:
    experiment_id: str
    completed: bool
    prompt_name: str
    prompt_version: int
    dataset_id: str
    dataset_version: str
    sample_count: int
    scores: dict[str, float]
    evaluator_versions: dict[str, str]


class LangfuseEvaluationClient(Protocol):
    def create_dataset(self, **kwargs: Any) -> Any: ...
    def create_dataset_item(self, **kwargs: Any) -> Any: ...
    def run_experiment(self, **kwargs: Any) -> Any: ...


class ExperimentProvenanceStore(Protocol):
    def get_experiment_provenance(self, experiment_id: str) -> ExperimentProvenance: ...
    def promote_prompt_version(self, **kwargs: Any) -> Any: ...


class EvaluationGovernance:
    def __init__(self, langfuse: LangfuseEvaluationClient) -> None:
        self._langfuse = langfuse

    def create_dataset(
        self,
        name: str,
        cases: Sequence[EvaluationCase],
        *,
        role: str,
        task_type: str,
    ) -> None:
        self._langfuse.create_dataset(
            name=name,
            description="Governed synthetic role evaluation dataset",
            metadata={"role": role, "task_type": task_type},
        )
        for case in cases:
            self._langfuse.create_dataset_item(
                dataset_name=name,
                input=case.input,
                expected_output=case.expected,
                metadata={"case_id": case.case_id, "role": role, "task_type": task_type},
            )

    def run_experiment(
        self,
        *,
        dataset_name: str,
        run_name: str,
        items: list[Any],
        task: Callable[..., Any],
        evaluators: list[Callable[..., Any]],
        role: str,
        task_type: str,
    ) -> Any:
        return self._langfuse.run_experiment(
            name=dataset_name,
            run_name=run_name,
            data=items,
            task=task,
            evaluators=evaluators,
            metadata={"case_id": "evaluation", "role": role, "task_type": task_type},
        )


class PromptPublishDenied(RuntimeError):
    pass


class PromptPublishGate:
    """Promote only a persisted experiment's immutable candidate prompt version."""

    REQUIRED_SCORES = frozenset({"compliance", "red_flag_recall", "tool_policy"})

    def __init__(self, store: ExperimentProvenanceStore, *, minimum_samples: int = 10) -> None:
        if minimum_samples < 1:
            raise ValueError("minimum_samples must be positive")
        self._store = store
        self._minimum_samples = minimum_samples

    def publish(
        self,
        *,
        name: str,
        prompt_version: int,
        experiment_id: str,
        label: str = "production",
    ) -> Any:
        provenance = self._store.get_experiment_provenance(experiment_id)
        if not provenance.completed:
            raise PromptPublishDenied("persisted experiment is not completed")
        if provenance.experiment_id != experiment_id:
            raise PromptPublishDenied("experiment identity mismatch")
        if (provenance.prompt_name, provenance.prompt_version) != (name, prompt_version):
            raise PromptPublishDenied("experiment is not bound to candidate prompt version")
        if not provenance.dataset_id or not provenance.dataset_version:
            raise PromptPublishDenied("immutable dataset provenance is required")
        if provenance.sample_count < self._minimum_samples:
            raise PromptPublishDenied("experiment sample count is below governed minimum")
        missing = self.REQUIRED_SCORES - provenance.evaluator_versions.keys()
        if missing or any(not provenance.evaluator_versions[m] for m in self.REQUIRED_SCORES):
            raise PromptPublishDenied("persisted evaluator identity/version is required")
        failed = sorted(
            metric
            for metric in self.REQUIRED_SCORES
            if provenance.scores.get(metric, 0.0) < 1.0
        )
        if failed:
            raise PromptPublishDenied(f"publish gate failed: {', '.join(failed)}")
        return self._store.promote_prompt_version(
            name=name,
            version=prompt_version,
            label=label,
            provenance=experiment_id,
        )
