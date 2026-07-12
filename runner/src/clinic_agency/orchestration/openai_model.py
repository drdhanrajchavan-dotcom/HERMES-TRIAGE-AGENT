import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel


class ParsedResponses(Protocol):
    def parse(self, **kwargs: Any) -> Any: ...


class OpenAIClient(Protocol):
    responses: ParsedResponses


class BudgetReservationError(RuntimeError):
    pass


class ToolDispatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServerTool:
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]


class ServerToolRegistry:
    """Server-owned definitions and handlers; model output never supplies either."""

    def __init__(self, tools: Mapping[str, ServerTool] | None = None) -> None:
        self._tools = dict(tools or {})

    def definitions(self, allowed: tuple[str, ...]) -> list[dict[str, Any]]:
        missing = sorted(set(allowed) - self._tools.keys())
        if missing:
            raise ToolDispatchError(f"allowed tool(s) not registered: {', '.join(missing)}")
        return [
            {
                "type": "function",
                "name": name,
                "description": self._tools[name].description,
                "parameters": self._tools[name].parameters,
                "strict": True,
            }
            for name in allowed
        ]

    def dispatch(self, name: str, arguments: str, allowed: tuple[str, ...]) -> Any:
        if name not in allowed:
            raise ToolDispatchError(f"tool not allowed: {name}")
        tool = self._tools.get(name)
        if tool is None:
            raise ToolDispatchError(f"tool not registered: {name}")
        try:
            parsed = json.loads(arguments)
        except (TypeError, json.JSONDecodeError) as error:
            raise ToolDispatchError(f"invalid arguments for tool: {name}") from error
        if not isinstance(parsed, dict):
            raise ToolDispatchError(f"tool arguments must be an object: {name}")
        return tool.handler(parsed)


class OpenAIStructuredModel:
    """Structured Responses adapter with pre-call reservation and server tool dispatch."""

    def __init__(
        self,
        *,
        client: OpenAIClient,
        pricing: Mapping[str, tuple[float, float]],
        token_estimator: Callable[[str], int] | None = None,
        tool_registry: ServerToolRegistry | None = None,
        max_tool_rounds: int = 2,
    ) -> None:
        if max_tool_rounds < 0 or max_tool_rounds > 4:
            raise ValueError("max_tool_rounds must be between 0 and 4")
        self._client = client
        self._pricing = dict(pricing)
        self._estimate = token_estimator or (lambda text: max(1, math.ceil(len(text) / 4)))
        self._tools = tool_registry or ServerToolRegistry()
        self._max_tool_rounds = max_tool_rounds

    def generate_structured(
        self,
        *,
        model: str,
        prompt: Any,
        input: dict[str, Any],
        output_schema: type[BaseModel],
        allowed_tools: tuple[str, ...],
        max_cost_usd: float,
        metadata: dict[str, Any],
        validation_feedback: str | None = None,
    ) -> tuple[dict[str, Any] | None, float]:
        prices = self._pricing.get(model)
        if prices is None:
            raise ValueError(f"pricing is required for model: {model}")
        input_price, output_price = prices
        if input_price < 0 or output_price <= 0 or max_cost_usd <= 0:
            raise ValueError("pricing and budget must be positive")
        instructions = (
            prompt if isinstance(prompt, str) else json.dumps(prompt, separators=(",", ":"))
        )
        if validation_feedback:
            instructions += "\nPrevious output validation failed: " + validation_feedback[:1000]
        serialized_input = json.dumps(input, separators=(",", ":"))
        tools = self._tools.definitions(allowed_tools) if allowed_tools else []
        safe_metadata = {
            key: str(value)[:512]
            for key, value in metadata.items()
            if key in {"case_id", "role", "task_type", "prompt_version"}
        }
        total_cost = 0.0
        request_input: str | list[dict[str, Any]] = serialized_input
        for tool_round in range(self._max_tool_rounds + 1):
            estimated_tokens = self._estimate(instructions + json.dumps(request_input))
            reserved_input_cost = estimated_tokens * input_price / 1_000_000
            remaining = max_cost_usd - total_cost - reserved_input_cost
            if remaining <= 0:
                raise BudgetReservationError("estimated input cost exhausts remaining budget")
            max_output_tokens = min(4096, int(remaining * 1_000_000 / output_price))
            if max_output_tokens < 1:
                raise BudgetReservationError("budget cannot reserve one output token")
            kwargs = dict(
                model=model,
                instructions=instructions,
                input=request_input,
                text_format=output_schema,
                max_output_tokens=max_output_tokens,
                metadata=safe_metadata,
                store=False,
            )
            if tools:
                kwargs["tools"] = tools
            response = self._client.responses.parse(**kwargs)
            usage = response.usage
            total_cost += (
                usage.input_tokens * input_price + usage.output_tokens * output_price
            ) / 1_000_000
            if total_cost > max_cost_usd:
                raise BudgetReservationError("provider usage exceeded reserved call budget")
            parsed = response.output_parsed
            if parsed is not None:
                return parsed.model_dump(), total_cost
            calls = [
                item
                for item in getattr(response, "output", ())
                if item.type == "function_call"
            ]
            if not calls:
                return None, total_cost
            if tool_round == self._max_tool_rounds:
                raise ToolDispatchError("maximum tool rounds exceeded")
            request_input = []
            for call in calls:
                result = self._tools.dispatch(call.name, call.arguments, allowed_tools)
                request_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, separators=(",", ":")),
                    }
                )
        raise AssertionError("unreachable")