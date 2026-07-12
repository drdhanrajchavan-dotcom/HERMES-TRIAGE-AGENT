"""Server-side execution and persistence boundaries for governed synthetic evaluations."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from langfuse import Evaluation

from clinic_agency.domain.roles import RoleConfig
from clinic_agency.evaluation.governance import EvaluationCase, ExperimentProvenance
from clinic_agency.orchestration.role_runner import RoleRunner, RoleTask


@dataclass(frozen=True)
class EvaluatorScore:
    name: str
    value: float
    evaluator_version: str
    comment: str | None = None


class EvaluationClient(Protocol):
    def run_experiment(self, **kwargs: Any) -> Any: ...
    def create_score(self, **kwargs: Any) -> Any: ...


class ProvenanceRecords(Protocol):
    """A durable create-only record port; the parent may bind this to business persistence."""

    def create(self, provenance: ExperimentProvenance) -> None: ...
    def get(self, experiment_id: str) -> ExperimentProvenance: ...
    def promote_prompt_version(self, **kwargs: Any) -> Any: ...


class ImmutableProvenanceError(RuntimeError):
    pass


class PersistedExperimentAdapter:
    """Expose immutable experiment provenance to the publish gate.

    Persistence is deliberately behind a Python port so this slice does not duplicate or
    modify the Convex schema. The backing implementation must make ``create`` atomic.
    """

    def __init__(self, records: ProvenanceRecords) -> None:
        self._records = records

    def persist(self, provenance: ExperimentProvenance) -> None:
        try:
            self._records.create(provenance)
        except (KeyError, FileExistsError) as error:
            raise ImmutableProvenanceError(
                f"experiment provenance already exists: {provenance.experiment_id}"
            ) from error

    def get_experiment_provenance(self, experiment_id: str) -> ExperimentProvenance:
        return self._records.get(experiment_id)

    def promote_prompt_version(self, **kwargs: Any) -> Any:
        return self._records.promote_prompt_version(**kwargs)


class GovernedEvaluationRunner:
    """Run the complete synthetic safety suite through the production role boundary."""

    def __init__(self, *, langfuse: EvaluationClient, role_runner: RoleRunner) -> None:
        self._langfuse = langfuse
        self._role_runner = role_runner

    def run(
        self,
        *,
        dataset_name: str,
        run_name: str,
        role: RoleConfig,
        task_type: str,
        scenarios: Sequence[EvaluationCase],
        evaluators: list[Callable[..., EvaluatorScore]],
    ) -> Any:
        if len(scenarios) != 10:
            raise ValueError("governed publish-gate suite must contain exactly 10 scenarios")
        if len({case.case_id for case in scenarios}) != 10:
            raise ValueError("governed scenarios must have unique case IDs")

        def execute(case: EvaluationCase) -> dict[str, Any]:
            result = self._role_runner.run(
                role,
                RoleTask(case_id=case.case_id, task_type=task_type, input=case.input),
            )
            return result.output

        def langfuse_evaluator(
            evaluator: Callable[..., EvaluatorScore],
        ) -> Callable[..., Evaluation]:
            def evaluate(**kwargs: Any) -> Evaluation:
                score = evaluator(**kwargs)
                return Evaluation(
                    name=score.name,
                    value=score.value,
                    comment=score.comment,
                    metadata={"evaluator_version": score.evaluator_version},
                )

            return evaluate

        return self._langfuse.run_experiment(
            name=dataset_name,
            run_name=run_name,
            data=list(scenarios),
            task=execute,
            evaluators=[langfuse_evaluator(evaluator) for evaluator in evaluators],
            metadata={
                "case_id": "evaluation",
                "role": role.name,
                "task_type": task_type,
                "synthetic_only": "true",
            },
        )

    def persist_score(
        self,
        *,
        experiment_id: str,
        trace_id: str,
        case_id: str,
        score: EvaluatorScore,
    ) -> Any:
        if not case_id.startswith("eval-"):
            raise ValueError("scores may only be persisted for synthetic evaluation cases")
        return self._langfuse.create_score(
            name=score.name,
            value=score.value,
            trace_id=trace_id,
            dataset_run_id=experiment_id,
            metadata={
                "experiment_id": experiment_id,
                "case_id": case_id,
                "evaluator_version": score.evaluator_version,
                "synthetic": True,
            },
        )
