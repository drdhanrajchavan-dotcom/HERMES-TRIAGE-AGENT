from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from dodopayments import APITimeoutError
from langfuse import get_client, observe


class CheckoutSessions(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class DepositIntentStore(Protocol):
    def create_intent(self, request: "DepositCheckoutRequest") -> None: ...

    def mark_created(
        self, request: "DepositCheckoutRequest", checkout: "DepositCheckout"
    ) -> None: ...

    def mark_uncertain(self, request: "DepositCheckoutRequest") -> None: ...


@dataclass(frozen=True)
class DepositCheckoutRequest:
    case_id: str
    hold_id: str
    product_id: str
    return_url: str | None = None

    def __post_init__(self) -> None:
        if not self.case_id or not self.hold_id or not self.product_id:
            raise ValueError("case, hold, and product IDs are required")
        if self.return_url and urlparse(self.return_url).scheme != "https":
            raise ValueError("return URL must use HTTPS")


@dataclass(frozen=True)
class DepositCheckout:
    session_id: str
    checkout_url: str


class UncertainCheckoutError(RuntimeError):
    pass


class DepositCheckoutCoordinator:
    def __init__(
        self, intent_store: DepositIntentStore, gateway: "DodoCheckoutGateway"
    ) -> None:
        self._intent_store = intent_store
        self._gateway = gateway

    @observe(
        name="booking.deposit_checkout",
        as_type="chain",
        capture_input=False,
        capture_output=False,
    )
    def create(self, request: DepositCheckoutRequest) -> DepositCheckout:
        get_client().update_current_span(
            input={"case_id": request.case_id, "hold_id": request.hold_id},
            metadata={
                "case_id": request.case_id,
                "role": "Booking",
                "task_type": "deposit_checkout",
            },
        )
        self._intent_store.create_intent(request)
        try:
            checkout = self._gateway.create(request)
        except UncertainCheckoutError:
            self._intent_store.mark_uncertain(request)
            raise
        self._intent_store.mark_created(request, checkout)
        get_client().update_current_span(output={"status": "checkout_created"})
        return checkout


class DodoCheckoutGateway:
    def __init__(self, checkout_sessions: CheckoutSessions) -> None:
        self._checkout_sessions = checkout_sessions

    @observe(
        name="tool.dodo.checkout.create",
        as_type="tool",
        capture_input=False,
        capture_output=False,
    )
    def create(self, request: DepositCheckoutRequest) -> DepositCheckout:
        metadata = {
            "case_id": request.case_id,
            "role": "Booking",
            "task_type": "deposit_checkout",
        }
        langfuse = get_client()
        langfuse.update_current_span(
            input={
                "case_id": request.case_id,
                "hold_id": request.hold_id,
                "product_id": request.product_id,
            },
            metadata=metadata,
        )
        payload: dict[str, Any] = {
            "product_cart": [{"product_id": request.product_id, "quantity": 1}],
            "metadata": {
                "case_id": request.case_id,
                "appointment_hold_id": request.hold_id,
            },
        }
        if request.return_url:
            payload["return_url"] = request.return_url
        try:
            response = self._checkout_sessions.create(**payload)
        except (APITimeoutError, TimeoutError) as exc:
            langfuse.update_current_span(
                level="ERROR",
                status_message="Checkout outcome uncertain after timeout",
            )
            raise UncertainCheckoutError(
                "Dodo checkout outcome is uncertain; reconcile before retrying"
            ) from exc
        result = DepositCheckout(
            session_id=response.session_id,
            checkout_url=response.checkout_url,
        )
        if not result.session_id or urlparse(result.checkout_url).scheme != "https":
            raise RuntimeError("Dodo returned an invalid checkout session")
        langfuse.update_current_span(
            output={"status": "created", "session_id": result.session_id}
        )
        return result
