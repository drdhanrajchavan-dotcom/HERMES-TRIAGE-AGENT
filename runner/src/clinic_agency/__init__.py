"""Clinic agency runner."""

from pathlib import Path

from dotenv import load_dotenv

# Langfuse initializes from environment variables when first imported. Load the
# project environment before any adapter or orchestration module imports it.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")
