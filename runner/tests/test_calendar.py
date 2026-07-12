from datetime import UTC, datetime, timedelta

import httpx
import pytest

from clinic_agency.calendar.google import GoogleCalendarClient
from clinic_agency.calendar.service import (
    CalendarConflict,
    CalendarService,
    HoldRequest,
    StoredHold,
)
from clinic_agency.main import create_app

START = datetime(2026, 7, 13, 4, 30, tzinfo=UTC)
END = START + timedelta(minutes=30)


def test_calendar_service_can_be_exposed_to_the_runner_tool_boundary():
    service = object()

    app = create_app(telegram_webhook_secret="secret", calendar_service=service)

    assert app.state.calendar_service is service


class FakeCalendar:
    def __init__(self, busy=()):
        self.busy = list(busy)
        self.created = []
        self.deleted = []

    def busy_periods(self, start, end):
        return self.busy

    def create_tentative_event(self, **kwargs):
        self.created.append(kwargs)
        return {"id": kwargs["event_id"], "htmlLink": "https://calendar/event"}

    def delete_event(self, event_id):
        self.deleted.append(event_id)


class FakeStore:
    def __init__(self):
        self.holds = {}

    def get(self, hold_key):
        return self.holds.get(hold_key)

    def save(self, hold):
        self.holds[hold.hold_key] = hold

    def mark_released(self, hold_key, released_at):
        hold = self.holds[hold_key]
        self.holds[hold_key] = StoredHold(**{**hold.__dict__, "status": "released"})

    def expired(self, now):
        return [h for h in self.holds.values() if h.status == "tentative" and h.expires_at <= now]


class FailingStore(FakeStore):
    def save(self, hold):
        raise TimeoutError("persistence outcome unknown")


def request(key="case-123:slot-1"):
    return HoldRequest(key, "case-123", START, END)


def test_availability_reports_conflicting_busy_periods():
    calendar = FakeCalendar([(START + timedelta(minutes=5), START + timedelta(minutes=15))])
    service = CalendarService(calendar, FakeStore(), hold_minutes=10)

    result = service.availability(START, END)

    assert result.available is False
    assert result.busy == ((START + timedelta(minutes=5), START + timedelta(minutes=15)),)


def test_create_hold_rechecks_conflicts_before_inserting():
    calendar = FakeCalendar([(START, END)])
    service = CalendarService(calendar, FakeStore(), hold_minutes=10)

    with pytest.raises(CalendarConflict):
        service.create_hold(request(), now=START - timedelta(minutes=1))

    assert calendar.created == []


def test_create_hold_is_tentative_and_persists_expiry():
    calendar, store = FakeCalendar(), FakeStore()
    service = CalendarService(calendar, store, hold_minutes=10)

    hold = service.create_hold(request(), now=START - timedelta(minutes=1))

    assert hold.status == "tentative"
    assert hold.expires_at == START + timedelta(minutes=9)
    assert calendar.created[0]["status"] == "tentative"
    assert calendar.created[0]["hold_key"] == "case-123:slot-1"
    assert calendar.created[0]["event_id"] == hold.event_id
    assert store.get(hold.hold_key) == hold


def test_unknown_persistence_outcome_keeps_deterministic_event_for_retry():
    calendar = FakeCalendar()
    service = CalendarService(calendar, FailingStore(), hold_minutes=10)

    with pytest.raises(TimeoutError, match="outcome unknown"):
        service.create_hold(request(), now=START - timedelta(minutes=1))

    assert len(calendar.created) == 1
    assert calendar.deleted == []


def test_create_hold_is_idempotent_without_second_calendar_write():
    calendar, store = FakeCalendar(), FakeStore()
    service = CalendarService(calendar, store, hold_minutes=10)

    first = service.create_hold(request(), now=START - timedelta(minutes=1))
    second = service.create_hold(request(), now=START)

    assert second == first
    assert len(calendar.created) == 1


def test_same_idempotency_key_cannot_change_slot():
    service = CalendarService(FakeCalendar(), FakeStore(), hold_minutes=10)
    service.create_hold(request(), now=START - timedelta(minutes=1))

    with pytest.raises(ValueError, match="different slot"):
        service.create_hold(
            HoldRequest("case-123:slot-1", "case-123", START, END + timedelta(minutes=5)), now=START
        )


def test_release_and_expiry_delete_event_and_are_idempotent():
    calendar, store = FakeCalendar(), FakeStore()
    service = CalendarService(calendar, store, hold_minutes=10)
    hold = service.create_hold(request(), now=START - timedelta(minutes=11))

    assert service.release(hold.hold_key, now=START) is True
    assert service.release(hold.hold_key, now=START) is False
    assert calendar.deleted == [hold.event_id]

    other = service.create_hold(request("case-124:slot-1"), now=START - timedelta(minutes=11))
    assert service.expire_due(now=START) == [other.hold_key]
    assert calendar.deleted[-1] == other.event_id


def test_google_freebusy_uses_rfc3339_and_configured_calendar():
    requests = []

    def handler(req):
        requests.append(req)
        return httpx.Response(
            200,
            json={
                "calendars": {
                    "clinic@example.com": {
                        "busy": [{"start": "2026-07-13T05:00:00Z", "end": "2026-07-13T05:30:00Z"}]
                    }
                }
            },
        )

    client = GoogleCalendarClient(
        "clinic@example.com",
        token_provider=lambda: "adc-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    busy = client.busy_periods(START, END)

    assert requests[0].headers["Authorization"] == "Bearer adc-token"
    assert requests[0].url.path.endswith("/freeBusy")
    assert busy == [
        (datetime(2026, 7, 13, 5, tzinfo=UTC), datetime(2026, 7, 13, 5, 30, tzinfo=UTC))
    ]


def test_google_event_insert_uses_tentative_private_hold_metadata():
    captured = {}

    def handler(req):
        captured.update(req.read() and __import__("json").loads(req.content))
        return httpx.Response(200, json={"id": captured["id"]})

    client = GoogleCalendarClient(
        "clinic@example.com",
        token_provider=lambda: "adc-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.create_tentative_event(
        event_id="abc123",
        start=START,
        end=END,
        hold_key="safe-key",
        expires_at=END,
        status="tentative",
    )

    assert captured["status"] == "tentative"
    assert captured["transparency"] == "opaque"
    assert captured["extendedProperties"]["private"] == {
        "holdKey": "safe-key",
        "expiresAt": END.isoformat(),
    }
    assert "case" not in captured["summary"].lower()


def test_google_client_loads_adc_with_calendar_scope(monkeypatch):
    seen = {}

    class Credentials:
        token = "token"
        valid = True

    def fake_default(*, scopes):
        seen["scopes"] = scopes
        return Credentials(), "project"

    monkeypatch.setattr("clinic_agency.calendar.google.google.auth.default", fake_default)

    client = GoogleCalendarClient("clinic@example.com")

    assert client.access_token() == "token"
    assert seen["scopes"] == ["https://www.googleapis.com/auth/calendar"]
