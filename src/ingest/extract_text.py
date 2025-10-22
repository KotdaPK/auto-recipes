"""Extract main page text using trafilatura."""

from __future__ import annotations

from typing import Optional
import logging

import trafilatura


logger = logging.getLogger(__name__)


def extract_main_text(html: str, url: Optional[str] = None) -> str:
    """Return main text extracted by trafilatura or empty string."""
    # text = trafilatura.extract(html, url=url)
    # with open("text.txt", "w", encoding="utf-8") as file:
    #     file.write(text or "")
    with open("text.txt", "r", encoding="utf-8") as file:
        text = file.read()
    logger.debug("Extracted text length: %d", len(text or ""))
    return text or ""
