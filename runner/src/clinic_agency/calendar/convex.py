from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from langfuse import observe

from clinic_agency.calendar.service import CalendarConflict, StoredHold
from clinic_agency.telemetry import current_trace_id


class ConvexHoldStore:
    """Durable calendar state machine backed by atomic Convex mutations."""

    def __init__(
        self,
        convex_url: str,
        *,
        internal_api_secret: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        root = convex_url.rstrip("/")
        self._query_url = f"{root}/api/query"
        self._mutation_url = f"{root}/api/mutation"
        self._secret = internal_api_secret
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @staticmethod
    def _decode(value: dict[str, Any]) -> StoredHold:
        def instant(name: str) -> datetime:
            return datetime.fromtimestamp(value[name] / 1000, UTC)

        return StoredHold(
            value["holdKey"],
            value["caseExternalId"],
            value["calendarEventId"],
            instant("startAt"),
            instant("endAt"),
            instant("expiresAt"),
            value["status"],
        )

    @observe(
        name="tool.convex.calendar_hold_query",
        as_type="tool",
        capture_input=False,
        capture_output=False,
    )
    def _call(self, url: str, path: str, args: dict[str, Any]) -> Any:
        response = self._client.post(url, json={"path": path, "args": args, "format": "json"})
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(
                f"Convex calendar hold request failed: {payload.get('errorMessage')}"
            )
        return payload.get("value")

    def _args(self, **values: Any) -> dict[str, Any]:
        return {"internalApiSecret": self._secret, **values}

    def get(self, hold_key: str) -> StoredHold | None:
        value = self._call(self._query_url, "calendarHolds:get", self._args(holdKey=hold_key))
        return self._decode(value) if value else None

    def claim(self, hold: StoredHold) -> StoredHold:
        value = self._call(
            self._mutation_url,
            "calendarHolds:claim",
            self._args(
                holdKey=hold.hold_key,
                caseExternalId=hold.case_id,
                calendarEventId=hold.event_id,
                startAt=hold.start.timestamp() * 1000,
                endAt=hold.end.timestamp() * 1000,
                expiresAt=hold.expires_at.timestamp() * 1000,
                langfuseTraceId=current_trace_id(),
            ),
        )
        if value.get("outcome") == "slot_conflict":
            raise CalendarConflict("requested calendar slot is already claimed")
        if value.get("outcome") == "key_conflict":
            raise ValueError("idempotency key already belongs to a different slot")
        return self._decode(value["hold"])

    def _transition(self, path: str, hold_key: str, **values: Any) -> Any:
        return self._call(
            self._mutation_url,
            f"calendarHolds:{path}",
            self._args(holdKey=hold_key, langfuseTraceId=current_trace_id(), **values),
        )

    def activate(self, hold_key: str) -> StoredHold:
        return self._decode(self._transition("activate", hold_key)["hold"])

    def record_error(self, hold_key: str, error: str) -> None:
        self._transition("recordError", hold_key, error=error[:1000])

    def fail(self, hold_key: str, error: str) -> None:
        self._transition("fail", hold_key, error=error[:1000])

    def claim_release(self, hold_key: str, released_at: datetime) -> StoredHold | None:
        value = self._transition(
            "claimRelease", hold_key, releasedAt=released_at.timestamp() * 1000
        )
        return self._decode(value["hold"]) if value.get("hold") else None

    def finalize_release(
        self, hold_key: str, released_at: datetime, *, expired: bool = False
    ) -> None:
        self._transition(
            "finalizeRelease", hold_key, releasedAt=released_at.timestamp() * 1000, expired=expired
        )

    def expired(self, now: datetime, *, limit: int = 100) -> list[StoredHold]:
        values = self._call(
            self._query_url,
            "calendarHolds:expired",
            self._args(now=now.timestamp() * 1000, limit=limit),
        )
        return [self._decode(value) for value in values]
