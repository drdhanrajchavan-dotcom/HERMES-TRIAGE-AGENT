from clinic_agency.domain.roles import Autonomy, PromptRef, RoleConfig
from clinic_agency.orchestration.role_runner import (
    RoleRunner,
    RoleRunResult,
    RoleTask,
)


def test_generic_role_runner_executes_data_driven_role() -> None:
    calls = []

    def execute(role, task):
        calls.append((role, task))
        return RoleRunResult(output={"intent": "pricing"}, cost_usd=0.01)

    role = RoleConfig(
        name="Triage",
        mission="Classify inbound requests",
        prompt_ref=PromptRef(name="triage", label="production"),
        model="gpt-test",
        autonomy=Autonomy.AUTO,
    )
    task = RoleTask(
        case_id="telegram:101",
        task_type="triage",
        input={"message": "private patient content"},
    )

    result = RoleRunner(execute).run(role, task)

    assert result.output == {"intent": "pricing"}
    assert calls == [(role, task)]
    assert hasattr(RoleRunner.run, "__wrapped__")
