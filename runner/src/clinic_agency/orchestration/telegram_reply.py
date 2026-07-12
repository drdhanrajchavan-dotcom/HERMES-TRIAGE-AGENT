from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from langfuse import get_client, observe
from pydantic import BaseModel, Field

from clinic_agency.calendar.service import HoldRequest
from clinic_agency.domain.cases import Case
from clinic_agency.domain.roles import RoleConfig
from clinic_agency.knowledge.service import GroundedKnowledgeService
from clinic_agency.orchestration.acknowledgement import (
    RED_FLAG_ACKNOWLEDGEMENT,
    ROUTINE_ACKNOWLEDGEMENT,
    DeliveryRecorder,
    OutboundSender,
    WorkflowResult,
)
from clinic_agency.orchestration.openai_model import ServerTool, ServerToolRegistry
from clinic_agency.orchestration.role_runner import RoleRunner, RoleTask
from clinic_agency.safety.compliance import review_draft
from clinic_agency.safety.outbound import OutboundDraft, OutboundGate


class TelegramReplyOutput(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    requested_tools: tuple[str, ...] = ()


class CalendarTools(Protocol):
    def availability(self, start: datetime, end: datetime) -> Any: ...

    def create_hold(self, request: HoldRequest) -> Any: ...


def _instant(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def calendar_tool_registry(calendar: CalendarTools) -> ServerToolRegistry:
    """Build the only calendar functions that a hosted model may invoke."""

    def read(arguments: dict[str, Any]) -> dict[str, Any]:
        result = calendar.availability(
            _instant(arguments.get("start"), "start"),
            _instant(arguments.get("end"), "end"),
        )
        return {
            "available": result.available,
            "busy": [[start.isoformat(), end.isoformat()] for start, end in result.busy],
        }

    def hold(arguments: dict[str, Any]) -> dict[str, Any]:
        result = calendar.create_hold(
            HoldRequest(
                hold_key=str(arguments.get("hold_key", "")),
                case_id=str(arguments.get("case_id", "")),
                start=_instant(arguments.get("start"), "start"),
                end=_instant(arguments.get("end"), "end"),
            )
        )
        return {
            "hold_key": result.hold_key,
            "event_id": result.event_id,
            "status": result.status,
            "start": result.start.isoformat(),
            "end": result.end.isoformat(),
            "expires_at": result.expires_at.isoformat(),
        }

    window = {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "Timezone-aware ISO-8601 timestamp"},
            "end": {"type": "string", "description": "Timezone-aware ISO-8601 timestamp"},
        },
        "required": ["start", "end"],
        "additionalProperties": False,
    }
    hold_parameters = {
        "type": "object",
        "properties": {
            "hold_key": {"type": "string", "minLength": 1, "maxLength": 128},
            "case_id": {"type": "string", "minLength": 1, "maxLength": 128},
            **window["properties"],
        },
        "required": ["hold_key", "case_id", "start", "end"],
        "additionalProperties": False,
    }
    return ServerToolRegistry(
        {
            "calendar.read": ServerTool(
                "Check clinic calendar availability for a time window.", window, read
            ),
            "calendar.hold": ServerTool(
                "Create a short-lived tentative appointment hold.", hold_parameters, hold
            ),
        }
    )


@dataclass
class IntelligentTelegramReplyWorkflow:
    sender: OutboundSender
    recorder: DeliveryRecorder
    role_runner: RoleRunner
    role: RoleConfig
    knowledge: GroundedKnowledgeService

    @observe(
        name="workflow.intelligent_telegram_reply",
        as_type="chain",
        capture_input=False,
        capture_output=False,
    )
    def handle(self, case: Case, chat_id: int) -> WorkflowResult:
        metadata = {
            "case_id": case.external_event_id,
            "role": "Communications",
            "task_type": "telegram_reply",
        }
        get_client().update_current_span(metadata=metadata)

        # Safety classification is performed before this workflow. It has absolute authority:
        # no model or retrieval call can suppress or rewrite an urgent response.
        if case.must_escalate:
            text = RED_FLAG_ACKNOWLEDGEMENT
        else:
            evidence = self.knowledge.gather(case.message, ())
            result = self.role_runner.run(
                self.role,
                RoleTask(
                    case_id=case.external_event_id,
                    task_type="telegram_reply",
                    input={
                        "message": case.message,
                        "evidence": [
                            {
                                "source_id": item.source_id,
                                "title": item.title,
                                "excerpt": item.excerpt,
                                "url": item.url,
                            }
                            for item in evidence
                        ],
                    },
                ),
            )
            text = TelegramReplyOutput.model_validate(result.output).text
            candidate = OutboundDraft.create(case.external_event_id, text)
            if review_draft(candidate).verdict != "pass":
                text = ROUTINE_ACKNOWLEDGEMENT
                get_client().update_current_span(metadata={**metadata, "compliance_bounced": True})

        # Deterministic review and exact reviewed-draft hash authorization are always last.
        draft = OutboundDraft.create(case.external_event_id, text)
        review = review_draft(draft)
        outbound = OutboundGate.authorize(draft, review)
        delivery = self.sender.send(chat_id, outbound)
        self.recorder.record_delivery(
            external_event_id=case.external_event_id,
            outbound=outbound,
            review=review,
            external_message_id=delivery.external_message_id,
        )
        return WorkflowResult(True, delivery.external_message_id, outbound.draft_hash)
