"""Map RecipePayload into Notion pages and junction rows."""

from __future__ import annotations

from typing import Dict

from src.models.recipe_schema import RecipePayload
from src.notion import io as notion_io
# no canonicalization or description extraction — we use fields directly
import logging

logger = logging.getLogger(__name__)


def map_and_upsert(recipe: RecipePayload, index, threshold: float = 0.92) -> Dict:
    """Upsert recipe, ingredients, and junctions. Returns a summary dict."""
    summary = {
        "recipe": None,
        "ingredients": [],
        "junctions": [],
    }

    # Create or find the recipe page using schema-based upsert
    recipe_page_id, created = notion_io.upsert_recipe(recipe)
    summary["recipe"] = {"page_id": recipe_page_id, "created": created}

    # load existing ingredient names
    existing = notion_io.list_ingredients()
    existing_names = set(existing.keys())

    # First pass: match-or-create key for every ingredient and aggregate duplicates
    aggregated: dict = {}
    for ing in recipe.ingredients:
        match_input = getattr(ing, "name", None) or getattr(ing, "raw", None) or ""
        try:
            status, matched_name, score = index.match_or_create(match_input, existing_names, index, threshold)
        except Exception:
            status, matched_name, score = "new", match_input, 0.0

        key = matched_name or match_input
        # initialize aggregator
        if key not in aggregated:
            aggregated[key] = {
                "name": key,
                "quantity": 0.0,
                "quantity_counted": 0,
                "unit": None,
                "notes": [],
                "raws": [],
                "score": score,
                "orig_items": [],
            }

        entry = aggregated[key]
        q = getattr(ing, "quantity", None)
        if isinstance(q, (int, float)):
            entry["quantity"] += q
            entry["quantity_counted"] += 1
        # prefer first non-empty unit
        u = getattr(ing, "unit", None)
        if not entry["unit"] and u:
            entry["unit"] = u
        # collect notes/raws
        n = getattr(ing, "notes", None)
        if n:
            entry["notes"].append(n)
        r = getattr(ing, "raw", None)
        if r:
            entry["raws"].append(r)
        # take max score
        try:
            entry["score"] = max(entry.get("score", 0.0), float(score))
        except Exception:
            pass
        entry["orig_items"].append(ing)

    # Second pass: upsert a single ingredient & junction per aggregated key
    for key, agg in aggregated.items():
        # prepare merged fields
        merged_raw = "; ".join(dict.fromkeys(agg["raws"])) if agg["raws"] else None
        merged_notes = "; ".join(dict.fromkeys(agg["notes"])) if agg["notes"] else None
        merged_qty = agg["quantity"] if agg["quantity_counted"] > 0 else None
        merged_unit = agg["unit"]

        # upsert ingredient page (store canonical name and raw if available).
        # Do NOT store recipe-specific qty/unit/notes on the ingredient page; those belong on the junction.
        page_id, created_flag = notion_io.upsert_ingredient(
            agg["name"], raw=merged_raw
        )
        logger.info("ingredient mapped (aggregated): %s -> %s (created=%s, score=%s)", agg["name"], page_id, created_flag, agg.get("score"))

        # build summary entry by merging the original items into a representative dict
        # Use the first original item's model_dump as base and then override with merged fields
        try:
            base = agg["orig_items"][0].model_dump()
        except Exception:
            base = dict(agg["orig_items"][0]) if agg["orig_items"] else {}
        base.update({
            "name": agg["name"],
            "raw": merged_raw,
            "quantity": merged_qty,
            "unit": merged_unit,
            "notes": merged_notes,
            "page_id": page_id,
            "created": created_flag,
            "score": agg.get("score", 0.0),
        })
        summary["ingredients"].append(base)

        # create or update junction row for this recipe <-> ingredient
        try:
            j_page = notion_io.upsert_recipe_ingredient(
                recipe_page_id, page_id, merged_qty, unit=merged_unit, notes=merged_notes, raw=merged_raw
            )
            logger.info("junction created: %s linking recipe %s to ingredient %s", j_page, recipe_page_id, page_id)
            summary["junctions"].append({"page_id": j_page, "ingredient": agg["name"]})
        except Exception:
            logger.exception("Failed to create junction for recipe %s and ingredient %s", recipe_page_id, page_id)

    return summary
