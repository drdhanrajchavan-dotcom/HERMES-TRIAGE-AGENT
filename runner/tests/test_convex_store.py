import json

import httpx

from clinic_agency.adapters.convex import ConvexCaseStore
from clinic_agency.domain.cases import Case
from clinic_agency.orchestration.planner import ManagerPlanner
from clinic_agency.safety.outbound import ComplianceReview, OutboundDraft, OutboundGate


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
    store = ConvexCaseStore(
        "https://example.convex.cloud",
        internal_api_secret="internal-secret",
        client=client,
    )

    created = store.add(sample_case())

    assert created is True
    assert captured["path"] == "cases:ingestTelegram"
    assert captured["format"] == "json"
    assert captured["args"]["externalEventId"] == "telegram:101"
    assert captured["args"]["patientExternalId"] == "telegram:99"
    assert captured["args"]["mustEscalate"] is False
    assert captured["args"]["internalApiSecret"] == "internal-secret"


def test_convex_case_store_reports_duplicate() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "success", "value": {"caseId": "case-1", "duplicate": True}},
        )

    store = ConvexCaseStore(
        "https://example.convex.cloud",
        internal_api_secret="internal-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert store.add(sample_case()) is False


def test_convex_case_store_records_approved_delivery() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "success", "value": {"recorded": True}})

    store = ConvexCaseStore(
        "https://example.convex.cloud",
        internal_api_secret="internal-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    draft = OutboundDraft.create("case-1", "Would you like available slots?")
    review = ComplianceReview.pass_draft(draft)
    outbound = OutboundGate.authorize(draft, review)

    store.record_delivery(
        external_event_id="telegram:101",
        outbound=outbound,
        review=review,
        external_message_id="42",
    )

    assert captured["path"] == "cases:recordApprovedDelivery"
    assert captured["args"]["externalEventId"] == "telegram:101"
    assert captured["args"]["draftHash"] == draft.draft_hash
    assert captured["args"]["reviewDraftHash"] == draft.draft_hash
    assert captured["args"]["externalMessageId"] == "42"


def test_convex_case_store_records_manager_plan() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "success", "value": {"recorded": True}})

    store = ConvexCaseStore(
        "https://example.convex.cloud",
        internal_api_secret="internal-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    case = sample_case()
    plan = ManagerPlanner().plan(case)

    store.record_plan(case.external_event_id, plan)

    assert captured["path"] == "cases:recordPlan"
    assert captured["args"]["externalEventId"] == "telegram:101"
    assert [step["key"] for step in captured["args"]["steps"]] == [
        "triage",
        "knowledge",
        "draft",
        "compliance",
    ]
