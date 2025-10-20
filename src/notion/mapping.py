"""Map RecipePayload into Notion pages and junction rows."""

from __future__ import annotations

from typing import Dict

from src.models.recipe_schema import RecipePayload
from src.notion import io as notion_io
from src.dedup.canonicalize import canonicalize, extract_description_and_name


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
        raw = ing.raw or ing.name
        # attempt to extract a short description (descriptors) and a cleaned name
        description, cleaned = extract_description_and_name(raw)
        can = cleaned or canonicalize(raw)
        status, name, score = index.match_or_create
        # Use provided matcher function: to support both our match_or_create wrapper and index.nearest
        try:
            status, name, score = index.match_or_create(
                raw, existing_names, index, threshold
            )
        except Exception:
            # fallback: if name canonical in existing
            if can in existing_names:
                status, name, score = "existing", can, 1.0
            else:
                status, name, score = "new", can, 0.0

        if status == "existing":
            page_id = existing.get(name)
            created_flag = False
            if not page_id:
                # create and update mapping
                page_id, created_flag = notion_io.upsert_ingredient(name)
                existing[name] = page_id
        else:
            page_id, created_flag = notion_io.upsert_ingredient(name)
            existing[name] = page_id

        summary["ingredients"].append(
            {
                "name": name,
                "page_id": page_id,
                "created": created_flag,
                "score": score,
                "description": description,
            }
        )

        # junction
        qty = ing.quantity
        j_page = notion_io.upsert_recipe_ingredient(recipe_page_id, page_id, qty)
        summary["junctions"].append({"page_id": j_page, "ingredient": name})

    return summary
