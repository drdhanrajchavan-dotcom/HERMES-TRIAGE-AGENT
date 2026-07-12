from dataclasses import dataclass
from typing import Protocol

from langfuse import get_client, observe

from clinic_agency.adapters.telegram_sender import DeliveryResult
from clinic_agency.domain.cases import Case
from clinic_agency.safety.compliance import review_draft
from clinic_agency.safety.outbound import (
    AuthorizedOutbound,
    ComplianceReview,
    OutboundDraft,
    OutboundGate,
)

ROUTINE_ACKNOWLEDGEMENT = (
    "Thank you. We received your message and are reviewing it. "
    "We'll reply with the relevant information shortly."
)
RED_FLAG_ACKNOWLEDGEMENT = (
    "Thank you for telling us. A clinic team member needs to review this promptly. "
    "If you feel seriously unwell or have difficulty breathing, "
    "contact local emergency services now."
)


class OutboundSender(Protocol):
    def send(self, chat_id: int, outbound: AuthorizedOutbound) -> DeliveryResult: ...


class DeliveryRecorder(Protocol):
    def record_delivery(
        self,
        *,
        external_event_id: str,
        outbound: AuthorizedOutbound,
        review: ComplianceReview,
        external_message_id: str,
    ) -> None: ...


@dataclass(frozen=True)
class WorkflowResult:
    sent: bool
    external_message_id: str
    draft_hash: str


class SafeAcknowledgementWorkflow:
    def __init__(self, *, sender: OutboundSender, recorder: DeliveryRecorder) -> None:
        self._sender = sender
        self._recorder = recorder

    @observe(name="workflow.safe_acknowledgement", as_type="chain", capture_input=False)
    def handle(self, case: Case, chat_id: int) -> WorkflowResult:
        metadata = {
            "case_id": case.external_event_id,
            "role": "Communications",
            "task_type": "acknowledgement",
        }
        get_client().update_current_trace(
            session_id=case.external_event_id,
            metadata=metadata,
            tags=["communications", "acknowledgement"],
        )
        get_client().update_current_span(metadata=metadata)
        text = RED_FLAG_ACKNOWLEDGEMENT if case.must_escalate else ROUTINE_ACKNOWLEDGEMENT
        draft = OutboundDraft.create(case.external_event_id, text)
        review = review_draft(draft)
        outbound = OutboundGate.authorize(draft, review)
        delivery = self._sender.send(chat_id, outbound)
        self._recorder.record_delivery(
            external_event_id=case.external_event_id,
            outbound=outbound,
            review=review,
            external_message_id=delivery.external_message_id,
        )
        return WorkflowResult(
            sent=True,
            external_message_id=delivery.external_message_id,
            draft_hash=outbound.draft_hash,
        )
