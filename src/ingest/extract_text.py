"""Extract main page text using trafilatura."""

from __future__ import annotations

from typing import Optional

import trafilatura


def extract_main_text(html: str, url: Optional[str] = None) -> str:
    """Return main text extracted by trafilatura or empty string."""
    text = trafilatura.extract(html, url=url)
    return text or ""
