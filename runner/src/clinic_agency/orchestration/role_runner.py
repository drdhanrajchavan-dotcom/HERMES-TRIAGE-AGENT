from dataclasses import dataclass
from typing import Any, Protocol

from langfuse import get_client, observe, propagate_attributes

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
