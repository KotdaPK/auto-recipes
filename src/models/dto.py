from __future__ import annotations

from typing import Optional


class IngredientDTO:
    def __init__(self, name: str, page_id: Optional[str] = None):
        self.name = name
        self.page_id = page_id


class RecipeDTO:
    def __init__(
        self,
        title: str,
        page_id: Optional[str] = None,
        source_url: Optional[str] = None,
    ):
        self.title = title
        self.page_id = page_id
        self.source_url = source_url
