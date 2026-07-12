# Clinic Agency Runner

FastAPI service for clinic coordination orchestration, safety gates, and integrations.

## Local development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run uvicorn clinic_agency.main:app --reload
```
