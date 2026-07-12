from clinic_agency.domain.cases import Case
from clinic_agency.orchestration.acknowledgement import SafeAcknowledgementWorkflow
from clinic_agency.safety.outbound import AuthorizedOutbound, ComplianceReview


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[int, AuthorizedOutbound]] = []

    def send(self, chat_id: int, outbound: AuthorizedOutbound):
        self.sent.append((chat_id, outbound))
        return type("Delivery", (), {"external_message_id": "42"})()


class RecordingStore:
    def __init__(self) -> None:
        self.recorded: list[dict] = []

    def record_delivery(
        self,
        *,
        external_event_id: str,
        outbound: AuthorizedOutbound,
        review: ComplianceReview,
        external_message_id: str,
    ) -> None:
        self.recorded.append(
            {
                "external_event_id": external_event_id,
                "outbound": outbound,
                "review": review,
                "external_message_id": external_message_id,
            }
        )


def test_workflow_sends_and_records_reviewed_routine_acknowledgement() -> None:
    case = Case.from_telegram(101, 99, "How much is laser treatment?")
    sender = RecordingSender()
    store = RecordingStore()

    result = SafeAcknowledgementWorkflow(sender=sender, recorder=store).handle(case, chat_id=99)

    assert result.sent is True
    assert len(sender.sent) == 1
    assert sender.sent[0][0] == 99
    assert "received your message" in sender.sent[0][1].text.lower()
    assert store.recorded[0]["review"].verdict == "pass"
    assert store.recorded[0]["review"].draft_hash == sender.sent[0][1].draft_hash


def test_workflow_uses_urgent_non_diagnostic_red_flag_acknowledgement() -> None:
    case = Case.from_telegram(102, 99, "Swollen and fever", ("swollen", "fever"))
    sender = RecordingSender()
    store = RecordingStore()

    SafeAcknowledgementWorkflow(sender=sender, recorder=store).handle(case, chat_id=99)

    text = sender.sent[0][1].text.lower()
    assert "review this promptly" in text
    assert "emergency services" in text
    assert "diagnos" not in text
