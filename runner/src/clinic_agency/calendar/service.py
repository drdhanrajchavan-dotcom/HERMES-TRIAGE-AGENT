from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from langfuse import observe


class CalendarConflict(RuntimeError):
    """The requested slot cannot be held."""


class CalendarPermanentError(RuntimeError):
    """A non-retryable calendar request failure."""


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
    status: str = "creating"


class CalendarPort(Protocol):
    def busy_periods(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]: ...
    def create_tentative_event(self, **kwargs: object) -> dict[str, object]: ...
    def delete_event(self, event_id: str) -> None: ...


class HoldStore(Protocol):
    def get(self, hold_key: str) -> StoredHold | None: ...
    def claim(self, hold: StoredHold) -> StoredHold: ...
    def activate(self, hold_key: str) -> StoredHold: ...
    def record_error(self, hold_key: str, error: str) -> None: ...
    def fail(self, hold_key: str, error: str) -> None: ...
    def claim_release(self, hold_key: str, released_at: datetime) -> StoredHold | None: ...
    def finalize_release(
        self, hold_key: str, released_at: datetime, *, expired: bool = False
    ) -> None: ...
    def expired(self, now: datetime, *, limit: int = 100) -> list[StoredHold]: ...


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _identifier(value: str, name: str) -> str:
    value = value.strip()
    if not value or len(value) > 128:
        raise ValueError(f"{name} must contain 1 to 128 characters")
    return value


class CalendarService:
    def __init__(self, calendar: CalendarPort, store: HoldStore, *, hold_minutes: int = 15) -> None:
        if not 1 <= hold_minutes <= 120:
            raise ValueError("hold_minutes must be between 1 and 120")
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
        hold_key = _identifier(request.hold_key, "hold_key")
        case_id = _identifier(request.case_id, "case_id")
        start, end = _aware(request.start, "start"), _aware(request.end, "end")
        now = _aware(now or datetime.now(UTC), "now")
        if end <= start:
            raise ValueError("end must be after start")
        if start <= now:
            raise ValueError("start must be in the future")
        if end - start > timedelta(hours=8):
            raise ValueError("appointment duration must not exceed 8 hours")
        expires_at = min(now + self._hold_duration, start)
        event_id = "h" + hashlib.sha256(hold_key.encode()).hexdigest()[:39]
        proposed = StoredHold(hold_key, case_id, event_id, start, end, expires_at, "creating")

        claimed = self._store.claim(proposed)  # atomic idempotency + canonical slot claim
        if (claimed.case_id, claimed.start, claimed.end) != (case_id, start, end):
            raise ValueError("idempotency key already belongs to a different slot")
        if claimed.status == "active" and claimed.expires_at > now:
            return claimed
        if claimed.status in {"released", "expired", "failed"} or claimed.expires_at <= now:
            raise CalendarConflict("idempotency key is terminal or expired")
        if claimed.status != "creating":
            raise CalendarConflict(f"hold cannot be created from {claimed.status} state")

        try:
            if not self.availability(start, end).available:
                self._store.fail(hold_key, "calendar slot is busy")
                raise CalendarConflict("requested calendar slot is no longer available")
            self._calendar.create_tentative_event(
                event_id=event_id,
                start=start,
                end=end,
                hold_key=hold_key,
                expires_at=claimed.expires_at,
                status="tentative",
            )
            return self._store.activate(hold_key)
        except CalendarConflict:
            raise
        except CalendarPermanentError as exc:
            self._store.fail(hold_key, str(exc))
            raise
        except Exception as exc:
            self._store.record_error(hold_key, str(exc))
            raise

    @observe(
        name="tool.calendar.release_hold", as_type="tool", capture_input=False, capture_output=False
    )
    def release(self, hold_key: str, *, now: datetime | None = None, expired: bool = False) -> bool:
        now = _aware(now or datetime.now(UTC), "now")
        hold = self._store.claim_release(_identifier(hold_key, "hold_key"), now)
        if not hold:
            return False
        try:
            self._calendar.delete_event(hold.event_id)
        except Exception as exc:
            self._store.record_error(hold_key, str(exc))
            raise
        self._store.finalize_release(hold_key, now, expired=expired)
        return True

    @observe(
        name="tool.calendar.expire_holds", as_type="tool", capture_input=False, capture_output=False
    )
    def expire_due(self, *, now: datetime | None = None, limit: int = 100) -> list[str]:
        now = _aware(now or datetime.now(UTC), "now")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        released = []
        for hold in self._store.expired(now, limit=limit):
            if self.release(hold.hold_key, now=now, expired=True):
                released.append(hold.hold_key)
        return released
