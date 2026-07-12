from dataclasses import dataclass

from clinic_agency.domain.cases import Case


@dataclass(frozen=True)
class PlanStep:
    key: str
    role: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class CasePlan:
    steps: tuple[PlanStep, ...]

    def __post_init__(self) -> None:
        known: set[str] = set()
        for step in self.steps:
            if step.key in known:
                raise ValueError(f"duplicate plan step: {step.key}")
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f"step {step.key} has unresolved dependencies: {sorted(missing)}")
            known.add(step.key)
        if not self.steps or self.steps[-1].role != "Compliance":
            raise ValueError("every plan must end at Compliance")


class ManagerPlanner:
    def plan(self, case: Case) -> CasePlan:
        if case.must_escalate:
            return CasePlan(
                (
                    PlanStep("triage", "Triage"),
                    PlanStep("escalation", "Manager", ("triage",)),
                    PlanStep("draft", "Communications", ("escalation",)),
                    PlanStep("compliance", "Compliance", ("draft",)),
                )
            )

        message = case.message.casefold()
        needs_booking = any(
            phrase in message
            for phrase in ("appointment", "book", "come ", "saturday", "slot")
        )
        needs_knowledge = any(
            phrase in message for phrase in ("price", "cost", "how much", "what is")
        )
        steps = [PlanStep("triage", "Triage")]
        draft_dependencies: list[str] = []
        if needs_knowledge:
            steps.append(PlanStep("knowledge", "Knowledge", ("triage",)))
            draft_dependencies.append("knowledge")
        if needs_booking:
            steps.append(PlanStep("booking", "Booking", ("triage",)))
            draft_dependencies.append("booking")
        if not draft_dependencies:
            draft_dependencies.append("triage")
        steps.extend(
            (
                PlanStep("draft", "Communications", tuple(draft_dependencies)),
                PlanStep("compliance", "Compliance", ("draft",)),
            )
        )
        return CasePlan(tuple(steps))
