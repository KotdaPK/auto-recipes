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
    NOTION_TOKEN: str | None = _get("NOTION_TOKEN")
    RECIPES_DB_ID: str | None = _get("RECIPES_DB_ID")
    INGREDIENTS_DB_ID: str | None = _get("INGREDIENTS_DB_ID")
    RECIPE_ING_DB_ID: str | None = _get("RECIPE_ING_DB_ID")
    MEALS_DB_ID: str | None = _get("MEALS_DB_ID")
    GROCERY_LINES_DB_ID: str | None = _get("GROCERY_LINES_DB_ID")

    # Notion property names (defaults chosen to common names)
    P_RECIPE_TITLE: str = _get("P_RECIPE_TITLE", "Name")
    P_RECIPE_SOURCE_URL: str = _get("P_RECIPE_SOURCE_URL", "Source")
    P_MEAL_WHEN: str = _get("P_MEAL_WHEN", "When")
    P_MEAL_TYPE: str = _get("P_MEAL_TYPE", "Meal Type")
    P_MEAL_PLANNED_SERVINGS: str = _get("P_MEAL_PLANNED_SERVINGS", "Planned Servings")
    P_MEAL_GOOGLE_EVENT_ID: str = _get("P_MEAL_GOOGLE_EVENT_ID", "Google Event ID")
    P_RECIPING_QTY_PER_SERVING: str = _get("P_RECIPING_QTY_PER_SERVING", "Qty per Serving")
    P_GROCERY_WEEK: str = _get("P_GROCERY_WEEK", "Week Start")
    P_GROCERY_QTY: str = _get("P_GROCERY_QTY", "Needed Qty")
    P_GROCERY_ING_REL: str = _get("P_GROCERY_ING_REL", "Ingredient")
    P_GROCERY_FROM_MEAL: str = _get("P_GROCERY_FROM_MEAL", "From Meal")

    # Google Calendar
    GCAL_CALENDAR_ID: str = _get("GCAL_CALENDAR_ID", "primary")
    LOCAL_TZ: str = _get("LOCAL_TZ", "UTC")
    # Optional ingredient properties in the Ingredients DB
    P_ING_UNIT: str = _get("P_ING_UNIT", "Unit")
    P_ING_NOTES: str = _get("P_ING_NOTES", "Notes")
    # Ingredient DB property keys (customizable)
    P_ING_TITLE: str = _get("P_ING_TITLE", "Name")
    P_ING_RAW: str = _get("P_ING_RAW", "Raw")
    P_ING_QTY: str = _get("P_ING_QTY", "Quantity")
    P_ING_RECIPES_REL: str = _get("P_ING_RECIPES_REL", "Recipes")

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
    if not os.getenv("NOTION_TOKEN"):
        missing.append("NOTION_TOKEN (Notion integration token)")
    if not os.getenv("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY (Gemini / Google Generative AI key)")
    if missing:
        msg = (
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\nPlease set them in your .env or environment and try again."
        )
        raise RuntimeError(msg)