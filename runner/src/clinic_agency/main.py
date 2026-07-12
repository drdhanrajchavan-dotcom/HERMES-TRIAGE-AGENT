from contextlib import asynccontextmanager
from datetime import datetime
from secrets import compare_digest
from typing import Annotated, Any, Protocol

from fastapi import FastAPI, Header, HTTPException, Response, status
from langfuse import get_client, observe
from pydantic import BaseModel, Field

from clinic_agency.adapters.case_store import InMemoryCaseStore
from clinic_agency.adapters.convex import ConvexCaseStore
from clinic_agency.adapters.telegram import extract_update
from clinic_agency.adapters.telegram_sender import TelegramSender
from clinic_agency.calendar.convex import ConvexHoldStore
from clinic_agency.calendar.google import GoogleCalendarClient
from clinic_agency.calendar.service import CalendarService
from clinic_agency.calendar.service import HoldRequest as CalendarHoldRequest
from clinic_agency.config import Settings
from clinic_agency.domain.cases import Case
from clinic_agency.knowledge.linkup import LinkupSearchClient
from clinic_agency.knowledge.responder import CitedKnowledgeResponder
from clinic_agency.knowledge.service import GroundedKnowledgeService
from clinic_agency.orchestration.acknowledgement import (
    SafeAcknowledgementWorkflow,
    WorkflowResult,
)
from clinic_agency.orchestration.planner import CasePlan, ManagerPlanner
from clinic_agency.safety.red_flags import classify_red_flags


class CaseStore(Protocol):
    def add(self, case: Case) -> bool: ...


class OutboundWorkflow(Protocol):
    def handle(self, case: Case, chat_id: int) -> WorkflowResult: ...


class PlanRecorder(Protocol):
    def record_plan(self, external_event_id: str, plan: CasePlan) -> None: ...


class CalendarWindowRequest(BaseModel):
    start: datetime
    end: datetime


class CalendarCreateHoldRequest(CalendarWindowRequest):
    hold_key: str = Field(min_length=1, max_length=128)
    case_id: str = Field(min_length=1, max_length=128)


class CalendarExpiryRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=100)


def create_app(
    telegram_webhook_secret: str = "",
    case_store: CaseStore | None = None,
    outbound_workflow: OutboundWorkflow | None = None,
    plan_recorder: PlanRecorder | None = None,
    verify_langfuse: bool = False,
    webhook_shared_secret: str = "",
    calendar_service: CalendarService | object | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if verify_langfuse and not get_client().auth_check():
            raise RuntimeError("Langfuse authentication failed")
        yield
        if verify_langfuse:
            get_client().flush()

    application = FastAPI(title="Clinic Agency Runner", lifespan=lifespan)
    application.state.case_store = case_store or InMemoryCaseStore()
    application.state.calendar_service = calendar_service

    def require_edge(edge_secret: str | None) -> None:
        if not webhook_shared_secret:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not edge_secret or not compare_digest(edge_secret, webhook_shared_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    def calendar() -> Any:
        service = application.state.calendar_service
        if service is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return service

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"service": "clinic-agency-runner", "status": "ready"}

    @application.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "clinic-agency-runner",
            "status": "ready",
            "interface": "api",
            "health": "/health",
        }

    @application.post("/internal/calendar/availability")
    def calendar_availability(
        payload: CalendarWindowRequest,
        edge_secret: Annotated[str | None, Header(alias="X-Clinic-Edge-Secret")] = None,
    ) -> dict[str, Any]:
        require_edge(edge_secret)
        result = calendar().availability(payload.start, payload.end)
        return {"available": result.available, "busy": result.busy}

    @application.post("/internal/calendar/holds")
    def calendar_create_hold(
        payload: CalendarCreateHoldRequest,
        edge_secret: Annotated[str | None, Header(alias="X-Clinic-Edge-Secret")] = None,
    ) -> dict[str, Any]:
        require_edge(edge_secret)
        hold = calendar().create_hold(
            CalendarHoldRequest(payload.hold_key, payload.case_id, payload.start, payload.end)
        )
        return {
            "hold_key": hold.hold_key,
            "event_id": hold.event_id,
            "status": hold.status,
            "start": hold.start,
            "end": hold.end,
            "expires_at": hold.expires_at,
        }

    @application.post("/internal/calendar/holds/{hold_key}/release")
    def calendar_release_hold(
        hold_key: str,
        edge_secret: Annotated[str | None, Header(alias="X-Clinic-Edge-Secret")] = None,
    ) -> dict[str, bool]:
        require_edge(edge_secret)
        return {"released": calendar().release(hold_key)}

    @application.post("/internal/calendar/expire")
    def calendar_expire_holds(
        payload: CalendarExpiryRequest,
        edge_secret: Annotated[str | None, Header(alias="X-Clinic-Edge-Secret")] = None,
    ) -> dict[str, list[str]]:
        require_edge(edge_secret)
        return {"expired_hold_keys": calendar().expire_due(limit=payload.limit)}

    @application.post("/webhooks/telegram")
    @observe(
        name="case.telegram",
        as_type="chain",
        capture_input=False,
        capture_output=False,
    )
    def telegram_webhook(
        payload: dict[str, Any],
        response: Response,
        secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
        edge_secret: Annotated[str | None, Header(alias="X-Clinic-Edge-Secret")] = None,
    ) -> dict[str, str | int | bool]:
        if webhook_shared_secret and (
            not edge_secret or not compare_digest(edge_secret, webhook_shared_secret)
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        if not secret or not compare_digest(secret, telegram_webhook_secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        update = extract_update(payload)
        safety = classify_red_flags(update.message.text)
        case = Case.from_telegram(
            update.update_id,
            update.message.chat.id,
            update.message.text,
            safety.matched_terms,
        )
        get_client().update_current_trace(
            session_id=case.external_event_id,
            metadata={
                "case_id": case.external_event_id,
                "role": "Manager",
                "task_type": "telegram_case",
            },
            tags=["telegram", "red_flag" if case.must_escalate else "routine"],
        )
        get_client().update_current_span(
            input={
                "case_id": case.external_event_id,
                "channel": case.channel,
                "must_escalate": case.must_escalate,
            }
        )
        if not application.state.case_store.add(case):
            return {"status": "duplicate", "update_id": update.update_id}
        if plan_recorder:
            plan_recorder.record_plan(case.external_event_id, ManagerPlanner().plan(case))
        outbound_sent = False
        if outbound_workflow:
            outbound_sent = outbound_workflow.handle(case, update.message.chat.id).sent
        response.status_code = status.HTTP_202_ACCEPTED
        return {
            "status": "accepted",
            "update_id": update.update_id,
            "must_escalate": safety.must_escalate,
            "outbound_sent": outbound_sent,
        }

    return application


def configured_app(settings: Settings | None = None) -> FastAPI:
    current = settings or Settings()
    if current.app_env in {"staging", "production"}:
        required = {
            "CONVEX_URL": current.convex_url,
            "INTERNAL_API_SECRET": current.internal_api_secret,
            "LANGFUSE_PUBLIC_KEY": current.langfuse_public_key,
            "LANGFUSE_SECRET_KEY": current.langfuse_secret_key,
            "LANGFUSE_HOST": current.langfuse_host,
            "TELEGRAM_BOT_TOKEN": current.telegram_bot_token,
            "TELEGRAM_WEBHOOK_SECRET": current.telegram_webhook_secret,
            "WEBHOOK_SHARED_SECRET": current.webhook_shared_secret,
            "LINKUP_API_KEY": current.linkup_api_key,
            "GOOGLE_CALENDAR_ID": current.google_calendar_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing required production configuration: {', '.join(missing)}")
    store: CaseStore = (
        ConvexCaseStore(
            current.convex_url,
            internal_api_secret=current.internal_api_secret,
        )
        if current.convex_url
        else InMemoryCaseStore()
    )
    workflow = None
    if isinstance(store, ConvexCaseStore) and current.telegram_bot_token:
        knowledge_responder = (
            CitedKnowledgeResponder(
                GroundedKnowledgeService(LinkupSearchClient(current.linkup_api_key))
            )
            if current.linkup_api_key
            else None
        )
        workflow = SafeAcknowledgementWorkflow(
            sender=TelegramSender(current.telegram_bot_token),
            recorder=store,
            knowledge_responder=knowledge_responder,
        )
    plan_recorder = store if isinstance(store, ConvexCaseStore) else None
    calendar_service = None
    if isinstance(store, ConvexCaseStore) and current.google_calendar_id:
        calendar_service = CalendarService(
            GoogleCalendarClient(current.google_calendar_id),
            ConvexHoldStore(
                current.convex_url,
                internal_api_secret=current.internal_api_secret,
            ),
            hold_minutes=current.google_calendar_hold_minutes,
        )
    return create_app(
        current.telegram_webhook_secret,
        store,
        workflow,
        plan_recorder,
        verify_langfuse=bool(current.langfuse_public_key and current.langfuse_secret_key),
        webhook_shared_secret=current.webhook_shared_secret,
        calendar_service=calendar_service,
    )


app = configured_app()
