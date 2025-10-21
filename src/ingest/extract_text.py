"""Extract main page text using trafilatura."""

from __future__ import annotations

from typing import Optional
import logging

import trafilatura


logger = logging.getLogger(__name__)


def extract_main_text(html: str, url: Optional[str] = None) -> str:
    """Return main text extracted by trafilatura or empty string."""
    text = trafilatura.extract(html, url=url)
    logger.debug("Extracted text length: %d", len(text or ""))
    return text or ""
