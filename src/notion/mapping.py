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
        # Prefer the parsed 'name' field from the LLM; fall back to raw if missing
        parsed_name = getattr(ing, "name", None) or ""
        raw = getattr(ing, "raw", None) or parsed_name

        # Clean the parsed name first; if it yields nothing, fall back to cleaning the raw text
        _, cleaned = extract_description_and_name(parsed_name)
        if not cleaned:
            _, cleaned = extract_description_and_name(raw)
        can = cleaned or canonicalize(parsed_name or raw)

        # Use the parsed name as the primary input to the matcher so the resulting
        # mapped name follows the LLM's 'name' when possible.
        try:
            status, name, score = index.match_or_create(
                parsed_name or raw, existing_names, index, threshold
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
            }
        )

        # junction
        qty = ing.quantity
        # Pass unit/notes when creating the ingredient page so Notion properties
        # can be populated if the DB exposes them.
        unit = getattr(ing, "unit", None)
        notes = getattr(ing, "notes", None)
        # If ingredient page didn't yet exist (we created it above), ensure we set unit/notes
        # by calling upsert_ingredient with those fields (implementations may ignore unknown props).
        if created_flag:
            # created above with name; recreate or update is out of scope for simple upsert
            pass
        else:
            # ensure ingredient exists and set optional fields if needed
            try:
                notion_io.upsert_ingredient(name, unit=unit, notes=notes)
            except Exception:
                # best-effort: continue even if updating optional fields fails
                pass

        j_page = notion_io.upsert_recipe_ingredient(recipe_page_id, page_id, qty)
        summary["junctions"].append({"page_id": j_page, "ingredient": name})

    return summary
