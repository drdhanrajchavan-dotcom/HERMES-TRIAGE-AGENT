from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from clinic_agency.config import Settings, create_openai_client
from clinic_agency.evaluation.governance import (
    ExperimentProvenance,
    PromptPublishDenied,
    PromptPublishGate,
)
from clinic_agency.orchestration.openai_model import (
    BudgetReservationError,
    OpenAIStructuredModel,
    ServerTool,
    ServerToolRegistry,
)


class Answer(BaseModel):
    answer: str


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


def response(*, parsed=None, output=(), input_tokens=10, output_tokens=10):
    return SimpleNamespace(
        output_parsed=parsed,
        output=output,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_provider_client_factory_uses_explicit_credentials_and_bounds(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("clinic_agency.config.OpenAI", Client)
    settings = Settings(
        model_api_key="secret",
        model_base_url="https://provider.example/v1",
        model_timeout_seconds=12,
        model_max_retries=1,
    )

    create_openai_client(settings)

    assert captured == {
        "api_key": "secret",
        "base_url": "https://provider.example/v1",
        "timeout": 12.0,
        "max_retries": 1,
    }


def test_model_rejects_before_call_when_estimated_input_exhausts_budget():
    client = FakeClient([])
    model = OpenAIStructuredModel(
        client=client,
        pricing={"gpt-test": (10.0, 20.0)},
        token_estimator=lambda _text: 1_000,
    )

    with pytest.raises(BudgetReservationError, match="estimated input"):
        model.generate_structured(
            model="gpt-test",
            prompt="prompt",
            input={"x": "y"},
            output_schema=Answer,
            allowed_tools=(),
            max_cost_usd=0.01,
            metadata={},
        )

    assert client.responses.calls == []


def test_only_allowlisted_registered_tools_are_exposed_and_dispatched():
    seen = []
    registry = ServerToolRegistry(
        {
            "knowledge.read": ServerTool(
                description="Read approved knowledge",
                parameters={"type": "object", "properties": {"query": {"type": "string"}}},
                handler=lambda args: seen.append(args) or {"result": "approved"},
            ),
            "calendar.read": ServerTool(
                description="Read calendar",
                parameters={"type": "object", "properties": {}},
                handler=lambda args: {"slots": []},
            ),
        }
    )
    tool_call = SimpleNamespace(
        type="function_call", name="knowledge.read", arguments='{"query":"hours"}', call_id="c1"
    )
    client = FakeClient(
        [response(output=[tool_call]), response(parsed=Answer(answer="9 to 5"))]
    )
    model = OpenAIStructuredModel(
        client=client,
        pricing={"gpt-test": (1.0, 1.0)},
        token_estimator=lambda _text: 10,
        tool_registry=registry,
    )

    output, _ = model.generate_structured(
        model="gpt-test",
        prompt="prompt",
        input={},
        output_schema=Answer,
        allowed_tools=("knowledge.read",),
        max_cost_usd=0.01,
        metadata={},
    )

    assert output == {"answer": "9 to 5"}
    assert seen == [{"query": "hours"}]
    assert [tool["name"] for tool in client.responses.calls[0]["tools"]] == ["knowledge.read"]
    assert "calendar.read" not in str(client.responses.calls)
    assert client.responses.calls[1]["input"][-1] == {
        "type": "function_call_output",
        "call_id": "c1",
        "output": '{"result":"approved"}',
    }


def test_publish_gate_fetches_immutable_provenance_and_promotes_bound_version():
    class Store:
        def __init__(self):
            self.promotions = []

        def get_experiment_provenance(self, experiment_id):
            assert experiment_id == "exp-immutable"
            return ExperimentProvenance(
                experiment_id="exp-immutable",
                completed=True,
                prompt_name="roles/triage",
                prompt_version=12,
                dataset_id="dataset-1",
                dataset_version="sha256:abc",
                sample_count=10,
                scores={"compliance": 1.0, "red_flag_recall": 1.0, "tool_policy": 1.0},
                evaluator_versions={
                    "compliance": "v1",
                    "red_flag_recall": "v1",
                    "tool_policy": "v1",
                },
            )

        def promote_prompt_version(self, **kwargs):
            self.promotions.append(kwargs)
            return "published"

    store = Store()
    result = PromptPublishGate(store, minimum_samples=10).publish(
        name="roles/triage", prompt_version=12, experiment_id="exp-immutable"
    )

    assert result == "published"
    assert store.promotions == [
        {
            "name": "roles/triage",
            "version": 12,
            "label": "production",
            "provenance": "exp-immutable",
        }
    ]


def test_publish_gate_rejects_mismatched_or_incomplete_persisted_provenance():
    class Store:
        def get_experiment_provenance(self, _experiment_id):
            return ExperimentProvenance(
                experiment_id="exp-1",
                completed=False,
                prompt_name="roles/other",
                prompt_version=2,
                dataset_id="",
                dataset_version="",
                sample_count=1,
                scores={},
                evaluator_versions={},
            )

        def promote_prompt_version(self, **_kwargs):
            raise AssertionError("must not promote")

    with pytest.raises(PromptPublishDenied, match="completed"):
        PromptPublishGate(Store()).publish(
            name="roles/triage", prompt_version=1, experiment_id="exp-1"
        )
