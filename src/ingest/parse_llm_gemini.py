"""
Gemini 2.5 Flash recipe parser with flattened response schema.
"""

from __future__ import annotations
import json
import logging
from typing import Optional
from pydantic import ValidationError
from src.models.recipe_schema import RecipePayload
from src.settings import settings, RECIPE_RESPONSE_SCHEMA

logger = logging.getLogger(__name__)

# Try to import jsonschema for strict JSON Schema validation; fall back if unavailable
try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except Exception:
    _HAS_JSONSCHEMA = False


def _build_prompt(text: str, url: Optional[str]) -> str:
    # Strongly require 'notes' to be filled where any preparation, parenthetical, or alternative text exists.
    # If none apply, explicitly set notes to an empty string "" in the JSON output.
    return "\n\n".join([
        "Extract exactly ONE cooking recipe from PAGE_TEXT into the provided JSON schema.",
        "- Normalize ingredient names to common grocery terms (no brands).",
        "- Number the steps in order starting from 1.",
        "- Parse quantities/units if present; leave null if not determinable.",
        "- For each ingredient, ALWAYS include a 'notes' string. Put preparation methods, descriptors, parenthetical alternatives, and optional swaps into 'notes' (e.g., 'drained', 'minced', 'roughly chopped', 'or chicken broth').",
        "- If a descriptor changes the ingredient identity (e.g., 'unsalted butter'), include that descriptor in the 'name' instead of notes.",
        "- If no notes apply, set notes to an empty string: \"\".",
        "- Do NOT invent data not present in PAGE_TEXT; copy descriptors/alternatives verbatim into notes where present.",
        "- Use standard abbreviations: tbsp, tsp, oz, lb, g, kg, ml, l.",
        "- Keep steps short imperative sentences.",
        "Example ingredient JSON entries (illustrative, non-exhaustive):",
        '[{"raw":"1/2 cup dry white wine (or chicken broth)", "name":"dry white wine", "quantity":0.5, "unit":"cup", "notes":"or chicken broth"}]',
        f"SOURCE_URL: {url or ''}",
        "PAGE_TEXT:",
        text[:120000],
    ])

def parse_recipe_text(text: str, url: Optional[str] = None) -> RecipePayload:
    """Parse text using Gemini 2.5 structured output."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured.")

    # Lazy import to avoid hard dependency at module import time during tests
    try:
        import google.generativeai as genai
    except Exception as e:
        raise RuntimeError(
            "google.generativeai is required to call the Gemini API: " + str(e)
        )

    genai.configure(api_key=settings.GEMINI_API_KEY)

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

        # Quick schema alignment check (JSON Schema) and log a warning if it fails
        if data is not None:
            if _HAS_JSONSCHEMA:
                try:
                    jsonschema.validate(instance=data, schema=RECIPE_RESPONSE_SCHEMA)
                except Exception as e:
                    logger.warning("Gemini response does not align with RECIPE_RESPONSE_SCHEMA: %s", e)
            else:
                logger.debug("jsonschema not installed; skipping strict schema validation")

        try:
            recipe = RecipePayload.model_validate(data)
            if url and not recipe.source_url:
                recipe.source_url = url
            logger.info("Parsed recipe: %s", recipe.title)
            logger.debug("Parsed recipe payload: %s", json.dumps(recipe.model_dump(), ensure_ascii=False, indent=2))
            return recipe
        except ValidationError as e:
            logger.warning("Pydantic validation failed for Gemini output: %s", e)
            if attempt == 0:
                logger.info("Retrying Gemini parsing once more due to validation error.")
                continue
            raise ValueError(f"Gemini output failed validation: {e}")
