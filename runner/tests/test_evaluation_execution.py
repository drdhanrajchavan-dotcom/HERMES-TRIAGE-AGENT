import pytest

from clinic_agency.domain.roles import Autonomy, PromptRef, RoleConfig
from clinic_agency.evaluation.execution import (
    EvaluatorScore,
    GovernedEvaluationRunner,
    ImmutableProvenanceError,
    PersistedExperimentAdapter,
)
from clinic_agency.evaluation.governance import ExperimentProvenance
from clinic_agency.evaluation.scenarios import clinic_safety_scenarios
from clinic_agency.orchestration.role_runner import RoleRunResult


class FakeRoleRunner:
    def __init__(self):
        self.calls = []

    def run(self, role, task):
        self.calls.append((role, task))
        return RoleRunResult(output={"safe": True})


class FakeLangfuse:
    def __init__(self):
        self.runs = []
        self.scores = []

    def run_experiment(self, **kwargs):
        self.runs.append(kwargs)
        outputs = [kwargs["task"](item) for item in kwargs["data"]]
        for item, output in zip(kwargs["data"], outputs, strict=True):
            for evaluator in kwargs["evaluators"]:
                score = evaluator(input=item.input, output=output, expected_output=item.expected)
                self.scores.append((item.case_id, score))
        return type("Result", (), {"run_id": "run-123"})()

    def create_score(self, **kwargs):
        self.scores.append(kwargs)


class MemoryRecords:
    def __init__(self):
        self.values = {}
        self.promotions = []

    def create(self, provenance):
        if provenance.experiment_id in self.values:
            raise KeyError(provenance.experiment_id)
        self.values[provenance.experiment_id] = provenance

    def get(self, experiment_id):
        return self.values[experiment_id]

    def promote_prompt_version(self, **kwargs):
        self.promotions.append(kwargs)
        return "promoted"


@pytest.fixture
def role():
    return RoleConfig(
        name="Triage", mission="Synthetic safety evaluation",
        prompt_ref=PromptRef(name="roles/triage", label="candidate"),
        model="test", autonomy=Autonomy.AUTO,
    )


def test_runner_executes_all_ten_synthetic_scenarios_through_role_boundary(role):
    roles = FakeRoleRunner()
    langfuse = FakeLangfuse()
    runner = GovernedEvaluationRunner(langfuse=langfuse, role_runner=roles)

    result = runner.run(
        dataset_name="clinic-safety-v1", run_name="candidate-7", role=role,
        task_type="triage", scenarios=clinic_safety_scenarios(),
        evaluators=[lambda **_: EvaluatorScore("compliance", 1.0, "compliance@1")],
    )

    assert result.run_id == "run-123"
    assert len(roles.calls) == 10
    assert [call[1].case_id for call in roles.calls] == [f"eval-{i:03d}" for i in range(1, 11)]
    assert all(call[1].input["synthetic"] is True for call in roles.calls)
    assert langfuse.runs[0]["metadata"]["synthetic_only"] == "true"
    persisted = langfuse.scores[0][1]
    assert persisted.name == "compliance"
    assert persisted.metadata == {"evaluator_version": "compliance@1"}


def test_runner_rejects_partial_or_non_synthetic_publish_gate_suite(role):
    runner = GovernedEvaluationRunner(langfuse=FakeLangfuse(), role_runner=FakeRoleRunner())
    with pytest.raises(ValueError, match="exactly 10"):
        runner.run(
            dataset_name="x", run_name="x", role=role, task_type="triage",
            scenarios=clinic_safety_scenarios()[:-1], evaluators=[],
        )


def test_score_sink_persists_evaluator_identity_without_payload_content():
    client = FakeLangfuse()
    runner = GovernedEvaluationRunner(langfuse=client, role_runner=FakeRoleRunner())
    runner.persist_score(
        experiment_id="run-123", trace_id="trace-1", case_id="eval-001",
        score=EvaluatorScore("tool_policy", 1.0, "tool-policy@2"),
    )
    assert client.scores[-1] == {
        "name": "tool_policy", "value": 1.0, "trace_id": "trace-1",
        "dataset_run_id": "run-123",
        "metadata": {
            "experiment_id": "run-123",
            "case_id": "eval-001",
            "evaluator_version": "tool-policy@2",
            "synthetic": True,
        },
    }


def test_provenance_adapter_is_create_only_and_returns_persisted_record():
    records = MemoryRecords()
    adapter = PersistedExperimentAdapter(records)
    provenance = ExperimentProvenance(
        experiment_id="run-123", completed=True, prompt_name="roles/triage",
        prompt_version=7, dataset_id="dataset-1", dataset_version="v1", sample_count=10,
        scores={"compliance": 1.0}, evaluator_versions={"compliance": "compliance@1"},
    )
    adapter.persist(provenance)
    assert adapter.get_experiment_provenance("run-123") == provenance
    with pytest.raises(ImmutableProvenanceError):
        adapter.persist(provenance)


def test_provenance_adapter_exposes_prompt_promotion_for_publish_gate():
    records = MemoryRecords()
    adapter = PersistedExperimentAdapter(records)
    result = adapter.promote_prompt_version(
        name="roles/triage", version=7, label="production", provenance="run-123"
    )
    assert result == "promoted"
    assert records.promotions == [{
        "name": "roles/triage", "version": 7, "label": "production",
        "provenance": "run-123",
    }]
