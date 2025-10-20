"""HTTP fetcher for recipe pages."""

from __future__ import annotations

import requests
from typing import Tuple


def fetch_url(url: str, timeout: int = 20) -> Tuple[str, str]:
    """GET the url with UA header and a timeout. Returns (html, final_url).

    Raises requests.HTTPError on non-200.
    """
    headers = {"User-Agent": "meal-text-to-notion/1.0 (+https://example.com)"}
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.text, resp.url
