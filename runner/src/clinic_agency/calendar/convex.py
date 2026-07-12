from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from langfuse import observe

from clinic_agency.calendar.service import StoredHold
from clinic_agency.telemetry import current_trace_id


class ConvexHoldStore:
    """Persists booking business state; Google remains the calendar system of record."""

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

    def get(self, hold_key: str) -> StoredHold | None:
        value = self._call(
            self._query_url,
            "calendarHolds:get",
            {"internalApiSecret": self._secret, "holdKey": hold_key},
        )
        return self._decode(value) if value else None

    def save(self, hold: StoredHold) -> None:
        self._call(
            self._mutation_url,
            "calendarHolds:save",
            {
                "internalApiSecret": self._secret,
                "holdKey": hold.hold_key,
                "caseExternalId": hold.case_id,
                "calendarEventId": hold.event_id,
                "startAt": hold.start.timestamp() * 1000,
                "endAt": hold.end.timestamp() * 1000,
                "expiresAt": hold.expires_at.timestamp() * 1000,
                "langfuseTraceId": current_trace_id(),
            },
        )

    def mark_released(self, hold_key: str, released_at: datetime) -> None:
        self._call(
            self._mutation_url,
            "calendarHolds:release",
            {
                "internalApiSecret": self._secret,
                "holdKey": hold_key,
                "releasedAt": released_at.timestamp() * 1000,
                "langfuseTraceId": current_trace_id(),
            },
        )

    def expired(self, now: datetime) -> list[StoredHold]:
        values = self._call(
            self._query_url,
            "calendarHolds:expired",
            {"internalApiSecret": self._secret, "now": now.timestamp() * 1000},
        )
        return [self._decode(value) for value in values]
