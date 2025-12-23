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
from src.dedup.match import match_or_create
from src.dedup.canonicalize import canonicalize
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
console = Console()
FALLBACK_RECIPE = {"title": "unknown", "servings": "-", "ingredients": []}
EMBED_INDEX_BASE = os.path.join("data", "ingredients")
_EMBED_INDEX_CACHE: EmbedIndex | None = None


def _normalize_nulls(obj):
    """Recursively replace None with '-' in a JSON-like object."""
    if isinstance(obj, dict):
        return {k: _normalize_nulls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_nulls(v) for v in obj]
    if obj is None:
        return "-"
    return obj


def _maybe_refresh_index() -> None:
    names_path = os.path.join("data", "ingredients.names.json")
    if not os.path.exists(names_path):
        return
    try:
        with open(names_path, "r", encoding="utf8") as fh:
            names = json.load(fh)
        idx = EmbedIndex()
        idx.build(names)
    except Exception:
        logger.debug("Ingredient index unavailable; continuing")


def _write_ingest_artifacts(recipe_dict: dict) -> dict:
    os.makedirs("data/ingests", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_title = (recipe_dict.get("title") or "recipe").replace("/", "_")[:80]
    base = f"data/ingests/{ts}_{safe_title}"
    recipe_path = base + "_recipe.json"
    summary_path = base + "_summary.json"

    norm_recipe = _normalize_nulls(recipe_dict)
    with open(recipe_path, "w", encoding="utf-8") as f:
        json.dump(norm_recipe, f, ensure_ascii=False, indent=2)

    summary = {
        "title": recipe_dict.get("title"),
        "servings": recipe_dict.get("servings"),
        "ingredient_count": len(recipe_dict.get("ingredients", [])),
    }
    norm_summary = _normalize_nulls(summary)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(norm_summary, f, ensure_ascii=False, indent=2)

    return norm_recipe


def _load_embed_index(path_base: str = EMBED_INDEX_BASE) -> EmbedIndex | None:
    global _EMBED_INDEX_CACHE
    if _EMBED_INDEX_CACHE is not None:
        return _EMBED_INDEX_CACHE
    names_path = f"{path_base}.names.json"
    vecs_path = f"{path_base}.vecs.npy"
    if not os.path.exists(names_path):
        logger.debug("Ingredient names file %s missing; skipping embedding dedup", names_path)
        return None
    idx = EmbedIndex()
    try:
        if os.path.exists(vecs_path):
            idx.load(path_base)
        else:
            with open(names_path, "r", encoding="utf8") as fh:
                names = json.load(fh)
            if names:
                idx.build(names)
    except Exception:
        logger.exception("Failed to initialize EmbedIndex; skipping dedup")
        return None
    _EMBED_INDEX_CACHE = idx
    return idx


def _dedupe_ingredients(recipe_dict: dict) -> dict:
    ingredients = recipe_dict.get("ingredients") or []
    if not ingredients:
        return recipe_dict
    index = _load_embed_index()
    if index is None:
        for ing in ingredients:
            name = ing.get("name") or ing.get("raw")
            if name:
                ing["name"] = canonicalize(name)
        return recipe_dict

    existing_names = set(index.names)
    new_names: list[str] = []
    for ing in ingredients:
        name = ing.get("name") or ing.get("raw")
        if not name:
            continue
        status, canonical_name, score = match_or_create(name, existing_names, index)
        if canonical_name:
            ing["name"] = canonical_name
        if status == "existing" or not canonical_name:
            continue
        existing_names.add(canonical_name)
        try:
            index.add_name(canonical_name)
            new_names.append(canonical_name)
        except Exception:
            logger.exception("Failed to append '%s' to embedding index", canonical_name)
    if new_names:
        logger.info("Dedup appended %d new ingredient names to index", len(new_names))
        try:
            index.save(EMBED_INDEX_BASE)
        except Exception:
            logger.exception("Failed to persist updated ingredient index")
    recipe_dict["ingredients"] = ingredients
    return recipe_dict


def url_to_recipe(url: str) -> dict:
    """Fetch a URL, extract text, call parser, and write simple audit artifacts.

    Returns a JSON-serializable dict representing the parsed recipe.
    """
    stage = "start"
    raw_recipe: dict | None = None
    logger.info("Ingest start | url=%s", url)
    try:
        stage = "fetch"
        html, final = fetch_url(url)

        stage = "extract"
        text = extract_main_text(html, final)

        stage = "parse"
        recipe = parse_recipe_text(text, final, html=html)
        raw_recipe = recipe.model_dump()

        stage = "dedupe"
        raw_recipe = _dedupe_ingredients(raw_recipe)

        stage = "index"
        _maybe_refresh_index()

        stage = "persist"
        norm_recipe = _write_ingest_artifacts(raw_recipe)

        stage = "complete"
        logger.info(
            "Ingest success | url=%s title=%s ingredients=%d",
            url,
            norm_recipe.get("title"),
            len(norm_recipe.get("ingredients") or []),
        )
        return norm_recipe
    except Exception:
        logger.exception("Ingest failed | url=%s stage=%s", url, stage)
        return FALLBACK_RECIPE.copy()


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
