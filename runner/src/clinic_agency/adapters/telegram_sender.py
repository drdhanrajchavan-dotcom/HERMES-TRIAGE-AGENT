from dataclasses import dataclass

import httpx
from langfuse import get_client, observe

from clinic_agency.safety.outbound import AuthorizedOutbound


@dataclass(frozen=True)
class DeliveryResult:
    external_message_id: str
    draft_hash: str


class TelegramSender:
    def __init__(
        self,
        bot_token: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @observe(name="tool.telegram.send", as_type="tool", capture_input=False)
    def send(self, chat_id: int, outbound: AuthorizedOutbound) -> DeliveryResult:
        get_client().update_current_span(
            metadata={
                "case_id": outbound.case_id,
                "role": "Communications",
                "task_type": "telegram.send",
            }
        )
        response = self._client.post(
            self._url,
            json={"chat_id": chat_id, "text": outbound.text},
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError("Telegram rejected outbound message")
        return DeliveryResult(
            external_message_id=str(payload["result"]["message_id"]),
            draft_hash=outbound.draft_hash,
        )
