"""Orchestrator glue: pipeline functions for ingesting URLs, reindexing, and syncing meals."""

from __future__ import annotations

import os
import json
import logging
import re
from rich.console import Console
logger = logging.getLogger(__name__)

from src.ingest.fetch import fetch_url
from src.ingest.extract_text import extract_main_text
from src.ingest.parse_llm_gemini import parse_recipe_text
from src.dedup.embed_index import EmbedIndex
from src.notion import mapping as notion_mapping
from src.notion import io as notion_io

console = Console()


def url_to_notion(url: str) -> None:
    logger.info("Ingesting: %s", url)
    console.print(f"Ingesting: {url}")
    html, final = fetch_url(url)
    text = extract_main_text(html, final)
    recipe = parse_recipe_text(text, final)

    # Try to extract schema.org Recipe JSON-LD from the page and use it to
    # populate/override simple metadata (servings, prep/cook/total minutes).
    def _find_jsonld_recipe(html_text: str) -> dict | None:
        # find all <script type="application/ld+json"> blocks
        scripts = re.findall(r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html_text, flags=re.I | re.S)
        for s in scripts:
            s = s.strip()
            if not s:
                continue
            try:
                data = json.loads(s)
            except Exception:
                # Try to be forgiving: strip surrounding HTML comments
                try:
                    cleaned = re.sub(r"^<!--|-->$", "", s).strip()
                    data = json.loads(cleaned)
                except Exception:
                    continue

            # data can be an array or an object; normalize
            candidates = data if isinstance(data, list) else [data]
            for cand in candidates:
                # Some pages nest objects under "@graph"
                if isinstance(cand, dict) and cand.get("@graph"):
                    graph = cand.get("@graph")
                    if isinstance(graph, list):
                        for g in graph:
                            if isinstance(g, dict) and (g.get("@type") == "Recipe" or "recipeYield" in g):
                                return g
                if isinstance(cand, dict) and (cand.get("@type") == "Recipe" or "recipeYield" in cand or cand.get("@type") == ["Recipe"]):
                    return cand
        return None

    def _parse_iso_duration_to_minutes(d: str) -> float | None:
        if not d:
            return None
        d = d.strip()
        # ISO 8601 pattern e.g. PT10M, PT1H30M
        m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", d)
        if m:
            hours = int(m.group(1) or 0)
            mins = int(m.group(2) or 0)
            secs = int(m.group(3) or 0)
            total = hours * 60 + mins + (secs / 60)
            return float(total)
        # human readable like "10 minutes" or "20 mins"
        m2 = re.search(r"(\d+)\s*(?:hours|hour|hrs|hr)", d, flags=re.I)
        if m2:
            return float(int(m2.group(1)) * 60)
        m3 = re.search(r"(\d+)\s*(?:minutes|minute|mins|min)", d, flags=re.I)
        if m3:
            return float(int(m3.group(1)))
        # fallback: extract first number
        m4 = re.search(r"(\d+)", d)
        if m4:
            return float(int(m4.group(1)))
        return None

    def _parse_recipe_card(card: dict) -> dict:
        out = {}
        # recipeYield can be string or numeric
        ry = card.get("recipeYield") or card.get("yield") or card.get("recipeYield")
        if ry is not None:
            if isinstance(ry, (list, tuple)):
                ry_val = ry[0]
            else:
                ry_val = ry
            # try to extract numeric servings
            if isinstance(ry_val, (int, float)):
                out["servings"] = float(ry_val)
            else:
                m = re.search(r"(\d+)", str(ry_val))
                if m:
                    out["servings"] = float(int(m.group(1)))
                else:
                    out["yield_text"] = str(ry_val)

        # times: prepTime, cookTime, totalTime
        for key, target in [("prepTime", "prep_min"), ("cookTime", "cook_min"), ("totalTime", "total_min")]:
            v = card.get(key)
            mins = None
            if v is not None:
                mins = _parse_iso_duration_to_minutes(str(v))
            if mins is not None:
                out[target] = mins
        return out

    card = _find_jsonld_recipe(html)
    if card:
        parsed_card = _parse_recipe_card(card)
        # Apply parsed card values to recipe model, prefer card values (override LLM)
        changed = []
        if parsed_card.get("servings") is not None:
            old = getattr(recipe, "servings", None)
            recipe.servings = parsed_card["servings"]
            changed.append(("servings", old, recipe.servings))
        if parsed_card.get("yield_text") is not None and not getattr(recipe, "yield_text", None):
            recipe.yield_text = parsed_card["yield_text"]
            changed.append(("yield_text", None, recipe.yield_text))
        if parsed_card.get("prep_min") is not None:
            old = getattr(recipe.time, "prep_min", None)
            recipe.time.prep_min = parsed_card["prep_min"]
            changed.append(("prep_min", old, recipe.time.prep_min))
        if parsed_card.get("cook_min") is not None:
            old = getattr(recipe.time, "cook_min", None)
            recipe.time.cook_min = parsed_card["cook_min"]
            changed.append(("cook_min", old, recipe.time.cook_min))
        if parsed_card.get("total_min") is not None:
            old = getattr(recipe.time, "total_min", None)
            recipe.time.total_min = parsed_card["total_min"]
            changed.append(("total_min", old, recipe.time.total_min))
        if changed:
            logger.info("Applied JSON-LD recipe card values: %s", changed)

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
    logger.info("Ingest summary: %s", json.dumps(summary, indent=2))
    logger.info("Recipe parsed: %s", recipe.model_dump_json(indent=2))

    # Persist ingest artifacts for auditing / debugging: recipe payload and summary
    try:
        os.makedirs("data/ingests", exist_ok=True)
        ts = re.sub(r"[^0-9A-Za-z_-]", "", __import__("datetime").datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))
        title = getattr(recipe, "title", "recipe") or "recipe"
        safe_title = re.sub(r"[^0-9A-Za-z_-]", "_", title)[:80]
        base = f"data/ingests/{ts}_{safe_title}"
        recipe_path = base + "_recipe.json"
        summary_path = base + "_summary.json"
        with open(recipe_path, "w", encoding="utf-8") as f:
            f.write(recipe.model_dump_json(indent=2))
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info("Wrote ingest recipe payload -> %s", recipe_path)
        logger.info("Wrote ingest summary -> %s", summary_path)
    except Exception:
        logger.exception("Failed to write ingest artifacts")


def reindex_ingredients(path_base: str = "data/ingredients") -> None:
    logger.info("Reindexing ingredients from Notion...")
    existing = notion_io.list_ingredients()
    names = list(existing.keys())
    idx = EmbedIndex()
    idx.build(names)
    os.makedirs(os.path.dirname(path_base), exist_ok=True)
    idx.save(path_base)
    logger.info("Wrote index for %d ingredients to %s.*", len(names), path_base)


def sync_meals(days_ahead: int = 10, default_duration: int = 45) -> None:
    console.print(
        f"Syncing meals for next {days_ahead} days (duration={default_duration})"
    )
    # Minimal: list meals from Notion and upsert events by reading P_MEAL_WHEN property
    # Placeholder: implement full sync when schema is known.
    console.print("Not implemented full sync in this minimal example.")
