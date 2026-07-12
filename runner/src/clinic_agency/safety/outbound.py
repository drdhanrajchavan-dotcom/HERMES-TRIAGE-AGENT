from dataclasses import dataclass
from hashlib import sha256
from typing import Literal


class UnsafeOutboundError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutboundDraft:
    case_id: str
    text: str
    draft_hash: str

    @classmethod
    def create(cls, case_id: str, text: str) -> "OutboundDraft":
        digest = sha256(text.encode("utf-8")).hexdigest()
        return cls(case_id=case_id, text=text, draft_hash=digest)


@dataclass(frozen=True)
class ComplianceReview:
    case_id: str
    draft_hash: str
    verdict: Literal["pass", "fail"]
    violations: tuple[str, ...] = ()

    @classmethod
    def pass_draft(cls, draft: OutboundDraft) -> "ComplianceReview":
        return cls(case_id=draft.case_id, draft_hash=draft.draft_hash, verdict="pass")

    @classmethod
    def fail_draft(
        cls, draft: OutboundDraft, violations: tuple[str, ...]
    ) -> "ComplianceReview":
        return cls(
            case_id=draft.case_id,
            draft_hash=draft.draft_hash,
            verdict="fail",
            violations=violations,
        )


@dataclass(frozen=True)
class AuthorizedOutbound:
    case_id: str
    text: str
    draft_hash: str


class OutboundGate:
    @staticmethod
    def authorize(
        draft: OutboundDraft, review: ComplianceReview
    ) -> AuthorizedOutbound:
        if review.verdict != "pass":
            raise UnsafeOutboundError("Outbound draft did not pass compliance review")
        if review.case_id != draft.case_id or review.draft_hash != draft.draft_hash:
            raise UnsafeOutboundError("Compliance approval does not match the exact draft")
        return AuthorizedOutbound(
            case_id=draft.case_id,
            text=draft.text,
            draft_hash=draft.draft_hash,
        )
