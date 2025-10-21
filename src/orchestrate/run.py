"""Orchestrator glue: pipeline functions for ingesting URLs, reindexing, and syncing meals."""

from __future__ import annotations

import os

from rich.console import Console

from src.ingest.fetch import fetch_url
from src.ingest.extract_text import extract_main_text
from src.ingest.parse_llm_gemini import parse_recipe_text
from src.dedup.embed_index import EmbedIndex
from src.notion import mapping as notion_mapping
from src.notion import io as notion_io

console = Console()


def url_to_notion(url: str) -> None:
    console.print(f"Ingesting: {url}")
    html, final = fetch_url(url)
    text = extract_main_text(html, final)
    recipe = parse_recipe_text(text, final)

    # build index from Notion existing ingredients
    existing = notion_io.list_ingredients()
    names = list(existing.keys())
    index = EmbedIndex()
    index.build(names)

    # wrap index with expected interface
    class _Idx:
        def __init__(self, ei: EmbedIndex):
            self.ei = ei

        def nearest(self, q):
            return self.ei.nearest(q, topk=1)

        def match_or_create(self, name, existing_names, index, threshold=0.92):
            from src.dedup.match import match_or_create as mfn

            return mfn(name, existing_names, self.ei, threshold)

    wrapper = _Idx(index)

    summary = notion_mapping.map_and_upsert(recipe, wrapper)
    console.print("Done:", summary)
    console.print("Recipe parsed:", recipe.model_dump_json(indent=2))


def reindex_ingredients(path_base: str = "data/ingredients") -> None:
    console.print("Reindexing ingredients from Notion...")
    existing = notion_io.list_ingredients()
    names = list(existing.keys())
    print("Ingredient names:", names)
    print(f"Found {len(names)} ingredients to index.")
    idx = EmbedIndex()
    idx.build(names)
    os.makedirs(os.path.dirname(path_base), exist_ok=True)
    idx.save(path_base)
    console.print(f"Wrote index for {len(names)} ingredients to {path_base}.*")


def sync_meals(days_ahead: int = 10, default_duration: int = 45) -> None:
    console.print(
        f"Syncing meals for next {days_ahead} days (duration={default_duration})"
    )
    # Minimal: list meals from Notion and upsert events by reading P_MEAL_WHEN property
    # Placeholder: implement full sync when schema is known.
    console.print("Not implemented full sync in this minimal example.")
