import re
from dataclasses import dataclass

DEFAULT_RED_FLAGS = (
    "adverse reaction",
    "difficulty breathing",
    "fever",
    "fainted",
    "hot",
    "severe pain",
    "shortness of breath",
    "swollen",
    "swelling",
    "unconscious",
)


@dataclass(frozen=True)
class RedFlagResult:
    must_escalate: bool
    matched_terms: tuple[str, ...]


def classify_red_flags(
    message: str, red_flags: tuple[str, ...] = DEFAULT_RED_FLAGS
) -> RedFlagResult:
    normalized = re.sub(r"\s+", " ", message.casefold()).strip()
    matched = tuple(term for term in red_flags if term.casefold() in normalized)
    return RedFlagResult(must_escalate=bool(matched), matched_terms=matched)
