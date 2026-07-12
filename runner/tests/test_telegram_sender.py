import json

import httpx

from clinic_agency.adapters.telegram_sender import TelegramSender
from clinic_agency.safety.outbound import ComplianceReview, OutboundDraft, OutboundGate


def test_telegram_sender_sends_only_authorized_outbound() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 42}},
        )

    draft = OutboundDraft.create(case_id="case-1", text="Would you like available slots?")
    authorized = OutboundGate.authorize(draft, ComplianceReview.pass_draft(draft))
    sender = TelegramSender(
        bot_token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = sender.send(chat_id=99, outbound=authorized)

    assert result.external_message_id == "42"
    assert result.draft_hash == draft.draft_hash
    assert captured == {"chat_id": 99, "text": draft.text}
