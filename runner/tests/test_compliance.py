from clinic_agency.safety.compliance import review_draft
from clinic_agency.safety.outbound import OutboundDraft


def test_compliance_rejects_cure_and_guarantee_claims() -> None:
    draft = OutboundDraft.create(
        case_id="case-1",
        text="This treatment will cure your acne and is guaranteed to work.",
    )

    review = review_draft(draft)

    assert review.verdict == "fail"
    assert set(review.violations) == {"cure_claim", "guarantee_claim"}


def test_compliance_rejects_diagnostic_language() -> None:
    draft = OutboundDraft.create(
        case_id="case-1",
        text="You definitely have melasma.",
    )

    review = review_draft(draft)

    assert review.verdict == "fail"
    assert review.violations == ("diagnosis_claim",)


def test_compliance_passes_grounded_coordination_copy() -> None:
    draft = OutboundDraft.create(
        case_id="case-1",
        text="A clinician can assess your concern. Would you like available consultation slots?",
    )

    review = review_draft(draft)

    assert review.verdict == "pass"
    assert review.violations == ()
