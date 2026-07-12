from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from langfuse import observe


class CalendarConflict(RuntimeError):
    """The requested slot became unavailable before the hold was created."""


@dataclass(frozen=True)
class Availability:
    available: bool
    busy: tuple[tuple[datetime, datetime], ...]


@dataclass(frozen=True)
class HoldRequest:
    hold_key: str
    case_id: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class StoredHold:
    hold_key: str
    case_id: str
    event_id: str
    start: datetime
    end: datetime
    expires_at: datetime
    status: str = "tentative"


class CalendarPort(Protocol):
    def busy_periods(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]: ...
    def create_tentative_event(self, **kwargs: object) -> dict[str, object]: ...
    def delete_event(self, event_id: str) -> None: ...


class HoldStore(Protocol):
    def get(self, hold_key: str) -> StoredHold | None: ...
    def save(self, hold: StoredHold) -> None: ...
    def mark_released(self, hold_key: str, released_at: datetime) -> None: ...
    def expired(self, now: datetime) -> list[StoredHold]: ...


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


class CalendarService:
    def __init__(self, calendar: CalendarPort, store: HoldStore, *, hold_minutes: int = 15) -> None:
        if hold_minutes <= 0:
            raise ValueError("hold_minutes must be positive")
        self._calendar = calendar
        self._store = store
        self._hold_duration = timedelta(minutes=hold_minutes)

    @observe(
        name="tool.calendar.availability", as_type="tool", capture_input=False, capture_output=False
    )
    def availability(self, start: datetime, end: datetime) -> Availability:
        start, end = _aware(start, "start"), _aware(end, "end")
        if end <= start:
            raise ValueError("end must be after start")
        busy = tuple(self._calendar.busy_periods(start, end))
        conflicts = tuple((a, b) for a, b in busy if a < end and b > start)
        return Availability(not conflicts, conflicts)

    @observe(
        name="tool.calendar.create_tentative_hold",
        as_type="tool",
        capture_input=False,
        capture_output=False,
    )
    def create_hold(self, request: HoldRequest, *, now: datetime | None = None) -> StoredHold:
        start, end = _aware(request.start, "start"), _aware(request.end, "end")
        now = _aware(now or datetime.now(UTC), "now")
        existing = self._store.get(request.hold_key)
        if existing:
            if (existing.case_id, existing.start, existing.end) != (request.case_id, start, end):
                raise ValueError("idempotency key already belongs to a different slot")
            return existing
        if not self.availability(start, end).available:
            raise CalendarConflict("requested calendar slot is no longer available")
        event_id = "h" + hashlib.sha256(request.hold_key.encode()).hexdigest()[:39]
        hold = StoredHold(
            request.hold_key, request.case_id, event_id, start, end, now + self._hold_duration
        )
        self._calendar.create_tentative_event(
            event_id=event_id,
            start=start,
            end=end,
            hold_key=request.hold_key,
            expires_at=hold.expires_at,
            status="tentative",
        )
        # Keep the deterministic event on an unknown persistence outcome. A retry can
        # recover the same Google event (409 -> GET) and finish saving business state.
        self._store.save(hold)
        return hold

    @observe(
        name="tool.calendar.release_hold", as_type="tool", capture_input=False, capture_output=False
    )
    def release(self, hold_key: str, *, now: datetime | None = None) -> bool:
        hold = self._store.get(hold_key)
        if not hold or hold.status != "tentative":
            return False
        now = _aware(now or datetime.now(UTC), "now")
        self._calendar.delete_event(hold.event_id)
        self._store.mark_released(hold_key, now)
        return True

    @observe(
        name="tool.calendar.expire_holds", as_type="tool", capture_input=False, capture_output=False
    )
    def expire_due(self, *, now: datetime | None = None) -> list[str]:
        now = _aware(now or datetime.now(UTC), "now")
        released = []
        for hold in self._store.expired(now):
            if self.release(hold.hold_key, now=now):
                released.append(hold.hold_key)
        return released
