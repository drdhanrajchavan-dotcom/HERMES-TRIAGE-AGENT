from dataclasses import dataclass

import httpx

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

    def send(self, chat_id: int, outbound: AuthorizedOutbound) -> DeliveryResult:
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
