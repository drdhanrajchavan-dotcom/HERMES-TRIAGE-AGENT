from dataclasses import dataclass
from typing import Any, Protocol

from langfuse import get_client, observe, propagate_attributes
from pydantic import BaseModel, ValidationError

from clinic_agency.domain.roles import RoleConfig


@dataclass(frozen=True)
class RoleTask:
    case_id: str
    task_type: str
    input: dict[str, Any]


@dataclass(frozen=True)
class RoleRunResult:
    output: dict[str, Any]
    cost_usd: float = 0


class RoleExecutor(Protocol):
    def __call__(self, role: RoleConfig, task: RoleTask) -> RoleRunResult: ...


class RoleExecutionError(RuntimeError):
    pass


class BudgetExceededError(RoleExecutionError):
    pass


class ToolNotAllowedError(RoleExecutionError):
    pass


class StructuredModel(Protocol):
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
    ) -> tuple[dict[str, Any] | None, float]: ...


class PromptStore(Protocol):
    def get_prompt(self, name: str, *, label: str) -> Any: ...


class HostedRoleExecutor:
    """Execute a hosted role prompt while enforcing deterministic local limits."""

    def __init__(
        self,
        *,
        langfuse: PromptStore,
        model: StructuredModel,
        output_schemas: dict[str, type[BaseModel]],
        max_attempts: int = 2,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._langfuse = langfuse
        self._model = model
        self._output_schemas = output_schemas
        self._max_attempts = max_attempts

    def __call__(self, role: RoleConfig, task: RoleTask) -> RoleRunResult:
        schema = self._output_schemas.get(task.task_type)
        if schema is None:
            raise RoleExecutionError(f"no output schema for task type: {task.task_type}")
        hosted_prompt = self._langfuse.get_prompt(
            role.prompt_ref.name, label=role.prompt_ref.label
        )
        prompt = hosted_prompt.compile(case_id=task.case_id, task_type=task.task_type)
        metadata = {
            "case_id": task.case_id,
            "role": role.name,
            "task_type": task.task_type,
            "prompt_version": hosted_prompt.version,
        }
        total_cost = 0.0
        validation_feedback = None
        for _attempt in range(self._max_attempts):
            raw, cost = self._model.generate_structured(
                model=role.model,
                prompt=prompt,
                input=task.input,
                output_schema=schema,
                allowed_tools=role.tools,
                max_cost_usd=role.max_cost_usd - total_cost,
                metadata=metadata,
                validation_feedback=validation_feedback,
            )
            total_cost += cost
            if total_cost > role.max_cost_usd:
                raise BudgetExceededError(
                    f"role cost ${total_cost:.4f} exceeded ${role.max_cost_usd:.4f} budget"
                )
            try:
                output = schema.model_validate(raw)
            except ValidationError as error:
                validation_feedback = "; ".join(
                    f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                    for item in error.errors(include_input=False)
                )
                continue
            requested = tuple(getattr(output, "requested_tools", ()))
            forbidden = sorted(set(requested) - set(role.tools))
            if forbidden:
                raise ToolNotAllowedError(f"tool(s) not allowed: {', '.join(forbidden)}")
            return RoleRunResult(output=output.model_dump(), cost_usd=total_cost)
        raise RoleExecutionError(
            f"structured model output invalid after {self._max_attempts} attempts"
        )


class RoleRunner:
    """Execute any validated role config through one instrumented boundary."""

    def __init__(self, executor: RoleExecutor) -> None:
        self._executor = executor

    @observe(
        name="role.execute",
        as_type="agent",
        capture_input=False,
        capture_output=False,
    )
    def run(self, role: RoleConfig, task: RoleTask) -> RoleRunResult:
        metadata = {
            "case_id": task.case_id,
            "role": role.name,
            "task_type": task.task_type,
            "model": role.model,
            "prompt_name": role.prompt_ref.name,
            "prompt_label": role.prompt_ref.label,
        }
        langfuse = get_client()
        langfuse.update_current_trace(metadata=metadata, tags=[role.name, task.task_type])
        langfuse.update_current_span(
            input={"case_id": task.case_id, "task_type": task.task_type},
            metadata=metadata,
        )
        with propagate_attributes(session_id=task.case_id, metadata=metadata):
            result = self._executor(role, task)
        langfuse.update_current_span(
            output={"status": "ok", "cost_usd": result.cost_usd}
        )
        return result
