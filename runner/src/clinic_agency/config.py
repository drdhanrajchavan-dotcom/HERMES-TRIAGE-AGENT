from pathlib import Path
from typing import Literal

from openai import OpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    convex_url: str = ""
    internal_api_secret: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    webhook_shared_secret: str = ""
    linkup_api_key: str = ""
    dodo_api_key: str = ""
    dodo_webhook_secret: str = ""
    dodo_environment: Literal["test_mode", "live_mode"] = "test_mode"
    dodo_product_id: str = ""
    dodo_currency: str = "INR"
    dodo_deposit_percent: int = 20
    dodo_success_url: str = ""
    dodo_cancel_url: str = ""
    google_calendar_id: str = ""
    google_calendar_timezone: str = "Asia/Kolkata"
    google_calendar_hold_minutes: int = 15
    model_api_key: str = ""
    model_base_url: str = ""
    model_timeout_seconds: float = 30.0
    model_max_retries: int = 0
    telegram_reply_model: str = ""
    telegram_reply_prompt_name: str = "roles/telegram-reply"
    telegram_reply_prompt_label: str = "production"
    telegram_reply_max_cost_usd: float = 0.25
    telegram_reply_input_price_per_million: float = 1.0
    telegram_reply_output_price_per_million: float = 4.0


def create_openai_client(settings: Settings) -> OpenAI:
    """Create the model client only from explicit, validated provider settings."""
    if not settings.model_api_key or not settings.model_base_url:
        raise ValueError("model_api_key and model_base_url are required")
    if settings.model_timeout_seconds <= 0:
        raise ValueError("model_timeout_seconds must be positive")
    if not 0 <= settings.model_max_retries <= 2:
        raise ValueError("model_max_retries must be between 0 and 2")
    return OpenAI(
        api_key=settings.model_api_key,
        base_url=settings.model_base_url,
        timeout=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
    )
