from typing import Any

from pydantic import BaseModel, Field


class TelegramChat(BaseModel):
    id: int


class TelegramMessage(BaseModel):
    chat: TelegramChat
    text: str = Field(min_length=1, max_length=4096)


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage

    model_config = {"extra": "ignore"}


def extract_update(payload: dict[str, Any]) -> TelegramUpdate:
    return TelegramUpdate.model_validate(payload)
