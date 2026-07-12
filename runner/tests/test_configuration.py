import pytest
from pydantic import ValidationError

from clinic_agency.config import Settings
from clinic_agency.main import configured_app
from clinic_agency.orchestration.telegram_reply import IntelligentTelegramReplyWorkflow


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


def test_model_configuration_uses_normalized_model_environment_names(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", "model-secret")
    monkeypatch.setenv("MODEL_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("TELEGRAM_REPLY_MODEL", "gpt-reply")

    settings = Settings(_env_file=None)

    assert settings.model_api_key == "model-secret"
    assert settings.model_base_url == "https://model.example/v1"
    assert settings.telegram_reply_model == "gpt-reply"


def test_production_requires_live_reply_model_provider_configuration() -> None:
    settings = Settings(
        app_env="production",
        convex_url="https://example.convex.cloud",
        internal_api_secret="internal-secret",
        langfuse_public_key="public",
        langfuse_secret_key="secret",
        langfuse_host="https://langfuse.example",
        telegram_bot_token="telegram-token",
        telegram_webhook_secret="telegram-secret",
        webhook_shared_secret="edge-secret",
        linkup_api_key="linkup-secret",
        google_calendar_id="calendar-id",
        model_api_key="",
        model_base_url="",
        telegram_reply_model="",
        _env_file=None,
    )

    with pytest.raises(RuntimeError) as error:
        configured_app(settings)

    message = str(error.value)
    assert "MODEL_API_KEY" in message
    assert "MODEL_BASE_URL" in message
    assert "TELEGRAM_REPLY_MODEL" in message


def test_live_composition_installs_intelligent_workflow(monkeypatch) -> None:
    class Store:
        pass

    monkeypatch.setattr("clinic_agency.main.ConvexCaseStore", lambda *args, **kwargs: Store())
    monkeypatch.setattr("clinic_agency.main.ConvexHoldStore", lambda *args, **kwargs: object())
    monkeypatch.setattr("clinic_agency.main.GoogleCalendarClient", lambda *args, **kwargs: object())
    monkeypatch.setattr("clinic_agency.main.CalendarService", lambda *args, **kwargs: object())
    monkeypatch.setattr("clinic_agency.main.TelegramSender", lambda *args, **kwargs: object())
    monkeypatch.setattr("clinic_agency.main.create_openai_client", lambda settings: object())
    settings = Settings(
        convex_url="https://example.convex.cloud",
        internal_api_secret="internal-secret",
        telegram_bot_token="telegram-token",
        telegram_webhook_secret="telegram-secret",
        linkup_api_key="linkup-secret",
        google_calendar_id="calendar-id",
        model_api_key="model-secret",
        model_base_url="https://model.example/v1",
        telegram_reply_model="gpt-reply",
        _env_file=None,
    )

    app = configured_app(settings)

    assert isinstance(app.state.outbound_workflow, IntelligentTelegramReplyWorkflow)
    assert app.state.outbound_workflow.role.prompt_ref.name == "roles/telegram-reply"
    assert app.state.outbound_workflow.role.prompt_ref.label == "production"
    assert app.state.outbound_workflow.role.tools == ("calendar.read", "calendar.hold")



def test_voice_is_disabled_safely_until_required_credentials_are_configured() -> None:
    settings = Settings(_env_file=None)

    assert settings.voice_enabled is False
    assert settings.elevenlabs_stt_model_id == "scribe_v1"
    assert settings.elevenlabs_tts_model_id == "eleven_multilingual_v2"
    assert settings.elevenlabs_output_format == "mp3_44100_128"
    assert settings.elevenlabs_agent_id == ""


def test_voice_is_enabled_only_with_server_key_and_voice_id() -> None:
    settings = Settings(
        elevenlabs_api_key="server-key",
        elevenlabs_voice_id="voice-id",
        _env_file=None,
    )

    assert settings.voice_enabled is True
