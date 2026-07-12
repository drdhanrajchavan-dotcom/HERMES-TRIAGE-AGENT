from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

ALLOWED_TOOLS = frozenset(
    {
        "calendar.hold",
        "calendar.read",
        "dodo.checkout",
        "knowledge.read",
        "linkup.search",
        "telegram.send",
    }
)


class Autonomy(StrEnum):
    AUTO = "auto"
    REVIEW = "review"
    DRAFT_ONLY = "draft-only"


class RoleConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=80)
    mission: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1)
    tools: tuple[str, ...] = ()
    autonomy: Autonomy
    max_cost_usd: float = Field(default=0.25, gt=0, le=10)
    escalation_triggers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def enforce_guardrails(self) -> "RoleConfig":
        unknown = sorted(set(self.tools) - ALLOWED_TOOLS)
        if unknown:
            raise ValueError(f"unknown tool(s): {', '.join(unknown)}")
        if self.name.casefold() == "compliance" and self.autonomy is not Autonomy.REVIEW:
            raise ValueError("Compliance must use review autonomy")
        return self
