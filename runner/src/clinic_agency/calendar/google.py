from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote

import google.auth
import httpx
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from langfuse import observe

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
API_ROOT = "https://www.googleapis.com/calendar/v3"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GoogleCalendarClient:
    """Calendar REST client authenticated only with Application Default Credentials."""

    def __init__(
        self,
        calendar_id: str,
        *,
        token_provider: Callable[[], str] | None = None,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        if not calendar_id:
            raise ValueError("calendar_id is required")
        self._calendar_id = calendar_id
        self._credentials: Credentials | None = None
        if token_provider is None:
            self._credentials, _ = google.auth.default(scopes=[CALENDAR_SCOPE])
            token_provider = self.access_token
        self._token_provider = token_provider
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def access_token(self) -> str:
        assert self._credentials is not None
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        if not self._credentials.token:
            raise RuntimeError("ADC did not provide a Google access token")
        return self._credentials.token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token_provider()}",
            "Content-Type": "application/json",
        }

    @observe(
        name="tool.google_calendar.freebusy",
        as_type="tool",
        capture_input=False,
        capture_output=False,
    )
    def busy_periods(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        response = self._client.post(
            f"{API_ROOT}/freeBusy",
            headers=self._headers(),
            json={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "items": [{"id": self._calendar_id}],
            },
        )
        response.raise_for_status()
        entries = response.json().get("calendars", {}).get(self._calendar_id, {}).get("busy", [])
        return [(_parse(item["start"]), _parse(item["end"])) for item in entries]

    @observe(
        name="tool.google_calendar.insert_tentative",
        as_type="tool",
        capture_input=False,
        capture_output=False,
    )
    def create_tentative_event(
        self,
        *,
        event_id: str,
        start: datetime,
        end: datetime,
        hold_key: str,
        expires_at: datetime,
        status: str = "tentative",
    ) -> dict[str, object]:
        body = {
            "id": event_id,
            "summary": "Tentative appointment hold",
            "status": status,
            "transparency": "opaque",
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
            "extendedProperties": {
                "private": {"holdKey": hold_key, "expiresAt": expires_at.isoformat()}
            },
        }
        url = f"{API_ROOT}/calendars/{quote(self._calendar_id, safe='')}/events"
        response = self._client.post(url, headers=self._headers(), json=body)
        if response.status_code == 409:
            response = self._client.get(f"{url}/{event_id}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    @observe(
        name="tool.google_calendar.delete_hold",
        as_type="tool",
        capture_input=False,
        capture_output=False,
    )
    def delete_event(self, event_id: str) -> None:
        calendar = quote(self._calendar_id, safe="")
        event = quote(event_id, safe="")
        url = f"{API_ROOT}/calendars/{calendar}/events/{event}"
        response = self._client.delete(url, headers=self._headers())
        if response.status_code not in (204, 404, 410):
            response.raise_for_status()
