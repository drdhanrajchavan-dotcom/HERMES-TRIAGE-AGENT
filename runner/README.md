# Clinic Agency Runner

FastAPI service for clinic coordination orchestration, safety gates, and integrations.

## Local development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run uvicorn clinic_agency.main:app --reload
```

## Optional Telegram voice I/O

`clinic_agency.adapters.voice` provides integration-only abstractions; it is
intentionally not wired into `main.py`. `TelegramVoiceNoteDownloader` resolves
and downloads Telegram voice files, while `ElevenLabsVoiceAdapter` transcribes
them and synthesizes audio from a reply already generated/approved by the
Hermes/OpenAI workflow. It never delegates reasoning to ElevenLabs Agents.

Copy the voice section from `.env.example`. Required runtime identifiers are an
ElevenLabs Voice ID plus pinned `scribe_v1`, `eleven_multilingual_v2`, and
`mp3_44100_128` model/output settings. `ELEVENLABS_AGENT_ID` is optional metadata
and is not used by the adapter. Keep `ELEVENLABS_API_KEY` server-side. With the
key or voice ID absent, `Settings.voice_enabled` is false and text operation is
unaffected.

## Google Calendar holds (keyless ADC)

The calendar integration uses Google Application Default Credentials with the
`calendar` OAuth scope. It does not accept a service-account JSON key or a JSON
credential environment variable. In Cloud Run, attach the runtime service
account and share the target calendar with that service-account email.

Configuration:

- `GOOGLE_CALENDAR_ID` — shared calendar ID (required when enabling booking)
- `GOOGLE_CALENDAR_TIMEZONE` — IANA timezone; defaults to `Asia/Kolkata`
- `GOOGLE_CALENDAR_HOLD_MINUTES` — tentative hold TTL; defaults to `15`
- `CONVEX_URL` and `INTERNAL_API_SECRET` — hold business-state persistence

For local development, use keyless user ADC or service-account impersonation:

```bash
gcloud auth application-default login
# Or impersonate the deployed identity; do not download a key:
gcloud auth application-default login \
  --impersonate-service-account=clinic-agency-runner@gws-cli-dhanraj-2026.iam.gserviceaccount.com
```

Exact verification commands (they do not print environment values or secrets):

```bash
cd runner
uv sync --locked
uv run pytest tests/test_calendar.py tests/test_calendar_convex.py -q
uv run pytest -q
uv run ruff check src/clinic_agency/calendar tests/test_calendar.py tests/test_calendar_convex.py
cd ..
npx tsc --noEmit
```
