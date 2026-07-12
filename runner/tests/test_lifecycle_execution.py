from datetime import UTC, datetime

from clinic_agency.lifecycle.execution import (
    DueLifecycleTask,
    LifecycleDueTaskExecutor,
    LifecycleExecutionState,
)
from clinic_agency.safety.outbound import ComplianceReview, OutboundDraft


class MemoryTasks:
    def __init__(self, tasks):
        self.tasks = tasks
        self.completed = []
        self.cancelled = []
        self.failed = []

    def claim_due(self, *, now, limit):
        return self.tasks[:limit]

    def complete(self, task_id, *, delivery_id, idempotency_key):
        self.completed.append((task_id, delivery_id, idempotency_key))

    def cancel(self, task_id, *, reason):
        self.cancelled.append((task_id, reason))

    def retry(self, task_id, *, error):
        self.failed.append((task_id, error))


class Sender:
    def __init__(self):
        self.calls = []

    def send(self, outbound, *, idempotency_key):
        self.calls.append((outbound, idempotency_key))
        return "delivery-1"


def task(**overrides):
    draft = OutboundDraft.create("case-1", "Your synthetic follow-up")
    values = dict(
        task_id="task-1", case_id="case-1", due_at=datetime(2026, 7, 12, tzinfo=UTC),
        draft=draft, review=ComplianceReview.pass_draft(draft),
        state=LifecycleExecutionState(case_open=True, opted_out=False, superseded=False),
    )
    values.update(overrides)
    return DueLifecycleTask(**values)


def test_due_executor_delivers_only_the_exact_compliance_approved_draft():
    tasks = MemoryTasks([task()])
    sender = Sender()
    result = LifecycleDueTaskExecutor(tasks=tasks, sender=sender).run_due(
        now=datetime(2026, 7, 12, 1, tzinfo=UTC), limit=10
    )
    assert result.sent == 1
    assert sender.calls[0][0].text == "Your synthetic follow-up"
    assert sender.calls[0][1] == "lifecycle:task-1:" + task().draft.draft_hash
    assert tasks.completed == [("task-1", "delivery-1", sender.calls[0][1])]


def test_mismatched_review_is_cancelled_without_delivery():
    original = task()
    changed = OutboundDraft.create("case-1", "Changed after approval")
    tasks = MemoryTasks([task(draft=changed, review=original.review)])
    sender = Sender()
    result = LifecycleDueTaskExecutor(tasks=tasks, sender=sender).run_due(
        now=datetime(2026, 7, 12, 1, tzinfo=UTC)
    )
    assert result.cancelled == 1
    assert sender.calls == []
    assert tasks.cancelled == [("task-1", "exact_draft_compliance_failed")]


def test_business_cancellation_conditions_prevent_delivery():
    rows = [
        (
            LifecycleExecutionState(case_open=False, opted_out=False, superseded=False),
            "case_closed",
        ),
        (
            LifecycleExecutionState(case_open=True, opted_out=True, superseded=False),
            "recipient_opted_out",
        ),
        (
            LifecycleExecutionState(case_open=True, opted_out=False, superseded=True),
            "task_superseded",
        ),
    ]
    for state, reason in rows:
        tasks = MemoryTasks([task(state=state)])
        sender = Sender()
        LifecycleDueTaskExecutor(tasks=tasks, sender=sender).run_due(
            now=datetime(2026, 7, 12, 1, tzinfo=UTC)
        )
        assert sender.calls == []
        assert tasks.cancelled == [("task-1", reason)]


def test_idempotency_key_is_stable_and_claim_port_owns_duplicate_suppression():
    first = MemoryTasks([task()])
    sender = Sender()
    executor = LifecycleDueTaskExecutor(tasks=first, sender=sender)
    executor.run_due(now=datetime(2026, 7, 12, 1, tzinfo=UTC))
    key = sender.calls[0][1]

    # A durable store atomically claims only pending tasks, so the next poll returns none.
    first.tasks = []
    result = executor.run_due(now=datetime(2026, 7, 12, 2, tzinfo=UTC))
    assert result.claimed == 0
    assert len(sender.calls) == 1
    assert first.completed[0][2] == key
