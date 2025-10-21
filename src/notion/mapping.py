"""Map RecipePayload into Notion pages and junction rows."""

from __future__ import annotations

from typing import Dict

from src.models.recipe_schema import RecipePayload
from src.notion import io as notion_io
from src.dedup.canonicalize import canonicalize, extract_description_and_name
import logging

logger = logging.getLogger(__name__)


def map_and_upsert(recipe: RecipePayload, index, threshold: float = 0.92) -> Dict:
    """Upsert recipe, ingredients, and junctions. Returns a summary dict."""
    summary = {
        "recipe": None,
        "ingredients": [],
        "junctions": [],
    }

    title = recipe.title
    recipe_page_id, created = notion_io.upsert_recipe(title, recipe.source_url)
    summary["recipe"] = {"page_id": recipe_page_id, "created": created}

    # load existing ingredient names
    existing = notion_io.list_ingredients()
    existing_names = set(existing.keys())

    for ing in recipe.ingredients:
        # Use the JSON fields directly. Do not canonicalize or extract.
        # Build match input inline (prefer parsed name, fall back to raw)
        match_input = getattr(ing, "name", None) or getattr(ing, "raw", None) or ""
        try:
            status, matched_name, score = index.match_or_create(match_input, existing_names, index, threshold)
            logger.debug("match_or_create result for '%s': %s (score=%s)", match_input, status, score)
        except Exception:
            # best-effort fallback: treat as new
            status, matched_name, score = "new", match_input, 0.0

        if status == "existing":
            page_id = existing.get(matched_name)
            created_flag = False
            if not page_id:
                page_id, created_flag = notion_io.upsert_ingredient(matched_name)
                existing[matched_name] = page_id
        else:
            # create ingredient page, include raw/quantity/unit/notes by passing fields directly
            page_id, created_flag = notion_io.upsert_ingredient(
                matched_name or match_input,
                raw=getattr(ing, "raw", None),
                quantity=getattr(ing, "quantity", None),
                unit=getattr(ing, "unit", None),
                notes=getattr(ing, "notes", None),
            )
            existing[matched_name or match_input] = page_id

        logger.info("ingredient mapped: %s -> %s (created=%s, score=%s)", matched_name or match_input, page_id, created_flag, score)

        # Put all ingredient properties directly into the summary without aliasing
        try:
            ing_dict = ing.model_dump()
        except Exception:
            # fallback for plain dict-like objects
            ing_dict = dict(ing)

        ing_dict.update({"page_id": page_id, "created": created_flag, "score": score})
        summary["ingredients"].append(ing_dict)

        # create junction row for this ingredient
        try:
            j_page = notion_io.upsert_recipe_ingredient(recipe_page_id, page_id, getattr(ing, "quantity", None))
            logger.info("junction created: %s linking recipe %s to ingredient %s", j_page, recipe_page_id, page_id)
            summary["junctions"].append({"page_id": j_page, "ingredient": matched_name or match_input})
        except Exception:
            logger.exception("Failed to create junction for recipe %s and ingredient %s", recipe_page_id, page_id)

    return summary
