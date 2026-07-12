from typing import Any

import httpx
from langfuse import observe

from clinic_agency.payments.dodo import DepositCheckout, DepositCheckoutRequest
from clinic_agency.telemetry import current_trace_id


class ConvexDepositStore:
    def __init__(
        self,
        convex_url: str,
        *,
        internal_api_secret: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self._url = f"{convex_url.rstrip('/')}/api/mutation"
        self._secret = internal_api_secret
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def create_intent(self, request: DepositCheckoutRequest) -> None:
        self._mutate(
            "payments:createDepositIntent",
            {
                "internalApiSecret": self._secret,
                "externalEventId": request.case_id,
                "holdKey": request.hold_id,
                "productId": request.product_id,
                "langfuseTraceId": current_trace_id(),
            },
        )

    def mark_created(
        self, request: DepositCheckoutRequest, checkout: DepositCheckout
    ) -> None:
        self._mutate(
            "payments:markCheckoutCreated",
            {
                "internalApiSecret": self._secret,
                "holdKey": request.hold_id,
                "checkoutSessionId": checkout.session_id,
                "checkoutUrl": checkout.checkout_url,
                "langfuseTraceId": current_trace_id(),
            },
        )

    def mark_uncertain(self, request: DepositCheckoutRequest) -> None:
        self._mutate(
            "payments:markCheckoutUncertain",
            {
                "internalApiSecret": self._secret,
                "holdKey": request.hold_id,
                "langfuseTraceId": current_trace_id(),
            },
        )

    @observe(
        name="tool.convex.deposit_mutation",
        as_type="tool",
        capture_input=False,
        capture_output=False,
    )
    def _mutate(self, path: str, args: dict[str, Any]) -> None:
        response = self._client.post(
            self._url,
            json={"path": path, "args": args, "format": "json"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(f"Convex deposit mutation failed: {payload.get('errorMessage')}")
