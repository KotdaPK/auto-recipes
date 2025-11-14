"""Deprecated Notion mapping helpers.

This module used to map recipe payloads to Notion DB properties at runtime.
Notion integration has been removed. These stubs exist to avoid breaking
imports from legacy scripts. If you require the original behavior, restore
from the repository history.
"""

def map_and_upsert(*_args, **_kwargs):
    raise RuntimeError("Notion mapping is deprecated; Notion integration removed")
