from clinic_agency.knowledge.linkup import SearchResult
from clinic_agency.knowledge.service import (
    GroundedKnowledgeService,
    KnowledgeCard,
)


class WebSearch:
    def __init__(self) -> None:
        self.queries = []

    def search(self, query: str):
        self.queries.append(query)
        return (
            SearchResult(
                "ClearSkin source",
                "https://clearskin.in/acne/",
                "Acne treatment choice depends on assessment.",
            ),
        )


def test_approved_local_card_is_preferred_and_cited() -> None:
    search = WebSearch()
    service = GroundedKnowledgeService(search)
    cards = [
        KnowledgeCard(
            "approved",
            "Acne care",
            "Assessment is required.",
            True,
            "https://clearskin.in/acne/",
            ("acne",),
        ),
        KnowledgeCard("draft", "Draft", "Guaranteed cure.", False, None, ("acne",)),
    ]

    evidence = service.gather("Tell me about acne care", cards)

    assert [item.source_id for item in evidence] == ["approved"]
    assert evidence[0].url == "https://clearskin.in/acne/"
    assert search.queries == []


def test_web_fallback_returns_cited_own_domain_evidence() -> None:
    search = WebSearch()
    service = GroundedKnowledgeService(search)

    evidence = service.gather("Tell me about acne care", [])

    assert evidence[0].source_id == "linkup:1"
    assert evidence[0].url == "https://clearskin.in/acne/"
    assert search.queries == ["Tell me about acne care"]
