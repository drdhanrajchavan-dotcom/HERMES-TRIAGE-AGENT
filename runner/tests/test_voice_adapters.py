from __future__ import annotations

import httpx
import pytest

from clinic_agency.adapters.voice import (
    ElevenLabsVoiceAdapter,
    TelegramVoiceNote,
    TelegramVoiceNoteDownloader,
    VoiceConfigurationError,
    VoiceReply,
)


def mock_client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_elevenlabs_transcribes_audio_with_current_multipart_contract() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.elevenlabs.io/v1/speech-to-text"
        assert request.headers["xi-api-key"] == "server-secret"
        body = request.read()
        assert b'name="model_id"' in body
        assert b"scribe_v1" in body
        assert b'name="file"; filename="voice.ogg"' in body
        assert b"audio/ogg" in body
        return httpx.Response(200, json={"text": "Namaste, I need an appointment."})

    adapter = ElevenLabsVoiceAdapter(
        api_key="server-secret",
        voice_id="voice-123",
        stt_model_id="scribe_v1",
        tts_model_id="eleven_multilingual_v2",
        client=mock_client(httpx.MockTransport(handle)),
    )

    assert adapter.transcribe(b"OggS-audio", filename="voice.ogg", content_type="audio/ogg") == (
        "Namaste, I need an appointment."
    )


def test_elevenlabs_synthesizes_human_brain_output_without_agent_api() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "https://api.elevenlabs.io/v1/text-to-speech/voice-123"
            "?output_format=mp3_44100_128"
        )
        assert request.headers["accept"] == "audio/mpeg"
        assert request.headers["xi-api-key"] == "server-secret"
        assert request.method == "POST"
        assert request.content == (
            b'{"text":"Approved Hermes reply","model_id":"eleven_multilingual_v2"}'
        )
        return httpx.Response(200, content=b"ID3-audio", headers={"content-type": "audio/mpeg"})

    adapter = ElevenLabsVoiceAdapter(
        api_key="server-secret",
        voice_id="voice-123",
        stt_model_id="scribe_v1",
        tts_model_id="eleven_multilingual_v2",
        agent_id="optional-agent-not-used",
        client=mock_client(httpx.MockTransport(handle)),
    )

    reply = adapter.synthesize("Approved Hermes reply")

    assert reply == VoiceReply(audio=b"ID3-audio", filename="reply.mp3", content_type="audio/mpeg")


def test_voice_adapter_rejects_missing_config_before_network() -> None:
    transport = httpx.MockTransport(lambda _: pytest.fail("network called"))
    adapter = ElevenLabsVoiceAdapter(api_key="", voice_id="", client=mock_client(transport))

    with pytest.raises(VoiceConfigurationError, match="ELEVENLABS_API_KEY"):
        adapter.transcribe(b"audio", filename="voice.ogg", content_type="audio/ogg")


def test_voice_adapter_rejects_empty_or_oversized_inputs() -> None:
    adapter = ElevenLabsVoiceAdapter(api_key="key", voice_id="voice", max_audio_bytes=4)

    with pytest.raises(ValueError, match="empty"):
        adapter.transcribe(b"", filename="voice.ogg", content_type="audio/ogg")
    with pytest.raises(ValueError, match="maximum"):
        adapter.transcribe(b"12345", filename="voice.ogg", content_type="audio/ogg")
    with pytest.raises(ValueError, match="empty"):
        adapter.synthesize("  ")


def test_provider_errors_are_sanitized_and_do_not_leak_api_key() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(401, text="server-secret invalid")
    )
    client = mock_client(transport)
    adapter = ElevenLabsVoiceAdapter(api_key="server-secret", voice_id="voice", client=client)

    with pytest.raises(RuntimeError, match="ElevenLabs speech-to-text request failed") as error:
        adapter.transcribe(b"audio", filename="voice.ogg", content_type="audio/ogg")

    assert "server-secret" not in str(error.value)


def test_telegram_download_resolves_file_then_downloads_voice_note() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/getFile"):
            assert request.url.params["file_id"] == "telegram-file-id"
            return httpx.Response(
                200, json={"ok": True, "result": {"file_path": "voice/file_1.oga"}}
            )
        assert request.url.path.endswith("/file/botbot-token/voice/file_1.oga")
        return httpx.Response(200, content=b"OggS")

    downloader = TelegramVoiceNoteDownloader(
        bot_token="bot-token",
        client=mock_client(httpx.MockTransport(handle)),
        max_audio_bytes=10,
    )

    result = downloader.download("telegram-file-id")

    assert result == TelegramVoiceNote(
        audio=b"OggS", filename="file_1.oga", content_type="audio/ogg"
    )
    assert len(requests) == 2


def test_telegram_download_rejects_missing_token_bad_paths_and_large_files() -> None:
    missing = TelegramVoiceNoteDownloader(bot_token="")
    with pytest.raises(VoiceConfigurationError, match="TELEGRAM_BOT_TOKEN"):
        missing.download("id")

    bad_path_client = mock_client(
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"ok": True, "result": {"file_path": "../secret"}})
        )
    )
    with pytest.raises(RuntimeError, match="unsafe file path"):
        TelegramVoiceNoteDownloader(bot_token="token", client=bad_path_client).download("id")

    def large(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "voice/a.ogg"}})
        return httpx.Response(200, content=b"12345")

    with pytest.raises(ValueError, match="maximum"):
        TelegramVoiceNoteDownloader(
            bot_token="token",
            client=mock_client(httpx.MockTransport(large)),
            max_audio_bytes=4,
        ).download("id")
