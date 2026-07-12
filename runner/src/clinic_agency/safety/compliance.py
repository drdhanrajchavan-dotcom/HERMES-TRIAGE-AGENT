import re

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
