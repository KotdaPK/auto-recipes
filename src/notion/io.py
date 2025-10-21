"""Notion I/O helpers: list ingredients, upsert ingredient/recipe/junction rows."""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

from notion_client import Client

from src.settings import settings
import os

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
        title_key = settings.P_RECIPE_TITLE
        title_prop = props.get(title_key) or props.get("Name")
        name = ""
        if title_prop and title_prop.get("title"):
            name = "".join([t.get("plain_text", "") for t in title_prop.get("title")])
        if name:
            mapping[name] = page.get("id")
    return mapping


def upsert_ingredient(name: str, unit: Optional[str] = None, notes: Optional[str] = None) -> Tuple[str, bool]:
    """Upsert ingredient by name; returns (page_id, created_flag).

    If the Ingredients DB contains properties for unit/notes (names configured
    via `settings.P_ING_UNIT` and `settings.P_ING_NOTES`), set them when
    creating the page.
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

    title_key = settings.P_RECIPE_TITLE
    # naive search by filter using title property key
    filter_key = title_key if title_key in db_props else "Name"
    resp = client.databases.query(
        database_id=db, filter={"property": filter_key, "title": {"equals": name}}
    )
    if resp.get("results"):
        return resp["results"][0]["id"], False

    # Prepare properties for creation, include optional unit/notes only if DB has them
    props = {filter_key: {"title": [{"text": {"content": name}}]}}
    # Unit
    unit_key = settings.P_ING_UNIT
    if unit and unit_key in db_props and db_props[unit_key].get("type") == "rich_text":
        props[unit_key] = {"rich_text": [{"text": {"content": unit}}]}
    # Notes
    notes_key = settings.P_ING_NOTES
    if notes and notes_key in db_props and db_props[notes_key].get("type") in ("rich_text", "title"):
        # Use rich_text for notes; fallback to title if configured that way
        if db_props[notes_key].get("type") == "title":
            props[notes_key] = {"title": [{"text": {"content": notes}}]}
        else:
            props[notes_key] = {"rich_text": [{"text": {"content": notes}}]}

    page = client.pages.create(parent={"database_id": db}, properties=props)
    return page.get("id"), True


def upsert_recipe(title: str, source_url: Optional[str] = None) -> Tuple[str, bool]:
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

    # Determine property keys
    title_key = settings.P_RECIPE_TITLE
    source_key = settings.P_RECIPE_SOURCE_URL
    has_source = source_key in db_props and db_props[source_key].get("type") == "url"

    # Build filter: always include title match; include source URL only if property exists
    filter_clauses = [{"property": title_key, "title": {"equals": title}}]
    if source_url and has_source:
        filter_clauses.append({"property": source_key, "url": {"equals": source_url}})
    resp = client.databases.query(database_id=db, filter={"and": filter_clauses})
    if resp.get("results"):
        return resp["results"][0]["id"], False

    # Prepare properties for creation
    props = {title_key: {"title": [{"text": {"content": title}}]}}
    if source_url and has_source:
        props[source_key] = {"url": source_url}
    page = client.pages.create(parent={"database_id": db}, properties=props)
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

    # Find relation properties in the junction DB
    relation_keys = [k for k, v in db_props.items() if v.get("type") == "relation"]

    # Prefer explicit property names if they exist, otherwise pick relation props
    recipe_key = "Recipe" if "Recipe" in db_props else (relation_keys[0] if relation_keys else None)
    ingredient_key = (
        "Ingredient"
        if "Ingredient" in db_props
        else (relation_keys[1] if len(relation_keys) > 1 else (relation_keys[0] if relation_keys else None))
    )

    if not recipe_key or not ingredient_key:
        available = ", ".join(sorted(db_props.keys())) or "<none>"
        raise RuntimeError(
            f"Junction DB missing relation properties. Expected 'Recipe' and 'Ingredient' or at least two relation properties. Available properties: {available}"
        )

    props = {
        recipe_key: {"relation": [{"id": recipe_page_id}]},
        ingredient_key: {"relation": [{"id": ingredient_page_id}]},
    }

    # Only set the qty property if it exists and is a number
    qty_key = settings.P_RECIPING_QTY_PER_SERVING
    if qty_per_serving is not None and qty_key in db_props and db_props[qty_key].get("type") == "number":
        props[qty_key] = {"number": qty_per_serving}

    page = client.pages.create(parent={"database_id": db}, properties=props)
    return page.get("id")
