from pathlib import Path
from typing import Literal

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
