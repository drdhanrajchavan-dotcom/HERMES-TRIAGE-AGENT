"""Langfuse dataset, experiment, and prompt-promotion governance boundaries."""

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


@dataclass(frozen=True)
class EvaluationReport:
    dataset_name: str
    run_name: str
    scores: dict[str, float]


class LangfuseEvaluationClient(Protocol):
    def create_dataset(self, **kwargs: Any) -> Any: ...

    def create_dataset_item(self, **kwargs: Any) -> Any: ...

    def run_experiment(self, **kwargs: Any) -> Any: ...

    def create_prompt(self, **kwargs: Any) -> Any: ...


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
    """The only application boundary allowed to attach a deployable prompt label."""

    REQUIRED_SCORES = frozenset({"compliance", "red_flag_recall", "tool_policy"})

    def __init__(self, langfuse: LangfuseEvaluationClient) -> None:
        self._langfuse = langfuse

    def publish(
        self,
        *,
        name: str,
        prompt: str | list[dict[str, Any]],
        report: EvaluationReport,
        label: str = "production",
    ) -> Any:
        failed = sorted(
            metric
            for metric in self.REQUIRED_SCORES
            if report.scores.get(metric, 0.0) < 1.0
        )
        if failed:
            raise PromptPublishDenied(f"publish gate failed: {', '.join(failed)}")
        return self._langfuse.create_prompt(
            name=name,
            prompt=prompt,
            labels=[label],
            config={
                "evaluation_dataset": report.dataset_name,
                "evaluation_run": report.run_name,
                "scores": report.scores,
            },
            commit_message=f"Promoted after governed evaluation {report.run_name}",
        )
