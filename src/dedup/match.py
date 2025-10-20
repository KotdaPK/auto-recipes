"""Matching logic for ingredients: match_or_create."""

from __future__ import annotations

from typing import Set, Tuple

from src.dedup.canonicalize import canonicalize


def match_or_create(
    name: str, existing_names: Set[str], index, threshold: float = 0.92
) -> Tuple[str, str, float]:
    """Return a tuple (status, name, score).

    status is 'existing' or 'new'. If existing, name is canonical existing name.
    index must implement nearest(query) -> (name, score).
    """
    can = canonicalize(name)
    if can in existing_names:
        return "existing", can, 1.0

    existing_name, score = index.nearest(can)
    if existing_name and score >= threshold:
        return "existing", existing_name, score

    return "new", can, score
