import json
from collections.abc import Mapping
from typing import Any, Protocol

from openai import OpenAI
from pydantic import BaseModel


class ParsedResponses(Protocol):
    def parse(self, **kwargs: Any) -> Any: ...


class OpenAIClient(Protocol):
    responses: ParsedResponses


class OpenAIStructuredModel:
    """Structured Responses API adapter with deterministic local cost accounting."""

    def __init__(
        self,
        *,
        client: OpenAIClient | None = None,
        pricing: Mapping[str, tuple[float, float]],
    ) -> None:
        self._client = client or OpenAI()
        self._pricing = dict(pricing)

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
    ) -> tuple[dict[str, Any] | None, float]:
        del allowed_tools
        prices = self._pricing.get(model)
        if prices is None:
            raise ValueError(f"pricing is required for model: {model}")
        input_price, output_price = prices
        if input_price < 0 or output_price <= 0:
            raise ValueError("model pricing must be non-negative with positive output pricing")
        if max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be positive")
        max_output_tokens = max(1, min(4096, int(max_cost_usd * 1_000_000 / output_price)))
        instructions = (
            prompt
            if isinstance(prompt, str)
            else json.dumps(prompt, separators=(",", ":"))
        )
        safe_metadata = {
            key: str(value)[:512]
            for key, value in metadata.items()
            if key in {"case_id", "role", "task_type", "prompt_version"}
        }
        response = self._client.responses.parse(
            model=model,
            instructions=instructions,
            input=json.dumps(input, separators=(",", ":")),
            text_format=output_schema,
            max_output_tokens=max_output_tokens,
            metadata=safe_metadata,
            store=False,
        )
        usage = response.usage
        cost = (
            usage.input_tokens * input_price + usage.output_tokens * output_price
        ) / 1_000_000
        parsed = response.output_parsed
        return (parsed.model_dump() if parsed is not None else None), cost
