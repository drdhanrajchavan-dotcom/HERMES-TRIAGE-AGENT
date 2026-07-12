import pytest

from clinic_agency.config import Settings
from clinic_agency.main import configured_app


def test_production_requires_convex() -> None:
    settings = Settings(
        app_env="production",
        convex_url="",
        telegram_webhook_secret="secret",
        _env_file=None,
    )

    with pytest.raises(RuntimeError, match="CONVEX_URL"):
        configured_app(settings)


def test_development_can_use_in_memory_store() -> None:
    settings = Settings(
        app_env="development",
        convex_url="",
        telegram_webhook_secret="secret",
        _env_file=None,
    )

    app = configured_app(settings)

    assert app.state.case_store.cases == []
