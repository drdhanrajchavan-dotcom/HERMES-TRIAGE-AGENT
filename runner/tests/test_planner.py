from clinic_agency.domain.cases import Case
from clinic_agency.orchestration.planner import ManagerPlanner


def step_keys(plan) -> list[str]:
    return [step.key for step in plan.steps]


def test_manager_planner_is_langfuse_instrumented() -> None:
    assert hasattr(ManagerPlanner.plan, "__wrapped__")


def test_pricing_plan_routes_through_knowledge_draft_and_compliance() -> None:
    case = Case.from_telegram(1, 99, "How much is laser hair removal?")

    plan = ManagerPlanner().plan(case)

    assert step_keys(plan) == ["triage", "knowledge", "draft", "compliance"]
    assert plan.steps[-1].depends_on == ("draft",)


def test_booking_plan_has_structurally_distinct_calendar_branch() -> None:
    case = Case.from_telegram(2, 99, "What is the price and can I come Saturday?")

    plan = ManagerPlanner().plan(case)

    assert step_keys(plan) == ["triage", "knowledge", "booking", "draft", "compliance"]
    assert plan.steps[2].role == "Booking"
    assert plan.steps[3].depends_on == ("knowledge", "booking")


def test_red_flag_plan_escalates_without_booking_or_knowledge() -> None:
    case = Case.from_telegram(3, 99, "Swollen and fever", ("swollen", "fever"))

    plan = ManagerPlanner().plan(case)

    assert step_keys(plan) == ["triage", "escalation", "draft", "compliance"]
    assert "booking" not in step_keys(plan)
    assert "knowledge" not in step_keys(plan)
