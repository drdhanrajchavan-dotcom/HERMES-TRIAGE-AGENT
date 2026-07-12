import json
from datetime import UTC, datetime, timedelta

import httpx

from clinic_agency.calendar.convex import ConvexHoldStore
from clinic_agency.calendar.service import StoredHold
from clinic_agency.config import Settings


def sample_hold(status="creating"):
    start = datetime(2026, 7, 13, 4, 30, tzinfo=UTC)
    return StoredHold(
        "case:slot", "case", "habc", start, start + timedelta(minutes=30), start, status
    )


def encoded(hold):
    return {
        "holdKey": hold.hold_key,
        "caseExternalId": hold.case_id,
        "calendarEventId": hold.event_id,
        "startAt": hold.start.timestamp() * 1000,
        "endAt": hold.end.timestamp() * 1000,
        "expiresAt": hold.expires_at.timestamp() * 1000,
        "status": hold.status,
    }


def test_calendar_configuration_is_explicit_and_keyless():
    settings = Settings(
        google_calendar_id="clinic@example.com",
        google_calendar_timezone="Asia/Kolkata",
        google_calendar_hold_minutes=12,
        _env_file=None,
    )
    assert settings.google_calendar_id == "clinic@example.com"
    assert settings.google_calendar_timezone == "Asia/Kolkata"
    assert settings.google_calendar_hold_minutes == 12
    assert not hasattr(settings, "google_service_account_key")
    assert not hasattr(settings, "google_credentials_json")


def test_convex_hold_store_uses_atomic_claim_and_durable_transitions():
    creating, active = sample_hold(), sample_hold("active")
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        path = payload["path"]
        if path.endswith(":claim"):
            value = {"outcome": "claimed", "hold": encoded(creating)}
        elif path.endswith(":activate"):
            value = {"hold": encoded(active)}
        elif path.endswith(":claimRelease"):
            value = {"hold": encoded(sample_hold("releasing"))}
        else:
            value = {"recorded": True}
        return httpx.Response(200, json={"status": "success", "value": value})

    store = ConvexHoldStore(
        "https://example.convex.cloud",
        internal_api_secret="internal",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert store.claim(creating) == creating
    assert store.activate(creating.hold_key) == active
    assert store.claim_release(creating.hold_key, creating.end).status == "releasing"
    store.finalize_release(creating.hold_key, creating.end)
    assert [call["path"] for call in calls] == [
        "calendarHolds:claim",
        "calendarHolds:activate",
        "calendarHolds:claimRelease",
        "calendarHolds:finalizeRelease",
    ]
    assert all(call["args"]["internalApiSecret"] == "internal" for call in calls)


def test_convex_store_queries_expired_holds_with_bounded_limit():
    hold = sample_hold("active")
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"status": "success", "value": [encoded(hold)]})

    store = ConvexHoldStore(
        "https://example.convex.cloud",
        internal_api_secret="internal",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert store.expired(hold.end, limit=25) == [hold]
    assert captured["args"]["limit"] == 25
