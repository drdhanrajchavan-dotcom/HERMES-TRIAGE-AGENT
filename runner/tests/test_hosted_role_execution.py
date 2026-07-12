import pytest
from pydantic import BaseModel

from clinic_agency.domain.roles import Autonomy, PromptRef, RoleConfig
from clinic_agency.orchestration.role_runner import (
    BudgetExceededError,
    HostedRoleExecutor,
    RoleExecutionError,
    RoleTask,
    ToolNotAllowedError,
)


class TriageOutput(BaseModel):
    intent: str
    requested_tools: tuple[str, ...] = ()


class FakePrompt:
    version = 7

    def compile(self, **variables):
        assert variables == {"case_id": "case-1", "task_type": "triage"}
        return "hosted instructions"


class FakeLangfuse:
    def __init__(self):
        self.prompt_calls = []

    def get_prompt(self, name, *, label):
        self.prompt_calls.append((name, label))
        return FakePrompt()


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def role(**overrides):
    values = dict(
        name="Triage",
        mission="Classify safely",
        prompt_ref=PromptRef(name="roles/triage", label="production"),
        model="gpt-test",
        tools=("knowledge.read",),
        autonomy=Autonomy.AUTO,
        max_cost_usd=0.05,
    )
    values.update(overrides)
    return RoleConfig(**values)


def task():
    return RoleTask(case_id="case-1", task_type="triage", input={"message": "private"})


def test_fetches_hosted_prompt_by_name_and_label_and_validates_structured_output():
    langfuse = FakeLangfuse()
    model = FakeModel([({"intent": "pricing", "requested_tools": ["knowledge.read"]}, 0.01)])

    result = HostedRoleExecutor(
        langfuse=langfuse, model=model, output_schemas={"triage": TriageOutput}
    )(role(), task())

    assert langfuse.prompt_calls == [("roles/triage", "production")]
    assert result.output == {"intent": "pricing", "requested_tools": ("knowledge.read",)}
    assert result.cost_usd == 0.01
    assert model.calls[0]["prompt"] == "hosted instructions"
    assert model.calls[0]["max_cost_usd"] == 0.05
    assert model.calls[0]["metadata"] == {
        "case_id": "case-1",
        "role": "Triage",
        "task_type": "triage",
        "prompt_version": 7,
    }
    assert "private" not in repr(model.calls[0]["metadata"])


def test_retries_are_bounded_and_accumulated_cost_cannot_exceed_role_budget():
    model = FakeModel(
        [
            (None, 0.03),
            ({"intent": "pricing"}, 0.03),
        ]
    )
    executor = HostedRoleExecutor(
        langfuse=FakeLangfuse(),
        model=model,
        output_schemas={"triage": TriageOutput},
        max_attempts=2,
    )

    with pytest.raises(BudgetExceededError):
        executor(role(), task())

    assert len(model.calls) == 2


def test_invalid_outputs_stop_after_bounded_attempts():
    model = FakeModel([(None, 0.0), (None, 0.0)])

    with pytest.raises(RoleExecutionError, match="after 2 attempts"):
        HostedRoleExecutor(
            langfuse=FakeLangfuse(),
            model=model,
            output_schemas={"triage": TriageOutput},
            max_attempts=2,
        )(role(), task())

    assert len(model.calls) == 2


def test_model_cannot_request_tool_outside_deterministic_role_allowlist():
    model = FakeModel([({"intent": "book", "requested_tools": ["calendar.hold"]}, 0.01)])

    with pytest.raises(ToolNotAllowedError, match="calendar.hold"):
        HostedRoleExecutor(
            langfuse=FakeLangfuse(), model=model, output_schemas={"triage": TriageOutput}
        )(role(), task())
