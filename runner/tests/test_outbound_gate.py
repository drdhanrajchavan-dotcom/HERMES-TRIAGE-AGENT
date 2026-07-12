import pytest

from clinic_agency.safety.outbound import (
    ComplianceReview,
    OutboundDraft,
    OutboundGate,
    UnsafeOutboundError,
)


def test_gate_authorizes_exact_approved_draft() -> None:
    draft = OutboundDraft.create(
        case_id="case-1",
        text="Laser treatment prices vary by treatment area. The clinic can confirm the exact fee.",
    )
    review = ComplianceReview.pass_draft(draft)

    authorized = OutboundGate.authorize(draft, review)

    assert authorized.text == draft.text
    assert authorized.draft_hash == draft.draft_hash


def test_gate_rejects_text_changed_after_review() -> None:
    reviewed = OutboundDraft.create(case_id="case-1", text="The clinic can confirm the fee.")
    altered = OutboundDraft.create(case_id="case-1", text="The treatment is guaranteed to work.")
    review = ComplianceReview.pass_draft(reviewed)

    with pytest.raises(UnsafeOutboundError, match="exact draft"):
        OutboundGate.authorize(altered, review)


def test_gate_rejects_failed_review() -> None:
    draft = OutboundDraft.create(case_id="case-1", text="This will cure your acne permanently.")
    review = ComplianceReview.fail_draft(draft, violations=("cure_claim", "guarantee"))

    with pytest.raises(UnsafeOutboundError, match="did not pass"):
        OutboundGate.authorize(draft, review)
