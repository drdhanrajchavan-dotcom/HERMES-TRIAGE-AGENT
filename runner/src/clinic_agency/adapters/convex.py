from typing import Any

import httpx

from clinic_agency.domain.cases import Case


class ConvexCaseStore:
    def __init__(
        self,
        deployment_url: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self._url = deployment_url.rstrip("/") + "/api/mutation"
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def add(self, case: Case) -> bool:
        response = self._client.post(
            self._url,
            json={
                "path": "cases:ingestTelegram",
                "args": self._mutation_args(case),
                "format": "json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            detail = payload.get("errorMessage", "unknown error")
            raise RuntimeError(f"Convex mutation failed: {detail}")
        return not bool(payload["value"]["duplicate"])

    @staticmethod
    def _mutation_args(case: Case) -> dict[str, Any]:
        return {
            "externalEventId": case.external_event_id,
            "patientExternalId": case.patient_external_id,
            "message": case.message,
            "mustEscalate": case.must_escalate,
            "redFlags": list(case.red_flags),
            "openedAt": int(case.opened_at.timestamp() * 1000),
        }
