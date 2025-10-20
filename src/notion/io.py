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
        title_prop = props.get("Name") or props.get(title_key)
        name = ""
        if title_prop and title_prop.get("title"):
            name = "".join([t.get("plain_text", "") for t in title_prop.get("title")])
        if name:
            mapping[name] = page.get("id")
    return mapping


def upsert_ingredient(name: str) -> Tuple[str, bool]:
    """Upsert ingredient by name; returns (page_id, created_flag)."""
    client = get_client()
    db = settings.INGREDIENTS_DB_ID
    if not db:
        raise RuntimeError("INGREDIENTS_DB_ID not configured")
    # naive search by filter
    resp = client.databases.query(
        database_id=db, filter={"property": "Name", "title": {"equals": name}}
    )
    if resp.get("results"):
        return resp["results"][0]["id"], False
    # create
    page = client.pages.create(
        parent={"database_id": db},
        properties={"Name": {"title": [{"text": {"content": name}}]}},
    )
    return page.get("id"), True


def upsert_recipe(title: str, source_url: Optional[str] = None) -> Tuple[str, bool]:
    client = get_client()
    db = settings.RECIPES_DB_ID
    if not db:
        raise RuntimeError("RECIPES_DB_ID not configured")
    # search by title and source_url
    title_key = settings.P_RECIPE_TITLE
    filter_body = {
        "and": [{"property": title_key, "title": {"equals": title}}]
    }
    if source_url:
        filter_body["and"].append({"property": "Source", "url": {"equals": source_url}})
    resp = client.databases.query(database_id=db, filter=filter_body)
    if resp.get("results"):
        return resp["results"][0]["id"], False
    props = {settings.P_RECIPE_TITLE: {"title": [{"text": {"content": title}}]}}
    if source_url:
        props["Source"] = {"url": source_url}
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
    props = {
        "Recipe": {"relation": [{"id": recipe_page_id}]},
        "Ingredient": {"relation": [{"id": ingredient_page_id}]},
    }
    if qty_per_serving is not None:
        props[settings.P_RECIPING_QTY_PER_SERVING] = {"number": qty_per_serving}
    page = client.pages.create(parent={"database_id": db}, properties=props)
    return page.get("id")
