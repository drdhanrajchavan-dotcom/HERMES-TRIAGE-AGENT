"""Server-side voice I/O adapters.

The application model/Hermes remains the authoritative conversation brain. This
module only turns Telegram audio into text and already-approved reply text into
audio; it never calls the ElevenLabs conversational-agent API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
TELEGRAM_BASE_URL = "https://api.telegram.org"
DEFAULT_MAX_AUDIO_BYTES = 25 * 1024 * 1024


class VoiceConfigurationError(RuntimeError):
    """Voice functionality was invoked without its optional configuration."""


@dataclass(frozen=True)
class TelegramVoiceNote:
    audio: bytes
    filename: str
    content_type: str


@dataclass(frozen=True)
class VoiceReply:
    audio: bytes
    filename: str = "reply.mp3"
    content_type: str = "audio/mpeg"


class ElevenLabsVoiceAdapter:
    """Thin, synchronous ElevenLabs STT/TTS transport adapter."""

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        *,
        stt_model_id: str = "scribe_v1",
        tts_model_id: str = "eleven_multilingual_v2",
        output_format: str = "mp3_44100_128",
        agent_id: str = "",
        client: httpx.Client | None = None,
        timeout_seconds: float = 30,
        max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    ) -> None:
        self._api_key = api_key.strip()
        self._voice_id = voice_id.strip()
        self._stt_model_id = stt_model_id.strip()
        self._tts_model_id = tts_model_id.strip()
        self._output_format = output_format.strip()
        # Kept as deployment metadata only. It is deliberately never sent by this adapter.
        self.agent_id = agent_id.strip()
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._max_audio_bytes = max_audio_bytes

    def transcribe(self, audio: bytes, *, filename: str, content_type: str) -> str:
        self._require_api_key()
        if not audio:
            raise ValueError("audio is empty")
        if len(audio) > self._max_audio_bytes:
            raise ValueError("audio exceeds configured maximum size")
        if not self._stt_model_id:
            raise VoiceConfigurationError("ELEVENLABS_STT_MODEL_ID is required")

        try:
            response = self._client.post(
                f"{ELEVENLABS_BASE_URL}/speech-to-text",
                headers={"xi-api-key": self._api_key},
                data={"model_id": self._stt_model_id},
                files={"file": (PurePosixPath(filename).name or "voice.ogg", audio, content_type)},
            )
            response.raise_for_status()
            text = response.json().get("text")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise RuntimeError("ElevenLabs speech-to-text request failed") from exc
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("ElevenLabs speech-to-text response contained no transcript")
        return text.strip()

    def synthesize(self, text: str) -> VoiceReply:
        self._require_api_key()
        if not self._voice_id:
            raise VoiceConfigurationError("ELEVENLABS_VOICE_ID is required")
        if not self._tts_model_id:
            raise VoiceConfigurationError("ELEVENLABS_TTS_MODEL_ID is required")
        if not text.strip():
            raise ValueError("text is empty")

        voice_id = quote(self._voice_id, safe="")
        try:
            response = self._client.post(
                f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
                params={"output_format": self._output_format},
                headers={"xi-api-key": self._api_key, "accept": "audio/mpeg"},
                json={"text": text, "model_id": self._tts_model_id},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("ElevenLabs text-to-speech request failed") from exc
        if not response.content:
            raise RuntimeError("ElevenLabs text-to-speech response contained no audio")
        return VoiceReply(audio=response.content)

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise VoiceConfigurationError("ELEVENLABS_API_KEY is required")


class TelegramVoiceNoteDownloader:
    """Resolve and download a Telegram file without exposing the bot token."""

    def __init__(
        self,
        bot_token: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20,
        max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    ) -> None:
        self._bot_token = bot_token.strip()
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._max_audio_bytes = max_audio_bytes

    def download(self, file_id: str) -> TelegramVoiceNote:
        if not self._bot_token:
            raise VoiceConfigurationError("TELEGRAM_BOT_TOKEN is required")
        if not file_id.strip():
            raise ValueError("Telegram file_id is empty")
        try:
            metadata = self._client.get(
                f"{TELEGRAM_BASE_URL}/bot{self._bot_token}/getFile",
                params={"file_id": file_id},
            )
            metadata.raise_for_status()
            payload = metadata.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise RuntimeError("Telegram getFile request failed") from exc
        file_path = payload.get("result", {}).get("file_path") if payload.get("ok") else None
        if not isinstance(file_path, str) or not file_path:
            raise RuntimeError("Telegram getFile response contained no file path")
        path = PurePosixPath(file_path)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError("Telegram returned an unsafe file path")

        try:
            response = self._client.get(
                f"{TELEGRAM_BASE_URL}/file/bot{self._bot_token}/{file_path}"
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Telegram voice-note download failed") from exc
        if len(response.content) > self._max_audio_bytes:
            raise ValueError("Telegram voice note exceeds configured maximum size")
        if not response.content:
            raise RuntimeError("Telegram returned an empty voice note")
        suffix = path.suffix.lower()
        content_type = (
            "audio/ogg" if suffix in {".ogg", ".oga", ".opus"} else "application/octet-stream"
        )
        return TelegramVoiceNote(
            audio=response.content,
            filename=path.name or "voice.ogg",
            content_type=content_type,
        )
