import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from langfuse import get_client, observe

from clinic_agency.knowledge.linkup import SearchResult


@dataclass(frozen=True)
class KnowledgeCard:
    source_id: str
    title: str
    body: str
    approved: bool
    source_url: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeEvidence:
    source_id: str
    title: str
    excerpt: str
    url: str


class OwnDomainSearch(Protocol):
    def search(self, query: str) -> Sequence[SearchResult]: ...


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class GroundedKnowledgeService:
    def __init__(self, web_search: OwnDomainSearch, max_evidence: int = 5) -> None:
        self._web_search = web_search
        self._max_evidence = max_evidence

    @observe(
        name="knowledge.gather",
        as_type="retriever",
        capture_input=False,
        capture_output=False,
    )
    def gather(
        self, query: str, cards: Sequence[KnowledgeCard]
    ) -> tuple[KnowledgeEvidence, ...]:
        query_terms = _terms(query)
        matched = [
            card
            for card in cards
            if card.approved
            and card.source_url
            and query_terms.intersection(
                _terms(" ".join((card.title, card.body, *card.tags)))
            )
        ][: self._max_evidence]
        if matched:
            evidence = tuple(
                KnowledgeEvidence(
                    source_id=card.source_id,
                    title=card.title,
                    excerpt=card.body,
                    url=card.source_url or "",
                )
                for card in matched
            )
            source = "approved_kb"
        else:
            evidence = tuple(
                KnowledgeEvidence(
                    source_id=f"linkup:{index}",
                    title=result.title,
                    excerpt=result.content,
                    url=result.url,
                )
                for index, result in enumerate(
                    self._web_search.search(query)[: self._max_evidence], start=1
                )
            )
            source = "own_domain_web"
        get_client().update_current_span(
            output={"evidence_count": len(evidence), "source": source},
            metadata={"role": "Knowledge", "task_type": "knowledge_retrieval"},
        )
        return evidence
