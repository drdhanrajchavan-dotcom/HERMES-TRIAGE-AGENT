from secrets import compare_digest
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Response, status

from clinic_agency.adapters.case_store import InMemoryCaseStore
from clinic_agency.adapters.telegram import extract_update
from clinic_agency.domain.cases import Case
from clinic_agency.safety.red_flags import classify_red_flags


def create_app(telegram_webhook_secret: str = "") -> FastAPI:
    application = FastAPI(title="Clinic Agency Runner")
    application.state.case_store = InMemoryCaseStore()

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
        response.status_code = status.HTTP_202_ACCEPTED
        return {
            "status": "accepted",
            "update_id": update.update_id,
            "must_escalate": safety.must_escalate,
        }

    return application


app = create_app()
