import pytest

from clinic_agency.evaluation.governance import (
    EvaluationCase,
    EvaluationGovernance,
    EvaluationReport,
    PromptPublishDenied,
    PromptPublishGate,
    Score,
)
from clinic_agency.evaluation.scenarios import clinic_safety_scenarios


class FakeLangfuse:
    def __init__(self):
        self.datasets = []
        self.items = []
        self.experiments = []
        self.prompts = []

    def create_dataset(self, **kwargs):
        self.datasets.append(kwargs)

    def create_dataset_item(self, **kwargs):
        self.items.append(kwargs)

    def run_experiment(self, **kwargs):
        self.experiments.append(kwargs)
        return "experiment-result"

    def create_prompt(self, **kwargs):
        self.prompts.append(kwargs)
        return "published"


def test_dataset_scaffolding_uses_synthetic_case_ids_and_governance_metadata():
    client = FakeLangfuse()
    governance = EvaluationGovernance(client)

    governance.create_dataset(
        "triage-v1",
        [EvaluationCase(case_id="eval-001", input={"intent": "pricing"}, expected={"safe": True})],
        role="Triage",
        task_type="triage",
    )

    assert client.datasets[0]["name"] == "triage-v1"
    assert client.items[0] == {
        "dataset_name": "triage-v1",
        "input": {"intent": "pricing"},
        "expected_output": {"safe": True},
        "metadata": {"case_id": "eval-001", "role": "Triage", "task_type": "triage"},
    }


def test_experiment_scaffolding_attaches_required_non_patient_metadata():
    client = FakeLangfuse()
    result = EvaluationGovernance(client).run_experiment(
        dataset_name="triage-v1",
        run_name="candidate-12",
        items=[object()],
        task=lambda item: item,
        evaluators=[lambda **kwargs: Score(name="compliance", value=1.0)],
        role="Triage",
        task_type="triage",
    )

    assert result == "experiment-result"
    assert client.experiments[0]["name"] == "triage-v1"
    assert client.experiments[0]["metadata"] == {
        "case_id": "evaluation",
        "role": "Triage",
        "task_type": "triage",
    }


def passing_report():
    return EvaluationReport(
        dataset_name="triage-v1",
        run_name="candidate-12",
        scores={"compliance": 1.0, "red_flag_recall": 1.0, "tool_policy": 1.0},
    )


def test_server_side_publish_gate_labels_prompt_only_after_required_scores_pass():
    client = FakeLangfuse()

    result = PromptPublishGate(client).publish(
        name="roles/triage",
        prompt="hosted prompt {{case_id}}",
        report=passing_report(),
        label="production",
    )

    assert result == "published"
    assert client.prompts[0]["labels"] == ["production"]
    assert client.prompts[0]["config"]["evaluation_run"] == "candidate-12"


def test_publish_gate_rejects_missing_or_failing_deterministic_scores():
    client = FakeLangfuse()
    report = EvaluationReport(
        dataset_name="triage-v1",
        run_name="bad-run",
        scores={"compliance": 1.0, "red_flag_recall": 0.99},
    )

    with pytest.raises(PromptPublishDenied, match="red_flag_recall, tool_policy"):
        PromptPublishGate(client).publish(
            name="roles/triage", prompt="unsafe candidate", report=report
        )

    assert client.prompts == []


def test_publish_gate_dataset_contains_ten_unique_synthetic_safety_scenarios():
    scenarios = clinic_safety_scenarios()

    assert len(scenarios) == 10
    assert len({scenario.case_id for scenario in scenarios}) == 10
    assert all(scenario.case_id.startswith("eval-") for scenario in scenarios)
    assert all(scenario.input["synthetic"] is True for scenario in scenarios)
