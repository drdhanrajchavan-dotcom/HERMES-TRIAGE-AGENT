import re
from collections.abc import Sequence
from typing import Protocol

from langfuse import observe

from clinic_agency.knowledge.service import KnowledgeCard, KnowledgeEvidence

GENERAL_INFORMATION_NOTE = (
    "This is general clinic information. A clinician can confirm what is appropriate for you "
    "after an assessment."
)
NO_EVIDENCE_REPLY = (
    "I couldn't confirm that from the clinic's approved sources. "
    "Our clinic team can review your question and confirm the correct information."
)


class EvidenceService(Protocol):
    def gather(
        self, query: str, cards: Sequence[KnowledgeCard]
    ) -> tuple[KnowledgeEvidence, ...]: ...


def _bounded_excerpt(value: str, limit: int = 600) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= limit:
        return normalized
    shortened = normalized[:limit].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{shortened}…"


class CitedKnowledgeResponder:
    def __init__(
        self,
        evidence_service: EvidenceService,
        cards: Sequence[KnowledgeCard] = (),
    ) -> None:
        self._evidence_service = evidence_service
        self._cards = tuple(cards)

    @observe(
        name="knowledge.answer",
        as_type="chain",
        capture_input=False,
        capture_output=False,
    )
    def answer(self, question: str) -> str:
        evidence = self._evidence_service.gather(question, self._cards)
        if not evidence:
            return NO_EVIDENCE_REPLY
        primary = evidence[0]
        excerpt = _bounded_excerpt(primary.excerpt)
        return f"{excerpt}\n\nSource: {primary.url}\n\n{GENERAL_INFORMATION_NOTE}"
