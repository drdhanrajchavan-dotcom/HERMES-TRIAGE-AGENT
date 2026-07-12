from clinic_agency.safety.compliance import (
    ComplianceRevisionError,
    review_draft,
    revise_until_compliant,
)
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


def test_compliance_revision_stops_as_soon_as_deterministic_rules_pass() -> None:
    attempts = []

    def revise(draft, violations):
        attempts.append((draft.text, violations))
        return OutboundDraft.create(draft.case_id, "A clinician can assess your concern.")

    result = revise_until_compliant(
        OutboundDraft.create("case-1", "This will cure acne."), revise, max_revisions=2
    )

    assert result.text == "A clinician can assess your concern."
    assert len(attempts) == 1


def test_compliance_revision_cap_cannot_be_bypassed() -> None:
    attempts = []

    def still_unsafe(draft, violations):
        attempts.append(violations)
        return OutboundDraft.create(draft.case_id, "Guaranteed cure.")

    try:
        revise_until_compliant(
            OutboundDraft.create("case-1", "Guaranteed cure."),
            still_unsafe,
            max_revisions=2,
        )
    except ComplianceRevisionError as error:
        assert error.review.verdict == "fail"
    else:
        raise AssertionError("unsafe draft escaped compliance revision cap")

    assert len(attempts) == 2
