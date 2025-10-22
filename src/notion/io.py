"""Notion I/O helpers: list ingredients, upsert ingredient/recipe/junction rows."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

import logging
from notion_client import Client

from src.settings import settings
import os

logger = logging.getLogger(__name__)

def get_client() -> Client:
  notion_token = os.getenv("NOTION_TOKEN")
  if not notion_token:
    raise RuntimeError("NOTION_TOKEN not configured")
  return Client(auth=notion_token)


def _paginate_query(
    client: Client, database_id: str, filter: Optional[dict] = None
) -> Iterable[dict]:
    start_cursor = None
    while True:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        if filter:
            body["filter"] = filter
        res = client.databases.query(database_id=database_id, **body)
        for r in res.get("results", []):
            yield r
        start_cursor = res.get("next_cursor")
        if not res.get("has_more"):
            break


def list_ingredients() -> Dict[str, str]:
    """Return mapping canonical_name -> page_id for all Ingredients in INGREDIENTS_DB_ID."""
    client = get_client()
    db = settings.INGREDIENTS_DB_ID
    if not db:
        return {}
    mapping = {}
    for page in _paginate_query(client, db):
        props = page.get("properties", {})
        # assume title property is first title
        title_key = settings.P_ING_TITLE
        title_prop = props.get(title_key) or props.get("Name")
        name = ""
        if title_prop and title_prop.get("title"):
            name = "".join([t.get("plain_text", "") for t in title_prop.get("title")])
        if name:
            mapping[name] = page.get("id")
    logger.debug("list_ingredients: found %d ingredients in DB %s", len(mapping), db)
    return mapping


def upsert_ingredient(
    name: str,
    raw: Optional[str] = None,
    quantity: Optional[float] = None,
    unit: Optional[str] = None,
    notes: Optional[str] = None,
) -> Tuple[str, bool]:
    """Create or update an ingredient page.

    The Ingredients DB is expected to expose these properties (common names):
    Name (title), Recipes (relation), Quantity (number), Unit (rich_text),
    Notes (rich_text), Raw (rich_text).

    This function will create the page if it does not exist, or update the
    existing page's properties when optional fields are provided.
    Returns (page_id, created_flag).
    """
    client = get_client()
    db = settings.INGREDIENTS_DB_ID
    if not db:
        raise RuntimeError("INGREDIENTS_DB_ID not configured")

    # Fetch DB schema to determine which properties exist
    try:
        db_meta = client.databases.retrieve(database_id=db)
        db_props = db_meta.get("properties", {}) or {}
    except Exception:
        db_props = {}

    logger.debug("upsert_ingredient: ingredient DB properties: %s", list(db_props.keys()))

    title_key = settings.P_ING_TITLE
    # naive search by filter using title property key (Title property)
    filter_key = title_key if title_key in db_props else "Name"
    resp = client.databases.query(
        database_id=db, filter={"property": filter_key, "title": {"equals": name}}
    )
    if resp.get("results"):
        # existing page: update any provided optional fields
        page_id = resp["results"][0]["id"]
        update_props: dict = {}
        # Quantity (number)
        qty_key = settings.P_ING_QTY
        if quantity is not None and qty_key in db_props and db_props[qty_key].get("type") == "number":
            update_props[qty_key] = {"number": quantity}
        # Unit
        unit_key = settings.P_ING_UNIT
        if unit and unit_key in db_props and db_props[unit_key].get("type") in ("rich_text", "title"):
            if db_props[unit_key].get("type") == "title":
                update_props[unit_key] = {"title": [{"text": {"content": unit}}]}
            else:
                update_props[unit_key] = {"rich_text": [{"text": {"content": unit}}]}
        # Notes
        notes_key = settings.P_ING_NOTES
        if notes and notes_key in db_props and db_props[notes_key].get("type") in ("rich_text", "title"):
            if db_props[notes_key].get("type") == "title":
                update_props[notes_key] = {"title": [{"text": {"content": notes}}]}
            else:
                update_props[notes_key] = {"rich_text": [{"text": {"content": notes}}]}
        # Raw
        raw_key = settings.P_ING_RAW
        if raw and raw_key in db_props and db_props[raw_key].get("type") in ("rich_text", "title"):
            if db_props[raw_key].get("type") == "title":
                update_props[raw_key] = {"title": [{"text": {"content": raw}}]}
            else:
                update_props[raw_key] = {"rich_text": [{"text": {"content": raw}}]}

        if update_props:
            try:
                client.pages.update(page_id=page_id, properties=update_props)
                logger.info("upsert_ingredient: updated page %s for %s", page_id, name)
            except Exception:
                # best-effort: ignore update failures
                logger.exception("upsert_ingredient: failed to update page %s", page_id)
        else:
            logger.debug("upsert_ingredient: no updates required for existing %s", page_id)
        return page_id, False

    # Prepare properties for creation, include optional fields only if DB has them
    props = {filter_key: {"title": [{"text": {"content": name}}]}}
    # Quantity (number)
    qty_key = settings.P_ING_QTY
    if quantity is not None and qty_key in db_props and db_props[qty_key].get("type") == "number":
        props[qty_key] = {"number": quantity}
    # Unit
    unit_key = settings.P_ING_UNIT
    if unit and unit_key in db_props and db_props[unit_key].get("type") in ("rich_text", "title"):
        if db_props[unit_key].get("type") == "title":
            props[unit_key] = {"title": [{"text": {"content": unit}}]}
        else:
            props[unit_key] = {"rich_text": [{"text": {"content": unit}}]}
    # Notes
    notes_key = settings.P_ING_NOTES
    if notes and notes_key in db_props and db_props[notes_key].get("type") in ("rich_text", "title"):
        if db_props[notes_key].get("type") == "title":
            props[notes_key] = {"title": [{"text": {"content": notes}}]}
        else:
            props[notes_key] = {"rich_text": [{"text": {"content": notes}}]}
    # Raw
    raw_key = settings.P_ING_RAW
    if raw and raw_key in db_props and db_props[raw_key].get("type") in ("rich_text", "title"):
        if db_props[raw_key].get("type") == "title":
            props[raw_key] = {"title": [{"text": {"content": raw}}]}
        else:
            props[raw_key] = {"rich_text": [{"text": {"content": raw}}]}

    page = client.pages.create(parent={"database_id": db}, properties=props)
    logger.info("upsert_ingredient: created page %s for %s", page.get("id"), name)
    return page.get("id"), True


def upsert_recipe(recipe) -> Tuple[str, bool]:
    """Create or update a recipe page using the RecipePayload object.

    Maps these payload fields into the Recipes DB when available:
    - Name (title)
    - Source (url)
    - Servings (number)
    - Prep Time / Cook Time (number)
    - Steps (rich_text) — joined into a single text block
    """
    client = get_client()
    db = settings.RECIPES_DB_ID
    if not db:
        raise RuntimeError("RECIPES_DB_ID not configured")

    # Fetch database schema once to know available properties
    try:
        db_meta = client.databases.retrieve(database_id=db)
        db_props = db_meta.get("properties", {}) or {}
    except Exception:
        db_props = {}

    logger.debug("upsert_recipe: recipes DB properties: %s", list(db_props.keys()))

    title_key = settings.P_RECIPE_TITLE
    title = getattr(recipe, "title", None) or ""

    # Build filter: match existing by title
    filter_clauses = [{"property": title_key, "title": {"equals": title}}]
    # if Source property exists and recipe has source_url, include it in filter
    source_key = settings.P_RECIPE_SOURCE_URL
    if getattr(recipe, "source_url", None) and source_key in db_props and db_props[source_key].get("type") == "url":
        filter_clauses.append({"property": source_key, "url": {"equals": getattr(recipe, "source_url")}})

    resp = client.databases.query(database_id=db, filter={"and": filter_clauses})
    if resp.get("results"):
        page_id = resp["results"][0]["id"]
        logger.debug("upsert_recipe: found existing recipe %s -> %s", title, page_id)
        # Optionally update numeric fields if present
        update_props: dict = {}
        servings_key = "Servings"
        if getattr(recipe, "servings", None) is not None and servings_key in db_props and db_props[servings_key].get("type") == "number":
            update_props[servings_key] = {"number": getattr(recipe, "servings")}
        prep_key = "Prep Time"
        if getattr(recipe, "time", None) and getattr(recipe.time, "prep_min", None) is not None and prep_key in db_props and db_props[prep_key].get("type") == "number":
            update_props[prep_key] = {"number": getattr(recipe.time, "prep_min")}
        cook_key = "Cook Time"
        if getattr(recipe, "time", None) and getattr(recipe.time, "cook_min", None) is not None and cook_key in db_props and db_props[cook_key].get("type") == "number":
            update_props[cook_key] = {"number": getattr(recipe.time, "cook_min")}
        steps_key = "Steps"
        if getattr(recipe, "steps", None) and steps_key in db_props and db_props[steps_key].get("type") == "rich_text":
            steps_text = "\n".join(getattr(recipe, "steps", []))
            update_props[steps_key] = {"rich_text": [{"text": {"content": steps_text}}]}

        if update_props:
            try:
                client.pages.update(page_id=page_id, properties=update_props)
                logger.info("upsert_recipe: updated recipe page %s", page_id)
            except Exception:
                logger.exception("upsert_recipe: failed to update recipe %s", page_id)

        return page_id, False

    # Create new page
    props = {title_key: {"title": [{"text": {"content": title}}]}}
    # Source
    if getattr(recipe, "source_url", None) and "Source" in db_props and db_props["Source"].get("type") == "url":
        props["Source"] = {"url": getattr(recipe, "source_url")}
    # Servings
    if getattr(recipe, "servings", None) is not None and "Servings" in db_props and db_props["Servings"].get("type") == "number":
        props["Servings"] = {"number": getattr(recipe, "servings")}
    # Prep/Cook times
    if getattr(recipe, "time", None):
        if getattr(recipe.time, "prep_min", None) is not None and "Prep Time" in db_props and db_props["Prep Time"].get("type") == "number":
            props["Prep Time"] = {"number": getattr(recipe.time, "prep_min")}
        if getattr(recipe.time, "cook_min", None) is not None and "Cook Time" in db_props and db_props["Cook Time"].get("type") == "number":
            props["Cook Time"] = {"number": getattr(recipe.time, "cook_min")}
    # Steps
    if getattr(recipe, "steps", None) and "Steps" in db_props and db_props["Steps"].get("type") == "rich_text":
        props["Steps"] = {"rich_text": [{"text": {"content": "\n".join(getattr(recipe, "steps", []))}}]}

    page = client.pages.create(parent={"database_id": db}, properties=props)
    logger.info("upsert_recipe: created recipe page %s for %s", page.get("id"), title)
    return page.get("id"), True


def upsert_recipe_ingredient(
    recipe_page_id: str, ingredient_page_id: str, qty_per_serving: Optional[float]
) -> str:
    """Create a junction row in RECIPE_ING_DB_ID linking recipe and ingredient."""
    client = get_client()
    db = settings.RECIPE_ING_DB_ID
    if not db:
        raise RuntimeError("RECIPE_ING_DB_ID not configured")
    # Fetch DB schema so we can adapt to custom property names
    try:
        db_meta = client.databases.retrieve(database_id=db)
        db_props = db_meta.get("properties", {}) or {}
    except Exception:
        db_props = {}

    logger.debug("upsert_recipe_ingredient: junction DB properties: %s", list(db_props.keys()))

    # Find relation properties in the junction DB
    relation_keys = [k for k, v in db_props.items() if v.get("type") == "relation"]

    # Prefer explicit property names discovered in the workspace dump
    recipe_key = "Recipes" if "Recipes" in db_props else (relation_keys[0] if relation_keys else None)
    ingredient_key = "Ingredients" if "Ingredients" in db_props else (
        relation_keys[1] if len(relation_keys) > 1 else (relation_keys[0] if relation_keys else None)
    )

    if not recipe_key or not ingredient_key:
        available = ", ".join(sorted(db_props.keys())) or "<none>"
        logger.error("Junction DB missing relation properties. Available properties: %s", available)
        raise RuntimeError(
            f"Junction DB missing relation properties. Expected 'Recipes' and 'Ingredients' or at least two relation properties. Available properties: {available}"
        )

    props = {
        recipe_key: {"relation": [{"id": recipe_page_id}]},
        ingredient_key: {"relation": [{"id": ingredient_page_id}]},
    }

    # Qty on junction appears to be named by settings.P_RECIPING_QTY_PER_SERVING in the DB
    qty_key = settings.P_RECIPING_QTY_PER_SERVING
    if qty_per_serving is not None and qty_key in db_props and db_props[qty_key].get("type") == "number":
        logger.debug("upsert_recipe_ingredient: setting qty %s on key %s", qty_per_serving, qty_key)
        props[qty_key] = {"number": qty_per_serving}

    # Unit and Note fields on the junction (optional)
    unit_key = "Unit"
    if unit_key in db_props and db_props[unit_key].get("type") in ("rich_text", "title"):
        # we don't have a unit value here by default; callers can extend if needed
        pass
    note_key = "Note"
    if note_key in db_props and db_props[note_key].get("type") in ("rich_text", "title"):
        pass

    page = client.pages.create(parent={"database_id": db}, properties=props)
    logger.info("upsert_recipe_ingredient: created junction %s", page.get("id"))
    return page.get("id")
