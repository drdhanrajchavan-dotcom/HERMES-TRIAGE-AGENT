from secrets import compare_digest
from typing import Annotated, Any, Protocol

from fastapi import FastAPI, Header, HTTPException, Response, status

from clinic_agency.adapters.case_store import InMemoryCaseStore
from clinic_agency.adapters.convex import ConvexCaseStore
from clinic_agency.adapters.telegram import extract_update
from clinic_agency.adapters.telegram_sender import TelegramSender
from clinic_agency.config import Settings
from clinic_agency.domain.cases import Case
from clinic_agency.orchestration.acknowledgement import (
    SafeAcknowledgementWorkflow,
    WorkflowResult,
)
from clinic_agency.safety.red_flags import classify_red_flags


class CaseStore(Protocol):
    def add(self, case: Case) -> bool: ...


class OutboundWorkflow(Protocol):
    def handle(self, case: Case, chat_id: int) -> WorkflowResult: ...


def create_app(
    telegram_webhook_secret: str = "",
    case_store: CaseStore | None = None,
    outbound_workflow: OutboundWorkflow | None = None,
) -> FastAPI:
    application = FastAPI(title="Clinic Agency Runner")
    application.state.case_store = case_store or InMemoryCaseStore()

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"service": "clinic-agency-runner", "status": "ready"}

    @application.post("/webhooks/telegram")
    def telegram_webhook(
        payload: dict[str, Any],
        response: Response,
        secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
    ) -> dict[str, str | int | bool]:
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
        if not application.state.case_store.add(case):
            return {"status": "duplicate", "update_id": update.update_id}
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
    if current.app_env in {"staging", "production"} and (
        not current.convex_url or not current.internal_api_secret
    ):
        raise RuntimeError(
            "CONVEX_URL and INTERNAL_API_SECRET are required outside development and test"
        )
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
        workflow = SafeAcknowledgementWorkflow(
            sender=TelegramSender(current.telegram_bot_token),
            recorder=store,
        )
    return create_app(current.telegram_webhook_secret, store, workflow)


app = configured_app()
