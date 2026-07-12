from typing import Any

import httpx

from clinic_agency.domain.cases import Case
from clinic_agency.safety.outbound import AuthorizedOutbound, ComplianceReview


class ConvexCaseStore:
    def __init__(
        self,
        deployment_url: str,
        *,
        internal_api_secret: str,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self._url = deployment_url.rstrip("/") + "/api/mutation"
        self._internal_api_secret = internal_api_secret
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def add(self, case: Case) -> bool:
        payload = self._mutate("cases:ingestTelegram", self._mutation_args(case))
        return not bool(payload["duplicate"])

    def record_delivery(
        self,
        *,
        external_event_id: str,
        outbound: AuthorizedOutbound,
        review: ComplianceReview,
        external_message_id: str,
    ) -> None:
        self._mutate(
            "cases:recordApprovedDelivery",
            {
                "internalApiSecret": self._internal_api_secret,
                "externalEventId": external_event_id,
                "text": outbound.text,
                "draftHash": outbound.draft_hash,
                "reviewDraftHash": review.draft_hash,
                "violations": list(review.violations),
                "externalMessageId": external_message_id,
            },
        )

    def _mutate(self, path: str, args: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(
            self._url,
            json={"path": path, "args": args, "format": "json"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            detail = payload.get("errorMessage", "unknown error")
            raise RuntimeError(f"Convex mutation failed: {detail}")
        return payload["value"]

    def _mutation_args(self, case: Case) -> dict[str, Any]:
        return {
            "internalApiSecret": self._internal_api_secret,
            "externalEventId": case.external_event_id,
            "patientExternalId": case.patient_external_id,
            "message": case.message,
            "mustEscalate": case.must_escalate,
            "redFlags": list(case.red_flags),
            "openedAt": int(case.opened_at.timestamp() * 1000),
        }
