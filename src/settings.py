"""Application settings loaded from environment (and .env).

This module provides a small Settings holder backed by environment variables.
Keep this file simple and import `settings` from other modules.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import json
from pathlib import Path

# Load the JSON schema from file so it can be edited without touching code.
_schema_path = Path(__file__).parent / "schemas" / "recipe_response_schema.json"
if _schema_path.exists():
    with open(_schema_path, "r", encoding="utf8") as _fh:
        RECIPE_RESPONSE_SCHEMA = json.load(_fh)
else:
    RECIPE_RESPONSE_SCHEMA = {}


def _get(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None:
        return default
    return v


@dataclass
class Settings:
    # API keys
    GEMINI_API_KEY: str | None = _get("GEMINI_API_KEY")

    # Notion
    # External integrations (optional)
    # Notion-related DB ids and tokens were removed; Notion is optional and
    # any required integration keys should be provided explicitly by the
    # operator when enabling those sinks.

    # Google Calendar
    GCAL_CALENDAR_ID: str = _get("GCAL_CALENDAR_ID", "primary")
    LOCAL_TZ: str = _get("LOCAL_TZ", "UTC")
    # Optional ingredient properties (if external sinks are enabled)
    P_ING_UNIT: str = _get("P_ING_UNIT", "Unit")
    P_ING_NOTES: str = _get("P_ING_NOTES", "Notes")

    # Logging configuration
    # LOG_LEVEL can be DEBUG, INFO, WARNING, ERROR, or CRITICAL
    LOG_LEVEL: str = _get("LOG_LEVEL", "INFO")
    # Optional path to write logs to a file; if unset, logs go to stderr
    LOG_FILE: str | None = _get("LOG_FILE", None)


settings = Settings()

# RECIPE_RESPONSE_SCHEMA is loaded above and exposed from this module.


def validate_required() -> None:
    """Validate required secrets and raise a helpful RuntimeError if missing.

    This function checks environment variables at runtime so callers can load a .env first.
    """
    missing = []
    if not os.getenv("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY (Gemini / Google Generative AI key)")
    if missing:
        msg = (
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\nPlease set them in your .env or environment and try again."
        )
        raise RuntimeError(msg)