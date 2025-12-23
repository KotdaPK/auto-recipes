"""
Gemini 2.5 Flash recipe parser with flattened response schema.
"""

from __future__ import annotations
import json
import logging
from typing import Optional
from datetime import datetime, timezone
import os
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


def _strip_markdown_fence(raw: str) -> str:
    if not raw:
        return raw
    stripped = raw.strip()
    if stripped.startswith("```"):
        content = stripped[3:]
    else:
        fence_start = stripped.find("```")
        if fence_start == -1:
            return raw
        content = stripped[fence_start + 3 :]
    content = content.lstrip()
    if content.lower().startswith("json"):
        content = content[4:]
    content = content.lstrip()
    closing = content.rfind("```")
    if closing != -1:
        content = content[:closing]
    return content.strip() or raw


def _extract_json_fragment(raw: str) -> str | None:
    start = None
    depth = 0
    in_string = False
    escape = False
    best: tuple[int, int] | None = None
    for idx, ch in enumerate(raw):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0 and start is not None:
                    if best is None or (idx - start) > (best[1] - best[0]):
                        best = (start, idx + 1)
    if best is None:
        return None
    return raw[best[0] : best[1]]


def _parse_candidate_json(raw: str) -> dict | None:
    candidates: list[str] = []

    def _add(value: str | None) -> None:
        if not value:
            return
        if value not in candidates:
            candidates.append(value)

    stripped = raw.strip()
    fenced = _strip_markdown_fence(raw)
    _add(fenced)
    _add(stripped)
    fragment = _extract_json_fragment(raw)
    _add(fragment)

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _extract_response_text(resp) -> str | None:
    for attr in ("text", "output_text"):
        raw = getattr(resp, attr, None)
        if raw:
            return raw
    candidates = getattr(resp, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if content is None:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text_value = getattr(part, "text", None)
            if text_value:
                return text_value
            if isinstance(part, str):
                return part
            # some SDK parts expose .inline_data -> skip for now
    return None


def _build_prompt(text: str, url: Optional[str], schema, page_json_ld: Optional[str] = None) -> str:
    # Strongly require 'notes' to be filled where any preparation, parenthetical, or alternative text exists.
    # If none apply, explicitly set notes to an empty string "" in the JSON output.
    return "\n\n".join([
        f"SOURCE_URL: {url or ''}",
        "Extract exactly ONE cooking recipe from the website into the provided JSON schema.",
        "- Normalize ingredient names to common grocery terms; no brands and .",
        "- Parse quantities/units if present; leave null if not determinable.",
        "- For each ingredient, ALWAYS include a 'notes' string. Put preparation methods, descriptors, parenthetical alternatives, and optional swaps into 'notes' (e.g., 'drained', 'minced', 'roughly chopped', 'or chicken broth').",
        "- If a descriptor changes the ingredient identity (e.g., 'unsalted butter'), include that descriptor in the 'name' instead of notes.",
        "- If no notes apply, set notes to an empty string: \"\".",
        "- Do NOT invent data not present in the website; copy descriptors/alternatives verbatim into notes where present.",
        "- Use standard abbreviations: tbsp, tsp, oz, lb, g, kg, ml, l.",
        "- Keep steps short imperative sentences.",
        "- Use an empty string \"\" for any text fields you cannot fill from the source and -1 for numeric fields you cannot fill from the source.",
        "Example ingredient JSON entries (illustrative, non-exhaustive):",
        '[{"raw":"1/2 cup dry white wine (or chicken broth)", "name":"dry white wine", "quantity":0.5, "unit":"cup", "notes":"or chicken broth"}]',
    # "PAGE_TEXT:",
    # text[:120000],
    # If available, include the page's JSON-LD Recipe object to help parsing.
    (f"PAGE_JSON_LD: {page_json_ld}" if page_json_ld else ""),
        "OUTPUT JSON SCHEMA:",
        json.dumps(schema, ensure_ascii=False, indent=2),
    ])

def parse_recipe_text(text: str, url: Optional[str] = None, html: Optional[str] = None) -> RecipePayload:
    """Parse text using Gemini 2.5 structured output."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured.")

    # Lazy import to avoid hard dependency at module import time during tests
    try:
        import google.genai as genai
        from google.genai import types
    except Exception as e:
        raise RuntimeError(
            "google.generativeai is required to call the Gemini API: " + str(e)
        )

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Try to extract a Recipe JSON-LD block from the provided HTML (if any)
    page_json_ld = None
    page_json_ld_obj = None
    try:
        if html:
            import re

            def _extract_json_ld_blocks(html_text: str):
                blocks = []
                for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_text, flags=re.S | re.I):
                    body = m.group(1).strip()
                    if not body:
                        continue
                    try:
                        parsed = json.loads(body)
                        if isinstance(parsed, list):
                            blocks.extend(parsed)
                        else:
                            blocks.append(parsed)
                    except Exception:
                        # try to recover common non-JSON wrappers
                        try:
                            # sometimes pages include multiple JSON objects concatenated; try to find first {..}
                            s = body
                            start = s.find('{')
                            end = s.rfind('}')
                            if start != -1 and end != -1:
                                parsed = json.loads(s[start:end+1])
                                blocks.append(parsed)
                        except Exception:
                            continue
                return blocks

            def _find_recipe_object(blocks):
                for obj in blocks:
                    if not isinstance(obj, dict):
                        continue
                    t = obj.get('@type') or obj.get('type')
                    if isinstance(t, list) and 'Recipe' in t:
                        return obj
                    if isinstance(t, str) and t.lower() == 'recipe':
                        return obj
                    # some sites nest recipe under other properties
                    for v in obj.values():
                        if isinstance(v, dict):
                            vt = v.get('@type') or v.get('type')
                            if (isinstance(vt, str) and vt.lower() == 'recipe') or (isinstance(vt, list) and 'Recipe' in vt):
                                return v
                return None

            blocks = _extract_json_ld_blocks(html)
            recipe_obj = _find_recipe_object(blocks)
            if recipe_obj is not None:
                # keep both the dict and a truncated JSON string for the prompt
                page_json_ld_obj = recipe_obj
                page_json_ld = json.dumps(recipe_obj, ensure_ascii=False)
                if len(page_json_ld) > 20000:
                    page_json_ld = page_json_ld[:20000] + '...'
    except Exception:
        logger.debug('Failed to extract JSON-LD from html; continuing')

    prompt = _build_prompt(text, url, RECIPE_RESPONSE_SCHEMA, page_json_ld)
    url_tool = types.Tool(url_context=types.UrlContext())

    for attempt in range(2):
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[url_tool],
                temperature=0,
                # response_mime_type="application/json",
                # response_schema=RECIPE_RESPONSE_SCHEMA,
            ),
        )


        raw = _extract_response_text(resp)
        if not raw:
            raise ValueError("No content from Gemini response.")
        data = _parse_candidate_json(raw)
        if data is None:
            logger.error("Gemini output missing JSON block. Snippet: %s", raw[:200])
            raise ValueError("Failed to parse JSON.")

        # Persist raw Gemini response and (best-effort) parsed JSON for debugging/artifacts
        try:
            os.makedirs("data/gemini", exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            raw_path = f"data/gemini/gemini_{ts}.txt"
            parsed_path = f"data/gemini/gemini_{ts}.json"
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(raw)
            # data may be a Python object; dump as JSON
            with open(parsed_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # also dump a lightweight repr of the full response object for debugging
            try:
                resp_repr_path = f"data/gemini/gemini_{ts}.repr"
                with open(resp_repr_path, "w", encoding="utf-8") as f:
                    f.write(repr(resp))
                logger.info("Wrote Gemini full resp repr -> %s", resp_repr_path)
            except Exception:
                logger.debug("Failed to write Gemini resp repr; continuing")

            logger.info("Wrote Gemini raw response -> %s", raw_path)
            logger.info("Wrote Gemini parsed JSON -> %s", parsed_path)
        except Exception:
            logger.exception("Failed to write Gemini artifacts")

        # data = getattr(resp, "parsed", None)

        if data is None:
            raise ValueError("Failed to parse JSON.")

        # Quick schema alignment check (JSON Schema) and log a warning if it fails
        if data is not None:
            if _HAS_JSONSCHEMA:
                try:
                    jsonschema.validate(instance=data, schema=RECIPE_RESPONSE_SCHEMA)
                except Exception as e:
                    logger.warning("Gemini response does not align with RECIPE_RESPONSE_SCHEMA: %s", e)
            else:
                logger.debug("jsonschema not installed; skipping strict schema validation")

        def _parse_iso8601_minutes(duration: Optional[str]) -> Optional[float]:
            if not duration or not isinstance(duration, str):
                return None
            # Very small ISO8601 PT parser (supports H, M, S)
            import re

            m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration.strip(), flags=re.I)
            if not m:
                return None
            hours = int(m.group(1) or 0)
            minutes = int(m.group(2) or 0)
            seconds = int(m.group(3) or 0)
            total = hours * 60 + minutes + (1 if seconds >= 30 else 0)
            return float(total)

        try:
            recipe = RecipePayload.model_validate(data)
            # If Gemini returned top-level prep_min/cook_min/total_min, merge them into the model
            try:
                if isinstance(data, dict):
                    if getattr(recipe, 'time', None) is None:
                        recipe.time = type(recipe.time)()
                    for key, attr in (('prep_min', 'prep_min'), ('cook_min', 'cook_min'), ('total_min', 'total_min')):
                        if getattr(recipe.time, attr, None) is None and key in data and isinstance(data[key], (int, float)):
                            setattr(recipe.time, attr, float(data[key]))
                    # if total still missing but prep and cook present, sum them
                    try:
                        if (getattr(recipe.time, 'total_min', None) is None) and (getattr(recipe.time, 'prep_min', None) is not None) and (getattr(recipe.time, 'cook_min', None) is not None):
                            recipe.time.total_min = float(recipe.time.prep_min) + float(recipe.time.cook_min)
                    except Exception:
                        pass
            except Exception:
                logger.debug('Failed to merge top-level time keys from Gemini output')

            # If the page provided JSON-LD recipe object, merge missing time/servings from it
            try:
                if page_json_ld_obj is not None:
                    # extract times
                    prep = _parse_iso8601_minutes(page_json_ld_obj.get('prepTime'))
                    cook = _parse_iso8601_minutes(page_json_ld_obj.get('cookTime'))
                    total = _parse_iso8601_minutes(page_json_ld_obj.get('totalTime'))
                    if recipe.time is None:
                        recipe.time = type(recipe.time)()
                    if (recipe.time.prep_min is None or recipe.time.prep_min == None) and prep is not None:
                        recipe.time.prep_min = prep
                    if (recipe.time.cook_min is None or recipe.time.cook_min == None) and cook is not None:
                        recipe.time.cook_min = cook
                    if (recipe.time.total_min is None or recipe.time.total_min == None) and total is not None:
                        recipe.time.total_min = total
                    # if total still missing but prep and cook present, sum them
                    if (recipe.time.total_min is None or recipe.time.total_min == None) and (recipe.time.prep_min is not None) and (recipe.time.cook_min is not None):
                        try:
                            recipe.time.total_min = float(recipe.time.prep_min) + float(recipe.time.cook_min)
                        except Exception:
                            pass
                    # try to parse servings/recipeYield
                    if (recipe.servings is None) and page_json_ld_obj.get('recipeYield'):
                        ry = page_json_ld_obj.get('recipeYield')
                        try:
                            # if numeric
                            if isinstance(ry, (int, float)):
                                recipe.servings = float(ry)
                            elif isinstance(ry, str):
                                import re
                                m = re.search(r"([0-9]+(?:\.[0-9]+)?)", ry)
                                if m:
                                    recipe.servings = float(m.group(1))
                        except Exception:
                            pass
            except Exception:
                logger.debug('Failed to merge JSON-LD times/servings; continuing')
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
