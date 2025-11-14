"""Deprecated: Notion I/O helpers (deprecated).

The Notion integration has been removed from the main code path. These
modules remain as lightweight stubs to avoid hard import failures for
historical scripts. If you need the original functionality, restore the
files from version control or re-add the Notion integration.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def list_ingredients() -> Dict[str, str]:
    """Stub: Notion integration removed. Returns empty mapping."""
    logger.debug("list_ingredients: Notion integration removed; returning empty mapping")
    return {}


def upsert_ingredient(*_args, **_kwargs) -> Tuple[str, bool]:
    """Stub: Notion integration removed."""
    raise RuntimeError("Notion integration removed; upsert_ingredient is unavailable")


def upsert_recipe(*_args, **_kwargs) -> Tuple[str, bool]:
    raise RuntimeError("Notion integration removed; upsert_recipe is unavailable")


def upsert_recipe_ingredient(*_args, **_kwargs) -> str:
    raise RuntimeError("Notion integration removed; upsert_recipe_ingredient is unavailable")
