from clinic_agency.knowledge.responder import CitedKnowledgeResponder
from clinic_agency.knowledge.service import KnowledgeEvidence


class EvidenceService:
    def __init__(self, evidence):
        self.evidence = evidence
        self.calls = []

    def gather(self, query, cards):
        self.calls.append((query, cards))
        return self.evidence


def test_responder_quotes_bounded_evidence_with_source() -> None:
    evidence = (
        KnowledgeEvidence(
            "linkup:1",
            "Acne care",
            "  Treatment options are selected after assessment.  ",
            "https://clearskin.in/acne/",
        ),
    )

    answer = CitedKnowledgeResponder(EvidenceService(evidence)).answer("Acne options?")

    assert "Treatment options are selected after assessment." in answer
    assert "Source: https://clearskin.in/acne/" in answer
    assert "general clinic information" in answer


def test_responder_defers_when_no_cited_evidence_exists() -> None:
    answer = CitedKnowledgeResponder(EvidenceService(())).answer("Unknown policy?")

    assert "clinic team" in answer.lower()
    assert "confirm" in answer.lower()
