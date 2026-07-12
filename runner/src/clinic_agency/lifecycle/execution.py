"""Lifecycle due-task execution with durable claiming and exact-draft authorization."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from clinic_agency.safety.outbound import (
    ComplianceReview,
    OutboundDraft,
    OutboundGate,
    UnsafeOutboundError,
)


@dataclass(frozen=True)
class LifecycleExecutionState:
    case_open: bool
    opted_out: bool
    superseded: bool

    def cancellation_reason(self) -> str | None:
        if not self.case_open:
            return "case_closed"
        if self.opted_out:
            return "recipient_opted_out"
        if self.superseded:
            return "task_superseded"
        return None


@dataclass(frozen=True)
class DueLifecycleTask:
    task_id: str
    case_id: str
    due_at: datetime
    draft: OutboundDraft
    review: ComplianceReview
    state: LifecycleExecutionState

    def __post_init__(self) -> None:
        if self.draft.case_id != self.case_id:
            raise ValueError("lifecycle task and outbound draft case IDs must match")


@dataclass(frozen=True)
class LifecycleRunSummary:
    claimed: int = 0
    sent: int = 0
    cancelled: int = 0
    retrying: int = 0


class LifecycleTaskStore(Protocol):
    """Durable port whose claim operation must atomically exclude prior/in-flight tasks."""

    def claim_due(self, *, now: datetime, limit: int) -> list[DueLifecycleTask]: ...
    def complete(self, task_id: str, *, delivery_id: str, idempotency_key: str) -> None: ...
    def cancel(self, task_id: str, *, reason: str) -> None: ...
    def retry(self, task_id: str, *, error: str) -> None: ...


class LifecycleSender(Protocol):
    def send(self, outbound: object, *, idempotency_key: str) -> str: ...


class LifecycleDueTaskExecutor:
    def __init__(self, *, tasks: LifecycleTaskStore, sender: LifecycleSender) -> None:
        self._tasks = tasks
        self._sender = sender

    def run_due(self, *, now: datetime, limit: int = 100) -> LifecycleRunSummary:
        if limit < 1:
            raise ValueError("limit must be positive")
        claimed = self._tasks.claim_due(now=now, limit=limit)
        sent = cancelled = retrying = 0
        for task in claimed:
            reason = task.state.cancellation_reason()
            if reason:
                self._tasks.cancel(task.task_id, reason=reason)
                cancelled += 1
                continue
            try:
                outbound = OutboundGate.authorize(task.draft, task.review)
            except UnsafeOutboundError:
                self._tasks.cancel(task.task_id, reason="exact_draft_compliance_failed")
                cancelled += 1
                continue

            key = f"lifecycle:{task.task_id}:{task.draft.draft_hash}"
            try:
                delivery_id = self._sender.send(outbound, idempotency_key=key)
            except Exception as error:
                self._tasks.retry(task.task_id, error=type(error).__name__)
                retrying += 1
                continue
            self._tasks.complete(task.task_id, delivery_id=delivery_id, idempotency_key=key)
            sent += 1
        return LifecycleRunSummary(
            claimed=len(claimed), sent=sent, cancelled=cancelled, retrying=retrying
        )
