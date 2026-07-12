import pytest
from pydantic import ValidationError

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


def test_production_requires_langfuse() -> None:
    settings = Settings(
        app_env="production",
        convex_url="https://example.convex.cloud",
        internal_api_secret="internal-secret",
        langfuse_public_key="",
        langfuse_secret_key="",
        telegram_webhook_secret="secret",
        _env_file=None,
    )

    with pytest.raises(RuntimeError, match="LANGFUSE_PUBLIC_KEY"):
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


def test_dodo_environment_is_restricted_to_provider_modes() -> None:
    with pytest.raises(ValidationError):
        Settings(dodo_environment="sandbox", _env_file=None)
