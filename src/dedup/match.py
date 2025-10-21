"""Matching logic for ingredients: match_or_create."""

from __future__ import annotations

from typing import Set, Tuple

from src.dedup.canonicalize import canonicalize
import logging

logger = logging.getLogger(__name__)


def match_or_create(
    name: str, existing_names: Set[str], index, threshold: float = 0.92
) -> Tuple[str, str, float]:
    """Return a tuple (status, name, score).

    status is 'existing' or 'new'. If existing, name is canonical existing name.
    index must implement nearest(query) -> (name, score).
    """
    can = canonicalize(name)
    logger.debug("match_or_create: canonicalized '%s' -> '%s'", name, can)
    if can in existing_names:
        logger.debug("match_or_create: exact match in existing_names for '%s'", can)
        return "existing", can, 1.0

    existing_name, score = index.nearest(can)
    if existing_name and score >= threshold:
        logger.debug("match_or_create: nearest match '%s' score %s >= threshold %s", existing_name, score, threshold)
        return "existing", existing_name, score

    logger.debug("match_or_create: no match, returning new '%s' score %s", can, score)
    return "new", can, score
