meal-text-to-notion
====================

Converts recipe web pages into structured recipes, deduplicates ingredients locally with embeddings, upserts to Notion, and optionally syncs Meals to Google Calendar.

Key ideas
- Always extract and parse the page text (no JSON-LD assumptions). Use a LLM (Gemini) to parse free text into a strict Pydantic schema.
- Deduplicate ingredient names locally using SentenceTransformers embeddings and a small nearest-neighbour matcher.
- Upsert Recipes, Ingredients and junction rows into Notion, and create idempotent Google Calendar events for Meals.

Quickstart
1. Create a virtualenv with Python 3.11+ and install dependencies:

```
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in keys and Notion DB IDs.

3. If using Google Calendar, place `credentials.json` (OAuth client secrets) in the project root.

4. Reindex ingredients from Notion:

```
python -m src.cli reindex-ingredients
```

5. Ingest a recipe URL:

```
python -m src.cli ingest url https://example.com/recipe
```

## Features

- Extracts and parses recipe page text (no reliance on JSON-LD) and uses a LLM (Gemini) to convert free text into a strict Pydantic recipe schema.
- End-to-end ingestion pipeline (fetch -> extract text -> LLM parse -> dedupe -> Notion upsert) orchestrated from `src/orchestrate/run.py`.
- Ingredient deduplication using local SentenceTransformers embeddings, a small nearest-neighbour matcher, and a tunable threshold (`src/dedup/match.py`).
- Canonicalization and alias mapping for ingredient names (`src/dedup/canonicalize.py`).
- Local embedding index management (save/load) via `src/dedup/embed_index.py`; indices and vectors stored under `data/` (e.g. `data/ingredients.names.json`, `data/ingredients.vecs.npy`).
- Idempotent upsert of Recipes, Ingredients, and junction rows into Notion with runtime DB schema adaptation (`src/notion/io.py`, `src/notion/mapping.py`).
- Optional Google Calendar sync for Meals (idempotent event creation). OAuth `credentials.json` support and code in `src/calendar/`.
- CLI (Typer) entrypoint at `src/cli.py` with common commands: `ingest <url>`, `reindex-ingredients`, and `sync-meals`.
- LLM parsing code (`src/ingest/parse_llm_gemini.py`) validates against `src/schemas/recipe_response_schema.json` and converts into `src/models/recipe_schema.py` (Pydantic) with retry-on-validation failure.
- Lazy imports for heavyweight external clients (Gemini / Notion) so tests can run without those packages installed.
- Tests with pytest in `tests/` (unit tests for canonicalization and matching included). Mock external services where appropriate.
- Environment-driven settings loaded from `src/settings.py`; `.env` recommended (copy from `.env.example`). The CLI loads `.env` early to ensure settings available at import time.
- Configurable behavior and defensive Notion integration: the code inspects Notion DB properties at runtime and adapts to available fields.
- Small, local-first design: deduplication and matching are performed locally (no external index), with the ability to reindex from Notion using `python -m src.cli reindex-ingredients`.


Design notes
- The pipeline always uses page text — we never assume the site provides structured JSON-LD. This reduces false positives from inconsistent markup.
- Ingredient deduplication uses a local SentenceTransformer model. Tweak the threshold in `src/dedup/match.py`.
- Alias map in `src/dedup/canonicalize.py` handles common renames.

See the `src/` package for implementation details.
# auto-recipes