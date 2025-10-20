"""Typer CLI for meal-text-to-notion."""

from __future__ import annotations

import sys
import click
import typer
from rich.console import Console

from dotenv import load_dotenv
# load .env immediately so subsequent imports (which read settings at import time)
# pick up values from the .env file
load_dotenv()

from src.orchestrate import run as orchestrator
from src.settings import validate_required

app = typer.Typer()
console = Console()


@app.command()
def ingest(url: str):
    """Ingest a single URL into Notion."""
    try:
        orchestrator.url_to_notion(url)
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