"""
Gemini 2.5 Flash recipe parser with flattened response schema.
"""

from __future__ import annotations
import json
from typing import Optional
from pydantic import ValidationError
import google.generativeai as genai
from src.models.recipe_schema import RecipePayload
from src.settings import settings

genai.configure(api_key=settings.GEMINI_API_KEY)


def _build_prompt(text: str, url: Optional[str]) -> str:
    return "\n\n".join([
        "Extract exactly ONE cooking recipe from PAGE_TEXT into the provided JSON schema.",
        "- Normalize ingredient names to common grocery terms (no brands).",
        "- Parse quantities/units if present; leave null if not determinable.",
        "- Keep steps as concise imperative sentences.",
        "- Do NOT invent data not in PAGE_TEXT.",
        f"SOURCE_URL: {url or ''}",
        "PAGE_TEXT:",
        text[:120000],
    ])


# --- define a flat response schema (no $defs/$ref) -----------------
RECIPE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "source_url": {"type": "string"},
        "yield_text": {"type": "string"},
        "servings": {"type": "number"},
        "time": {
            "type": "object",
            "properties": {
                "prep_min": {"type": "number"},
                "cook_min": {"type": "number"},
                "total_min": {"type": "number"},
            },
        },
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw": {"type": "string"},
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["name"],
            },
        },
        "steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "ingredients", "steps"],
}


def parse_recipe_text(text: str, url: Optional[str] = None) -> RecipePayload:
    """Parse text using Gemini 2.5 Flash structured output."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured.")

    prompt = _build_prompt(text, url)
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={
            "temperature": 0,
            "response_mime_type": "application/json",
            "response_schema": RECIPE_RESPONSE_SCHEMA,
        },
    )

    for attempt in range(2):
        resp = model.generate_content([prompt])
        data = getattr(resp, "parsed", None)

        if data is None:
            # fallback: manual JSON parse
            raw = getattr(resp, "text", None) or getattr(resp, "output_text", None)
            if not raw:
                raise ValueError("No content from Gemini response.")
            try:
                data = json.loads(raw)
            except Exception as e:
                # strip junk outside braces
                start, end = raw.find("{"), raw.rfind("}")
                if start != -1 and end != -1:
                    data = json.loads(raw[start:end + 1])
                else:
                    raise ValueError("Failed to parse JSON.") from e

        try:
            recipe = RecipePayload.model_validate(data)
            if url and not recipe.source_url:
                recipe.source_url = url
            print("Parsed recipe:", recipe.model_dump_json(indent=2))
            return recipe
        except ValidationError as e:
            if attempt == 0:
                continue
            raise ValueError(f"Gemini output failed validation: {e}")
