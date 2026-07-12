from types import SimpleNamespace

from pydantic import BaseModel

from clinic_agency.orchestration.openai_model import OpenAIStructuredModel


class Answer(BaseModel):
    answer: str
    requested_tools: tuple[str, ...] = ()


class FakeResponses:
    def __init__(self):
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=Answer(answer="Grounded answer"),
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
        )


class FakeClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_openai_model_returns_validated_output_and_computed_cost() -> None:
    client = FakeClient()
    model = OpenAIStructuredModel(
        client=client,
        pricing={"gpt-test": (1.0, 2.0)},
    )

    output, cost = model.generate_structured(
        model="gpt-test",
        prompt="Follow clinic policy.",
        input={"question": "synthetic question"},
        output_schema=Answer,
        allowed_tools=(),
        max_cost_usd=0.01,
        metadata={"case_id": "eval-1", "role": "Knowledge", "task_type": "answer"},
    )

    assert output == {"answer": "Grounded answer", "requested_tools": ()}
    assert cost == 0.002
    call = client.responses.calls[0]
    assert call["store"] is False
    assert call["text_format"] is Answer
    assert call["max_output_tokens"] > 0
    assert "synthetic question" in call["input"]


def test_openai_model_refuses_unknown_pricing() -> None:
    model = OpenAIStructuredModel(client=FakeClient(), pricing={})

    try:
        model.generate_structured(
            model="unknown",
            prompt="prompt",
            input={},
            output_schema=Answer,
            allowed_tools=(),
            max_cost_usd=1,
            metadata={"case_id": "eval-1", "role": "Knowledge", "task_type": "answer"},
        )
    except ValueError as error:
        assert "pricing" in str(error)
    else:
        raise AssertionError("unknown model pricing bypassed cost enforcement")
