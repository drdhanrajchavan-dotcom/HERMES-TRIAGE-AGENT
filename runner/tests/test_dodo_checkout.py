from types import SimpleNamespace

import pytest

from clinic_agency.payments.dodo import (
    DepositCheckoutCoordinator,
    DepositCheckoutRequest,
    DodoCheckoutGateway,
    UncertainCheckoutError,
)


class CheckoutSessions:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class IntentStore:
    def __init__(self) -> None:
        self.events = []

    def create_intent(self, request):
        self.events.append(("pending", request.hold_id))

    def mark_created(self, request, checkout):
        self.events.append(("created", checkout.session_id))

    def mark_uncertain(self, request):
        self.events.append(("uncertain", request.hold_id))


def test_creates_case_linked_deposit_checkout() -> None:
    sessions = CheckoutSessions(
        SimpleNamespace(
            session_id="chk_123",
            checkout_url="https://checkout.dodopayments.com/session/chk_123",
        )
    )
    gateway = DodoCheckoutGateway(sessions)
    request = DepositCheckoutRequest(
        case_id="telegram:101",
        hold_id="hold_123",
        product_id="pdt_deposit",
        return_url="https://clinic.example/booking/return",
    )

    result = gateway.create(request)

    assert result.session_id == "chk_123"
    assert result.checkout_url.startswith("https://checkout.dodopayments.com/")
    assert sessions.calls == [
        {
            "product_cart": [{"product_id": "pdt_deposit", "quantity": 1}],
            "return_url": "https://clinic.example/booking/return",
            "metadata": {
                "case_id": "telegram:101",
                "appointment_hold_id": "hold_123",
            },
        }
    ]


def test_timeout_is_uncertain_and_must_not_be_blindly_retried() -> None:
    sessions = CheckoutSessions(error=TimeoutError("response lost"))
    gateway = DodoCheckoutGateway(sessions)
    request = DepositCheckoutRequest(
        case_id="telegram:101",
        hold_id="hold_123",
        product_id="pdt_deposit",
    )

    with pytest.raises(UncertainCheckoutError, match="reconcile"):
        gateway.create(request)

    assert len(sessions.calls) == 1


def test_coordinator_persists_intent_before_external_checkout() -> None:
    sessions = CheckoutSessions(
        SimpleNamespace(
            session_id="chk_123", checkout_url="https://checkout.test/chk_123"
        )
    )
    intents = IntentStore()
    request = DepositCheckoutRequest("telegram:101", "hold_123", "pdt_deposit")

    result = DepositCheckoutCoordinator(
        intents, DodoCheckoutGateway(sessions)
    ).create(request)

    assert result.session_id == "chk_123"
    assert intents.events == [("pending", "hold_123"), ("created", "chk_123")]


def test_coordinator_marks_timeout_uncertain() -> None:
    intents = IntentStore()
    request = DepositCheckoutRequest("telegram:101", "hold_123", "pdt_deposit")

    with pytest.raises(UncertainCheckoutError):
        DepositCheckoutCoordinator(
            intents,
            DodoCheckoutGateway(CheckoutSessions(error=TimeoutError("lost"))),
        ).create(request)

    assert intents.events == [("pending", "hold_123"), ("uncertain", "hold_123")]
