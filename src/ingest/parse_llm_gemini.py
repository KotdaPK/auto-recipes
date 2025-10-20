"""
Call Gemini 2.5 Flash to parse recipe text into RecipePayload using structured JSON output.

This version uses the modern google-generativeai API (>= 0.8.5) with the
`GenerativeModel(...).generate_content()` call and a `response_schema`
for guaranteed JSON compliance.
"""

from __future__ import annotations

import json
from typing import Optional
from pydantic import ValidationError

import google.generativeai as genai
from src.models.recipe_schema import RecipePayload
from src.settings import settings


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

genai.configure(api_key=settings.GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(text: str, url: Optional[str]) -> str:
    """Assemble the instruction + source + text into one clean prompt."""
    instruction = (
        "Extract exactly ONE cooking recipe from PAGE_TEXT into the provided JSON schema.\n"
        "- Normalize ingredient names to common grocery terms (no brands).\n"
        "- Parse quantities/units if present; leave null if not determinable.\n"
        "- Keep steps as concise imperative sentences.\n"
        "- Do NOT invent data not in PAGE_TEXT.\n"
    )
    parts = [instruction, f"SOURCE_URL: {url or ''}", "PAGE_TEXT:", text[:120000]]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_recipe_text(text: str, url: Optional[str] = None) -> RecipePayload:
    """
    Use Gemini 2.5 Flash to parse raw recipe text into a validated RecipePayload.
    Retries once on validation failure, otherwise raises ValueError.
    """
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("Gemini API key not configured (GEMINI_API_KEY).")

    prompt = _build_prompt(text, url)

    # Use the Pydantic schema to derive a response schema for Gemini
    response_schema = RecipePayload.model_json_schema()

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config={
            "temperature": 0,
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        },
    )

    for attempt in range(2):
        response = model.generate_content([prompt])

        # Gemini structured output returns parsed JSON directly at .parsed
        data = None
        if hasattr(response, "parsed") and response.parsed is not None:
            data = response.parsed
        else:
            # Fallback: try to parse raw text
            try:
                raw = response.text or response.candidates[0].content.parts[0].text
                data = json.loads(raw)
            except Exception as e:
                raise ValueError("Could not extract JSON from Gemini response") from e

        try:
            recipe = RecipePayload.model_validate(data)
            if url and not recipe.source_url:
                recipe.source_url = url
            return recipe
        except ValidationError as e:
            if attempt == 0:
                continue
            raise ValueError(f"Gemini output failed validation: {e}") from e
