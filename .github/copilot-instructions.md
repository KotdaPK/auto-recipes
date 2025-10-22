This repository (auto-recipes / meal-text-to-notion) ingests recipe web pages, uses a LLM to parse free text into a strict Pydantic recipe schema, deduplicates ingredients with local embeddings, and upserts results into Notion (and optionally Google Calendar).

Be concise and code-focused. When you make edits, prefer small, well-tested changes and mention affected files.

Essential overview
- Entry point: `src/cli.py` (Typer CLI). Common commands: `ingest <url>`, `reindex-ingredients`, `sync-meals`.
- Orchestration: `src/orchestrate/run.py` — builds pipeline: fetch -> extract text -> LLM parse -> embed-index dedupe -> Notion upsert.
- LLM parsing: `src/ingest/parse_llm_gemini.py` — uses `google.generativeai` (Gemini). Schema for structured LLM output is loaded from `src/schemas/recipe_response_schema.json` and validated into `src/models/recipe_schema.py`.
- Notion integration: `src/notion/io.py` and `src/notion/mapping.py` — use `notion-client`. `NOTION_TOKEN` and DB IDs are in environment (see `src/settings.py`).
- Ingredient dedup: `src/dedup/embed_index.py`, `src/dedup/match.py`, `src/dedup/canonicalize.py` — canonicalization + SentenceTransformers embeddings.

Environment & common developer workflows
- Python 3.11+; create a venv and install deps from `requirements.txt`.
- Copy `.env.example` -> `.env` and set `NOTION_TOKEN`, `GEMINI_API_KEY`, and relevant DB IDs before running CLI commands. The CLI calls `dotenv.load_dotenv()` at import time so `.env` must exist before running `python -m src.cli`.
- Quick commands used by humans (examples that agents can suggest/run):
  - Reindex ingredients (build local embeddings): `python -m src.cli reindex-ingredients`
  - Ingest a single page into Notion: `python -m src.cli ingest https://example.com/recipe`
  - Sync meals (partial/placeholder): `python -m src.cli sync-meals --days 10 --duration 45`

Project-specific conventions and gotchas
- Settings are read at import time from environment via `src/settings.py`. `src/cli.py` deliberately calls `load_dotenv()` early so the rest of the code sees `.env` values. When adding scripts or tests that import settings, ensure `.env` is loaded or set env vars in the test harness.
- The LLM integration is lazy-imported inside `src/ingest/parse_llm_gemini.py` to allow tests to run without the `google.generativeai` package present. Mirror that pattern when adding optional heavy deps.
- Notion DB properties are treated as configurable: the code inspects the DB schema at runtime and adapts. When adding new Notion fields, prefer detecting availability (as the code does) instead of hardcoding property names.
- Ingredient canonicalization: `src/dedup/canonicalize.py` is the single source of truth for normalized names. Use it before matching or building embeddings.
- Embedding storage: `src/orchestrate/run.py` writes indices under `data/ingredients*` by default. Tests and CLI use these files — updating the index format requires updating `EmbedIndex.save/load` in `src/dedup/embed_index.py`.

Integration points & external deps to be careful with
- Gemini / Google Generative AI (api key in `GEMINI_API_KEY`) — responses are expected to be JSON matching `src/schemas/recipe_response_schema.json`. Code retries once on validation failures.
- Notion API (token in `NOTION_TOKEN`) — `src/notion/io.py` reads DB schema and performs queries and page creation/updates. Prefer defensive coding: operations may raise network/permission errors and are often best-effort (some exceptions are logged and swallowed).
- Optional Google Calendar sync requires OAuth credentials.json at project root and relies on `google-api-python-client` in `requirements.txt`.

Files to reference when making changes
- `src/cli.py` — CLI surface and how `.env` is loaded
- `src/settings.py` — environment names and defaults
- `src/orchestrate/run.py` — pipeline flow and where to hook changes
- `src/ingest/parse_llm_gemini.py` — LLM prompt and parsing pattern
- `src/notion/io.py` — Notion schema adaptation, upsert patterns
- `src/dedup/*` — canonicalization, matching, and embedding index usage

Testing and quick validation
- Unit tests live in `tests/` and use pytest. The LLM and Notion integrations are not unit-tested live; prefer to mock external clients in tests.
- To run tests: `pytest -q` (consider setting env vars or mocking). Keep tests small and fast; the project uses `ruff`/`black` config in `pyproject.toml`.

When editing code, prefer small, explicit changes and include a short rationale in the PR/commit. If you touch Notion or LLM code, include notes about required env vars and any offline-mode behavior (e.g., lazy imports or mockable hooks).

If anything here is unclear or you want more detail on a specific area (index format, LLM schema, Notion property mapping), tell me which file or flow to expand and I'll update this guidance.
