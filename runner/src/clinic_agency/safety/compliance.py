import re
from collections.abc import Callable

from clinic_agency.safety.outbound import ComplianceReview, OutboundDraft

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cure_claim", re.compile(r"\b(cure|cures|cured|permanent(?:ly)?)\b", re.IGNORECASE)),
    (
        "guarantee_claim",
        re.compile(r"\b(guarantee|guaranteed|100% effective)\b", re.IGNORECASE),
    ),
    (
        "diagnosis_claim",
        re.compile(r"\b(you (?:definitely )?have|you are diagnosed with)\b", re.IGNORECASE),
    ),
)


def review_draft(draft: OutboundDraft) -> ComplianceReview:
    violations = tuple(name for name, pattern in RULES if pattern.search(draft.text))
    if violations:
        return ComplianceReview.fail_draft(draft, violations)
    return ComplianceReview.pass_draft(draft)


class ComplianceRevisionError(RuntimeError):
    def __init__(self, review: ComplianceReview) -> None:
        super().__init__("draft remains unsafe after deterministic revision cap")
        self.review = review


def revise_until_compliant(
    draft: OutboundDraft,
    revise: Callable[[OutboundDraft, tuple[str, ...]], OutboundDraft],
    *,
    max_revisions: int = 2,
) -> OutboundDraft:
    """Apply bounded revisions; deterministic rules retain final authority."""
    if max_revisions < 0:
        raise ValueError("max_revisions cannot be negative")
    current = draft
    for revision in range(max_revisions + 1):
        review = review_draft(current)
        if review.verdict == "pass":
            return current
        if revision == max_revisions:
            raise ComplianceRevisionError(review)
        revised = revise(current, review.violations)
        if revised.case_id != current.case_id:
            raise ValueError("revision cannot change case_id")
        current = revised
    raise AssertionError("unreachable")
