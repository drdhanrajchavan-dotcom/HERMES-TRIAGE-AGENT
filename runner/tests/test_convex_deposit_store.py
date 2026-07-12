import httpx

from clinic_agency.payments.convex import ConvexDepositStore
from clinic_agency.payments.dodo import DepositCheckout, DepositCheckoutRequest


def test_convex_deposit_store_persists_pending_before_created() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.read().decode())
        return httpx.Response(200, json={"status": "success", "value": {"recorded": True}})

    store = ConvexDepositStore(
        "https://example.convex.cloud",
        internal_api_secret="internal",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    request = DepositCheckoutRequest("telegram:101", "hold_123", "pdt_deposit")

    store.create_intent(request)
    store.mark_created(
        request,
        DepositCheckout("cks_123", "https://test.checkout.dodopayments.com/cks_123"),
    )

    assert '"path":"payments:createDepositIntent"' in calls[0]
    assert '"holdKey":"hold_123"' in calls[0]
    assert '"path":"payments:markCheckoutCreated"' in calls[1]
    assert '"checkoutSessionId":"cks_123"' in calls[1]
