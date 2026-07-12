import json
from datetime import UTC, datetime, timedelta

import httpx

from clinic_agency.calendar.convex import ConvexHoldStore
from clinic_agency.calendar.service import StoredHold
from clinic_agency.config import Settings


def sample_hold():
    start = datetime(2026, 7, 13, 4, 30, tzinfo=UTC)
    return StoredHold(
        "case:slot",
        "case",
        "habc",
        start,
        start + timedelta(minutes=30),
        start + timedelta(minutes=10),
    )


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


def test_convex_hold_store_round_trips_business_state():
    hold = sample_hold()
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if request.url.path.endswith("/query"):
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "value": {
                        "holdKey": hold.hold_key,
                        "caseExternalId": hold.case_id,
                        "calendarEventId": hold.event_id,
                        "startAt": hold.start.timestamp() * 1000,
                        "endAt": hold.end.timestamp() * 1000,
                        "expiresAt": hold.expires_at.timestamp() * 1000,
                        "status": "tentative",
                    },
                },
            )
        return httpx.Response(200, json={"status": "success", "value": {"recorded": True}})

    store = ConvexHoldStore(
        "https://example.convex.cloud",
        internal_api_secret="internal",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    store.save(hold)
    loaded = store.get(hold.hold_key)
    store.mark_released(hold.hold_key, hold.end)

    assert loaded == hold
    assert calls[0]["path"] == "calendarHolds:save"
    assert calls[0]["args"]["internalApiSecret"] == "internal"
    assert calls[1]["path"] == "calendarHolds:get"
    assert calls[2]["path"] == "calendarHolds:release"


def test_convex_store_queries_expired_holds():
    hold = sample_hold()

    def handler(request):
        return httpx.Response(
            200,
            json={
                "status": "success",
                "value": [
                    {
                        "holdKey": hold.hold_key,
                        "caseExternalId": hold.case_id,
                        "calendarEventId": hold.event_id,
                        "startAt": hold.start.timestamp() * 1000,
                        "endAt": hold.end.timestamp() * 1000,
                        "expiresAt": hold.expires_at.timestamp() * 1000,
                        "status": "tentative",
                    }
                ],
            },
        )

    store = ConvexHoldStore(
        "https://example.convex.cloud",
        internal_api_secret="internal",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert store.expired(hold.end) == [hold]
