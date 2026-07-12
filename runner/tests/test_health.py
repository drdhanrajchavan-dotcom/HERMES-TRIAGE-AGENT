from fastapi.testclient import TestClient

from clinic_agency.main import app


def test_health_reports_service_ready() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "clinic-agency-runner",
        "status": "ready",
    }


def test_root_explains_that_the_runner_is_an_api() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "clinic-agency-runner",
        "status": "ready",
        "interface": "api",
        "health": "/health",
    }
