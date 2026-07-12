import json

import httpx

from clinic_agency.adapters.convex import ConvexCaseStore
from clinic_agency.domain.cases import Case


def sample_case() -> Case:
    return Case.from_telegram(101, 99, "How much is laser treatment?")


def test_convex_case_store_sends_canonical_mutation() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"status": "success", "value": {"caseId": "case-1", "duplicate": False}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = ConvexCaseStore("https://example.convex.cloud", client=client)

    created = store.add(sample_case())

    assert created is True
    assert captured["path"] == "cases:ingestTelegram"
    assert captured["format"] == "json"
    assert captured["args"]["externalEventId"] == "telegram:101"
    assert captured["args"]["patientExternalId"] == "telegram:99"
    assert captured["args"]["mustEscalate"] is False


def test_convex_case_store_reports_duplicate() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "success", "value": {"caseId": "case-1", "duplicate": True}},
        )

    store = ConvexCaseStore(
        "https://example.convex.cloud",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert store.add(sample_case()) is False
