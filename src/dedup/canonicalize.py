"""Canonicalize ingredient names and provide alias map."""

from __future__ import annotations

import re
from typing import Dict

ALIAS_MAP: Dict[str, str] = {
    "spring onions": "green onion",
    "scallions": "green onion",
    "roma tomatoes": "tomato",
    "extra virgin olive oil": "olive oil",
}

DESCRIPTORS = [
    "fresh",
    "chopped",
    "minced",
    "diced",
    "organic",
    "large",
    "small",
    "to taste",
    "finely",
    "sliced",
    "grated",
    "peeled",
    "crushed",
    "ground",
    "halved",
    "roughly",
    "thinly",
]


def canonicalize(name: str) -> str:
    """Lowercase, remove punctuation, common descriptors, apply alias map, and collapse spaces."""
    if not name:
        return ""
    s = name.lower()
    # replace hyphens with spaces
    s = s.replace("-", " ")
    # remove punctuation
    s = re.sub(r"[\.,;:()\[\]\\/\"]", " ", s)
    # remove descriptors words
    for d in DESCRIPTORS:
        s = re.sub(r"\b" + re.escape(d) + r"\b", "", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # alias map
    if s in ALIAS_MAP:
        s = ALIAS_MAP[s]
    return s
