from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

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

    def claim(self, hold):
        existing = self.holds.get(hold.hold_key)
        if existing:
            if (existing.case_id, existing.start, existing.end) != (
                hold.case_id,
                hold.start,
                hold.end,
            ):
                raise ValueError("idempotency key already belongs to a different slot")
            return existing
        if any(
            h.start == hold.start
            and h.end == hold.end
            and h.status in ("creating", "active", "releasing")
            for h in self.holds.values()
        ):
            raise CalendarConflict("requested calendar slot is already claimed")
        self.holds[hold.hold_key] = hold
        return hold

    def activate(self, hold_key):
        hold = self.holds[hold_key]
        self.holds[hold_key] = StoredHold(**{**hold.__dict__, "status": "active"})
        return self.holds[hold_key]

    def record_error(self, hold_key, error):
        pass

    def fail(self, hold_key, error):
        hold = self.holds[hold_key]
        self.holds[hold_key] = StoredHold(**{**hold.__dict__, "status": "failed"})

    def claim_release(self, hold_key, released_at):
        hold = self.holds.get(hold_key)
        if not hold or hold.status in ("released", "failed", "expired"):
            return None
        self.holds[hold_key] = StoredHold(**{**hold.__dict__, "status": "releasing"})
        return self.holds[hold_key]

    def finalize_release(self, hold_key, released_at, *, expired=False):
        hold = self.holds[hold_key]
        self.holds[hold_key] = StoredHold(
            **{**hold.__dict__, "status": "expired" if expired else "released"}
        )

    def expired(self, now, *, limit=100):
        return [h for h in self.holds.values() if h.status == "active" and h.expires_at <= now][
            :limit
        ]


class FailingStore(FakeStore):
    def activate(self, hold_key):
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

    assert hold.status == "active"
    assert hold.expires_at == START
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


def test_internal_calendar_endpoints_require_edge_auth_and_expose_tool_boundary():
    service = CalendarService(FakeCalendar(), FakeStore(), hold_minutes=10)
    client = TestClient(
        create_app(webhook_shared_secret="edge-secret", calendar_service=service)
    )
    payload = {"start": START.isoformat(), "end": END.isoformat()}

    assert client.post("/internal/calendar/availability", json=payload).status_code == 401
    available = client.post(
        "/internal/calendar/availability",
        json=payload,
        headers={"X-Clinic-Edge-Secret": "edge-secret"},
    )

    assert available.status_code == 200
    assert available.json() == {"available": True, "busy": []}


def test_internal_calendar_expiry_endpoint_is_bounded_and_authenticated():
    class ExpiryService:
        def expire_due(self, *, limit):
            assert limit == 25
            return ["hold-1"]

    client = TestClient(
        create_app(webhook_shared_secret="edge-secret", calendar_service=ExpiryService())
    )
    response = client.post(
        "/internal/calendar/expire",
        json={"limit": 25},
        headers={"X-Clinic-Edge-Secret": "edge-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"expired_hold_keys": ["hold-1"]}


def test_create_hold_is_idempotent_without_second_calendar_write():
    calendar, store = FakeCalendar(), FakeStore()
    service = CalendarService(calendar, store, hold_minutes=10)

    first = service.create_hold(request(), now=START - timedelta(minutes=1))
    second = service.create_hold(request(), now=START - timedelta(seconds=30))

    assert second == first
    assert len(calendar.created) == 1


def test_same_idempotency_key_cannot_change_slot():
    service = CalendarService(FakeCalendar(), FakeStore(), hold_minutes=10)
    service.create_hold(request(), now=START - timedelta(minutes=1))

    with pytest.raises(ValueError, match="different slot"):
        service.create_hold(
            HoldRequest("case-123:slot-1", "case-123", START, END + timedelta(minutes=5)),
            now=START - timedelta(seconds=30),
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


def test_different_keys_cannot_claim_the_same_slot_before_google_write():
    calendar, store = FakeCalendar(), FakeStore()
    service = CalendarService(calendar, store, hold_minutes=10)
    service.create_hold(request("key-one"), now=START - timedelta(minutes=1))
    with pytest.raises(CalendarConflict, match="claimed"):
        service.create_hold(request("key-two"), now=START - timedelta(minutes=1))
    assert len(calendar.created) == 1


def test_terminal_idempotency_key_is_never_returned_as_success():
    calendar, store = FakeCalendar(), FakeStore()
    service = CalendarService(calendar, store, hold_minutes=10)
    hold = service.create_hold(request(), now=START - timedelta(minutes=11))
    service.release(hold.hold_key, now=START)
    with pytest.raises(CalendarConflict, match="terminal"):
        service.create_hold(request(), now=START - timedelta(seconds=30))


def test_google_freebusy_fails_closed_on_calendar_level_errors():
    def handler(req):
        return httpx.Response(
            200, json={"calendars": {"clinic@example.com": {"errors": [{"reason": "notFound"}]}}}
        )

    client = GoogleCalendarClient(
        "clinic@example.com",
        token_provider=lambda: "adc-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(RuntimeError, match="freeBusy.*notFound"):
        client.busy_periods(START, END)


def test_google_409_rejects_event_not_owned_by_exact_hold_and_slot():
    def handler(req):
        if req.method == "POST":
            return httpx.Response(409)
        return httpx.Response(
            200,
            json={
                "id": "abc123",
                "start": {"dateTime": START.isoformat()},
                "end": {"dateTime": (END + timedelta(minutes=5)).isoformat()},
                "extendedProperties": {"private": {"holdKey": "safe-key"}},
            },
        )

    client = GoogleCalendarClient(
        "clinic@example.com",
        token_provider=lambda: "adc-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(CalendarConflict, match="not owned"):
        client.create_tentative_event(
            event_id="abc123", start=START, end=END, hold_key="safe-key", expires_at=END
        )


@pytest.mark.parametrize(
    "key,case", [("", "case"), ("x" * 129, "case"), ("key", ""), ("key", "x" * 129)]
)
def test_create_hold_validates_identifiers(key, case):
    service = CalendarService(FakeCalendar(), FakeStore())
    with pytest.raises(ValueError):
        service.create_hold(HoldRequest(key, case, START, END), now=START - timedelta(minutes=1))
