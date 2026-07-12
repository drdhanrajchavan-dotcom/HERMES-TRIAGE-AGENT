from datetime import UTC, datetime

from clinic_agency.domain.cases import Case
from clinic_agency.orchestration.telegram_reply import (
    IntelligentTelegramReplyWorkflow,
    TelegramReplyOutput,
    calendar_tool_registry,
)
from clinic_agency.safety.outbound import AuthorizedOutbound


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[int, AuthorizedOutbound]] = []

    def send(self, chat_id: int, outbound: AuthorizedOutbound):
        self.sent.append((chat_id, outbound))
        return type("Delivery", (), {"external_message_id": "sent-1"})()


class RecordingStore:
    def __init__(self) -> None:
        self.recorded: list[dict] = []

    def record_delivery(self, **values) -> None:
        self.recorded.append(values)


class RecordingRunner:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.calls = []

    def run(self, role, task):
        self.calls.append((role, task))
        return type("Run", (), {"output": self.output})()


class EvidenceService:
    def __init__(self) -> None:
        self.queries = []

    def gather(self, query, cards):
        self.queries.append((query, cards))
        return (
            type(
                "Evidence",
                (),
                {
                    "source_id": "linkup:1",
                    "title": "Acne care",
                    "excerpt": "Clinician-assessed acne care is available.",
                    "url": "https://clearskin.in/acne/",
                },
            )(),
        )


def test_routine_reply_uses_hosted_role_with_only_approved_evidence_then_exact_hash_gate() -> None:
    runner = RecordingRunner(
        {
            "text": "ClearSkin offers clinician-assessed acne care. Source: https://clearskin.in/acne/",
            "requested_tools": (),
        }
    )
    sender = RecordingSender()
    store = RecordingStore()
    evidence = EvidenceService()
    case = Case.from_telegram(11, 22, "What acne care is available?")

    result = IntelligentTelegramReplyWorkflow(
        sender=sender,
        recorder=store,
        role_runner=runner,
        role=object(),
        knowledge=evidence,
    ).handle(case, 22)

    assert evidence.queries == [(case.message, ())]
    task = runner.calls[0][1]
    assert task.case_id == "telegram:11"
    assert task.task_type == "telegram_reply"
    assert task.input == {
        "message": case.message,
        "evidence": [
            {
                "source_id": "linkup:1",
                "title": "Acne care",
                "excerpt": "Clinician-assessed acne care is available.",
                "url": "https://clearskin.in/acne/",
            }
        ],
    }
    assert store.recorded[0]["review"].draft_hash == result.draft_hash
    assert sender.sent[0][1].draft_hash == result.draft_hash


def test_red_flag_reply_bypasses_model_and_evidence() -> None:
    runner = RecordingRunner({"text": "unsafe", "requested_tools": ()})
    evidence = EvidenceService()
    sender = RecordingSender()
    case = Case.from_telegram(12, 22, "swollen and fever", ("swollen", "fever"))

    IntelligentTelegramReplyWorkflow(
        sender=sender,
        recorder=RecordingStore(),
        role_runner=runner,
        role=object(),
        knowledge=evidence,
    ).handle(case, 22)

    assert runner.calls == []
    assert evidence.queries == []
    assert "review this promptly" in sender.sent[0][1].text


def test_noncompliant_model_reply_falls_back_before_send() -> None:
    sender = RecordingSender()
    workflow = IntelligentTelegramReplyWorkflow(
        sender=sender,
        recorder=RecordingStore(),
        role_runner=RecordingRunner(
            {"text": "We guarantee a permanent cure.", "requested_tools": ()}
        ),
        role=object(),
        knowledge=EvidenceService(),
    )

    workflow.handle(Case.from_telegram(13, 22, "Can this be treated?"), 22)

    assert "received your message" in sender.sent[0][1].text.lower()
    assert "guarantee" not in sender.sent[0][1].text.lower()


class FakeCalendar:
    def __init__(self) -> None:
        self.reads = []
        self.holds = []

    def availability(self, start, end):
        self.reads.append((start, end))
        return type("Availability", (), {"available": True, "busy": ()})()

    def create_hold(self, request):
        self.holds.append(request)
        return type(
            "Hold",
            (),
            {
                "hold_key": request.hold_key,
                "event_id": "event-1",
                "status": "active",
                "start": request.start,
                "end": request.end,
                "expires_at": request.start,
            },
        )()


def test_calendar_registry_exposes_only_server_owned_read_and_hold_handlers() -> None:
    calendar = FakeCalendar()
    registry = calendar_tool_registry(calendar, case_id_provider=lambda: "telegram:11")
    start = "2030-01-01T10:00:00+05:30"
    end = "2030-01-01T10:30:00+05:30"

    definitions = registry.definitions(("calendar.read", "calendar.hold"))
    available = registry.dispatch(
        "calendar.read", f'{{"start":"{start}","end":"{end}"}}', ("calendar.read",)
    )
    held = registry.dispatch(
        "calendar.hold",
        f'{{"start":"{start}","end":"{end}"}}',
        ("calendar.hold",),
    )

    assert [item["name"] for item in definitions] == ["calendar.read", "calendar.hold"]
    assert available == {"available": True, "busy": []}
    assert held["event_id"] == "event-1"
    assert calendar.reads[0][0] == datetime.fromisoformat(start).astimezone(UTC)
    assert calendar.holds[0].case_id == "telegram:11"
    assert calendar.holds[0].hold_key.startswith("telegram:11:")


def test_reply_output_requires_visible_text() -> None:
    assert TelegramReplyOutput(text="Useful reply").text == "Useful reply"
