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


def extract_description_and_name(raw: str) -> tuple[str, str]:
    """Return a tuple (description, canonical_name).

    Description is the part of the raw string with descriptors (e.g. 'finely grated').
    canonical_name is the normalized ingredient name (e.g. 'parmesan cheese').
    """
    if not raw:
        return "", ""
    s = raw.strip()
    # lower for matching descriptors
    low = s.lower()
    desc_parts: list[str] = []

    # Find and extract descriptor words (simple approach: look for descriptors as whole words)
    for d in DESCRIPTORS:
        pattern = r"\b" + re.escape(d) + r"\b"
        if re.search(pattern, low):
            desc_parts.append(d)

    # Build description string preserving original casing where possible by matching fragments
    description = " ".join(desc_parts)

    # For name, remove descriptors from the original and canonicalize
    name_no_desc = low
    for d in DESCRIPTORS:
        name_no_desc = re.sub(r"\b" + re.escape(d) + r"\b", "", name_no_desc)
    # remove punctuation and collapse
    name_no_desc = re.sub(r"[\.,;:()\[\]\\/\"]", " ", name_no_desc)
    name_no_desc = re.sub(r"\s+", " ", name_no_desc).strip()

    # apply alias map and return
    if name_no_desc in ALIAS_MAP:
        name_no_desc = ALIAS_MAP[name_no_desc]

    return description.strip(), name_no_desc
