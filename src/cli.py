"""Typer CLI for auto-recipes (ingest, reindex, sync)."""

from __future__ import annotations

import sys
import click
import typer
from rich.console import Console

from dotenv import load_dotenv
# load .env immediately so subsequent imports (which read settings at import time)
# pick up values from the .env file
load_dotenv()

# Configure top-level logging early so other modules pick it up.
import logging
from src.settings import settings

log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
handlers = [logging.StreamHandler()]
if settings.LOG_FILE:
    handlers.append(logging.FileHandler(settings.LOG_FILE))
logging.basicConfig(
    level=log_level,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    handlers=handlers,
)

# Quiet noisy third-party loggers while keeping our app logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)

from src.orchestrate import run as orchestrator
from src.settings import validate_required

app = typer.Typer()
console = Console()


@app.command()
def ingest(url: str):
    """Ingest a single URL and persist parsed artifacts locally."""
    try:
        orchestrator.url_to_recipe(url)
        console.print("Ingest completed.")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("reindex-ingredients")
def reindex_ingredients():
    try:
        orchestrator.reindex_ingredients()
        console.print("Reindex completed.")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("sync-meals")
def sync_meals(days: int = 10, duration: int = 45):
    try:
        orchestrator.sync_meals(days, duration)
        console.print("Sync completed.")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    # validate required secrets (dotenv already loaded at module import)
    validate_required()
    app()