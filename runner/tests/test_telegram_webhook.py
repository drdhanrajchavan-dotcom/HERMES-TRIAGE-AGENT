from fastapi.testclient import TestClient

from clinic_agency.main import create_app


class RecordingWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[object, int]] = []

    def handle(self, case, chat_id: int):
        self.calls.append((case, chat_id))
        return type("Result", (), {"sent": True})()


class RecordingPlanStore:
    def __init__(self) -> None:
        self.plans: list[tuple[str, object]] = []

    def record_plan(self, external_event_id: str, plan) -> None:
        self.plans.append((external_event_id, plan))


def telegram_update(update_id: int = 101, text: str = "How much is laser treatment?") -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 7,
            "chat": {"id": 99},
            "from": {"id": 99, "first_name": "Synthetic Patient"},
            "text": text,
        },
    }


def test_telegram_webhook_rejects_invalid_secret() -> None:
    client = TestClient(create_app(telegram_webhook_secret="correct-secret"))

    response = client.post(
        "/webhooks/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        json=telegram_update(),
    )

    assert response.status_code == 401


def test_telegram_webhook_is_a_single_observed_case_root() -> None:
    app = create_app(telegram_webhook_secret="correct-secret")
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/webhooks/telegram"
    )

    assert hasattr(endpoint, "__wrapped__")


def test_telegram_webhook_requires_configured_edge_secret() -> None:
    client = TestClient(
        create_app(
            telegram_webhook_secret="telegram-secret",
            webhook_shared_secret="edge-secret",
        )
    )

    missing = client.post(
        "/webhooks/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "telegram-secret"},
        json=telegram_update(),
    )
    accepted = client.post(
        "/webhooks/telegram",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": "telegram-secret",
            "X-Clinic-Edge-Secret": "edge-secret",
        },
        json=telegram_update(),
    )

    assert missing.status_code == 401
    assert accepted.status_code == 202


def test_telegram_webhook_creates_case_once() -> None:
    app = create_app(telegram_webhook_secret="correct-secret")
    client = TestClient(app)
    headers = {"X-Telegram-Bot-Api-Secret-Token": "correct-secret"}

    first = client.post("/webhooks/telegram", headers=headers, json=telegram_update())
    replay = client.post("/webhooks/telegram", headers=headers, json=telegram_update())

    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    assert replay.status_code == 200
    assert replay.json() == {"status": "duplicate", "update_id": 101}
    assert len(app.state.case_store.cases) == 1
    assert app.state.case_store.cases[0].patient_external_id == "telegram:99"


def test_telegram_webhook_marks_red_flag_before_agent_planning() -> None:
    app = create_app(telegram_webhook_secret="correct-secret")
    client = TestClient(app)

    response = client.post(
        "/webhooks/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
        json=telegram_update(text="My face is swollen and hot and I have a fever"),
    )

    assert response.status_code == 202
    assert response.json()["must_escalate"] is True
    case = app.state.case_store.cases[0]
    assert case.must_escalate is True
    assert set(case.red_flags) == {"fever", "hot", "swollen"}


def test_telegram_webhook_runs_safe_outbound_workflow_once() -> None:
    workflow = RecordingWorkflow()
    app = create_app(
        telegram_webhook_secret="correct-secret",
        outbound_workflow=workflow,
    )
    client = TestClient(app)
    headers = {"X-Telegram-Bot-Api-Secret-Token": "correct-secret"}

    first = client.post("/webhooks/telegram", headers=headers, json=telegram_update())
    replay = client.post("/webhooks/telegram", headers=headers, json=telegram_update())

    assert first.status_code == 202
    assert first.json()["outbound_sent"] is True
    assert replay.json()["status"] == "duplicate"
    assert len(workflow.calls) == 1
    assert workflow.calls[0][1] == 99


def test_telegram_webhook_records_case_specific_manager_plan() -> None:
    plans = RecordingPlanStore()
    app = create_app(
        telegram_webhook_secret="correct-secret",
        plan_recorder=plans,
    )

    response = TestClient(app).post(
        "/webhooks/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
        json=telegram_update(text="What is the price and can I come Saturday?"),
    )

    assert response.status_code == 202
    assert len(plans.plans) == 1
    event_id, plan = plans.plans[0]
    assert event_id == "telegram:101"
    assert [step.key for step in plan.steps] == [
        "triage",
        "knowledge",
        "booking",
        "draft",
        "compliance",
    ]
