"""Orchestrator helpers: minimal functions used by scripts and tests.

This file intentionally keeps implementations small and dependency-light so
unit tests and helper scripts can import `url_to_recipe` without pulling in
complex, duplicated code paths.
"""

from __future__ import annotations

import os
import json
import logging
from rich.console import Console

from src.ingest.fetch import fetch_url
from src.ingest.extract_text import extract_main_text
from src.ingest.parse_llm_gemini import parse_recipe_text
from src.dedup.embed_index import EmbedIndex
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
console = Console()


def url_to_recipe(url: str) -> dict:
    """Fetch a URL, extract text, call parser, and write simple audit artifacts.

    Returns a JSON-serializable dict representing the parsed recipe.
    """
    logger.info("Ingesting: %s", url)
    html, final = fetch_url(url)
    text = extract_main_text(html, final)
    try:
        # pass raw html so the parser can extract JSON-LD and include it in the prompt
        recipe = parse_recipe_text(text, final, html=html)
    except Exception as exc:  # fallback when LLM/config not present
        logger.debug("LLM parse failed (%s); using fallback stub recipe", exc)

        class _StubRecipe:
            def __init__(self, title: str | None = None):
                self.title = title or "unknown"
                self.servings = None
                self.ingredients = []

            def model_dump_json(self, **_kwargs):
                return json.dumps({"title": self.title, "servings": self.servings, "ingredients": self.ingredients})

        recipe = _StubRecipe(title=None)

    # small optional index build (no-op if file missing)
    try:
        names_path = os.path.join("data", "ingredients.names.json")
        if os.path.exists(names_path):
            with open(names_path, "r", encoding="utf8") as fh:
                names = json.load(fh)
            idx = EmbedIndex()
            idx.build(names)
    except Exception:
        logger.debug("Ingredient index unavailable; continuing")

    # persist artifacts (with post-processing: convert nulls to "-")
    def _normalize_nulls(obj):
        """Recursively replace None with '-' in a JSON-like object."""
        if isinstance(obj, dict):
            return {k: _normalize_nulls(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_normalize_nulls(v) for v in obj]
        if obj is None:
            return "-"
        return obj

    try:
        os.makedirs("data/ingests", exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_title = (getattr(recipe, "title", "recipe") or "recipe").replace("/", "_")[:80]
        base = f"data/ingests/{ts}_{safe_title}"
        recipe_path = base + "_recipe.json"
        summary_path = base + "_summary.json"

        # Convert recipe to a JSON-serializable dict and normalize nulls for artifacts
        try:
            raw_recipe = json.loads(recipe.model_dump_json())
        except Exception:
            # fallback for stub objects
            raw_recipe = {"title": getattr(recipe, "title", None), "servings": getattr(recipe, "servings", None), "ingredients": getattr(recipe, "ingredients", [])}

        norm_recipe = _normalize_nulls(raw_recipe)
        with open(recipe_path, "w", encoding="utf-8") as f:
            json.dump(norm_recipe, f, ensure_ascii=False, indent=2)

        summary = {"title": raw_recipe.get("title"), "servings": raw_recipe.get("servings"), "ingredient_count": len(raw_recipe.get("ingredients", []))}
        norm_summary = _normalize_nulls(summary)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(norm_summary, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to write ingest artifacts")

    try:
        # Return normalized JSON (with '-' in place of nulls) for API/CLI consumers
        return norm_recipe
    except Exception:
        return {"title": getattr(recipe, "title", None), "summary": summary}


def reindex_ingredients(path_base: str = "data/ingredients") -> None:
    logger.info("Reindexing ingredients from local names file...")
    names = []
    try:
        names_path = os.path.join("data", "ingredients.names.json")
        if os.path.exists(names_path):
            with open(names_path, "r", encoding="utf8") as fh:
                names = json.load(fh)
    except Exception:
        logger.exception("Failed to load ingredient names file; skipping reindex")
        return
    idx = EmbedIndex()
    idx.build(names)
    os.makedirs(os.path.dirname(path_base), exist_ok=True)
    idx.save(path_base)


def sync_meals(days_ahead: int = 10, default_duration: int = 45) -> None:
    console.print(f"Syncing meals for next {days_ahead} days (duration={default_duration})")
    console.print("Not implemented full sync in this minimal example.")
