from typing import Any

from pydantic import BaseModel, Field, model_validator


class TelegramChat(BaseModel):
    id: int


class TelegramVoice(BaseModel):
    file_id: str = Field(min_length=1, max_length=512)
    file_size: int | None = Field(default=None, ge=1)


class TelegramMessage(BaseModel):
    chat: TelegramChat
    text: str | None = Field(default=None, min_length=1, max_length=4096)
    voice: TelegramVoice | None = None

    @model_validator(mode="after")
    def require_supported_content(self) -> "TelegramMessage":
        if self.text is None and self.voice is None:
            raise ValueError("Telegram message must contain text or a voice note")
        return self


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage

    model_config = {"extra": "ignore"}


def extract_update(payload: dict[str, Any]) -> TelegramUpdate:
    return TelegramUpdate.model_validate(payload)
