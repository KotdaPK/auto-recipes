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

Design notes
- The pipeline always uses page text — we never assume the site provides structured JSON-LD. This reduces false positives from inconsistent markup.
- Ingredient deduplication uses a local SentenceTransformer model. Tweak the threshold in `src/dedup/match.py`.
- Alias map in `src/dedup/canonicalize.py` handles common renames.

See the `src/` package for implementation details.
# auto-recipes