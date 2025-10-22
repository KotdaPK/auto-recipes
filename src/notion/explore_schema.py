"""Explore Notion DB schemas and dump properties for local inspection.

Usage: run with the project's venv so .env is loaded (NOTION_TOKEN must be set).
"""
from __future__ import annotations

import json
import os
import logging

from src.settings import settings
from notion_client import Client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)



def get_client():
    if not NOTION_TOKEN:
        raise RuntimeError("NOTION_TOKEN not configured in environment")
    print("Using NOTION_TOKEN:", NOTION_TOKEN[:4] + "..." + NOTION_TOKEN[-4:])
    return Client(auth=NOTION_TOKEN)


def dump_db_props(client: Client, db_id: str) -> dict:
    meta = client.databases.retrieve(database_id=db_id)
    props = meta.get("properties", {})
    # simplify to property_name -> type
    simple = {k: v.get("type") for k, v in props.items()}
    return {"id": db_id, "properties": simple}


def main():
    client = get_client()
    out = {}
    dbs = {
        "recipes": RECIPES_DB_ID,
        "ingredients": INGREDIENTS_DB_ID,
        "recipe_ingredients": RECIPE_ING_DB_ID,
    }
    for name, db_id in dbs.items():
        if not db_id:
            logger.warning("No DB id configured for %s", name)
            out[name] = {"error": "missing id"}
            continue
        try:
            out[name] = dump_db_props(client, db_id)
        except Exception as e:
            logger.exception("Failed to read db %s (%s): %s", name, db_id, e)
            out[name] = {"error": str(e)}

    os.makedirs("data", exist_ok=True)
    with open("data/notion_db_properties.json", "w", encoding="utf8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print("Wrote data/notion_db_properties.json")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
