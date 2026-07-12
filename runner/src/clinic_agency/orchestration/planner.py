from dataclasses import dataclass

from langfuse import get_client, observe

from clinic_agency.domain.cases import Case


@dataclass(frozen=True)
class PlanStep:
    key: str
    role: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class CasePlan:
    steps: tuple[PlanStep, ...]
    langfuse_trace_id: str = ""

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
    @observe(
        name="manager.plan",
        as_type="agent",
        capture_input=False,
        capture_output=False,
    )
    def plan(self, case: Case) -> CasePlan:
        langfuse = get_client()
        metadata = {
            "case_id": case.external_event_id,
            "role": "Manager",
            "task_type": "plan",
        }
        langfuse.update_current_trace(
            session_id=case.external_event_id,
            metadata=metadata,
            tags=["manager", "plan"],
        )
        langfuse.update_current_span(
            input={
                "case_id": case.external_event_id,
                "channel": case.channel,
                "must_escalate": case.must_escalate,
            },
            metadata=metadata,
        )
        trace_id = langfuse.get_current_trace_id() or ""
        if case.must_escalate:
            steps = (
                PlanStep("triage", "Triage"),
                PlanStep("escalation", "Manager", ("triage",)),
                PlanStep("draft", "Communications", ("escalation",)),
                PlanStep("compliance", "Compliance", ("draft",)),
            )
        else:
            message = case.message.casefold()
            needs_booking = any(
                phrase in message
                for phrase in ("appointment", "book", "come ", "saturday", "slot")
            )
            needs_knowledge = any(
                phrase in message for phrase in ("price", "cost", "how much", "what is")
            )
            planned = [PlanStep("triage", "Triage")]
            draft_dependencies: list[str] = []
            if needs_knowledge:
                planned.append(PlanStep("knowledge", "Knowledge", ("triage",)))
                draft_dependencies.append("knowledge")
            if needs_booking:
                planned.append(PlanStep("booking", "Booking", ("triage",)))
                draft_dependencies.append("booking")
            if not draft_dependencies:
                draft_dependencies.append("triage")
            planned.extend(
                (
                    PlanStep("draft", "Communications", tuple(draft_dependencies)),
                    PlanStep("compliance", "Compliance", ("draft",)),
                )
            )
            steps = tuple(planned)
        plan = CasePlan(steps, langfuse_trace_id=trace_id)
        langfuse.update_current_span(
            output={
                "steps": [step.key for step in plan.steps],
                "roles": [step.role for step in plan.steps],
            }
        )
        return plan
