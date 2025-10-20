from pydantic import BaseModel, Field
from typing import List, Optional


class TimeBlock(BaseModel):
    prep_min: Optional[float] = None
    cook_min: Optional[float] = None
    total_min: Optional[float] = None


class IngredientItem(BaseModel):
    raw: Optional[str] = None
    name: str
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = ""
    notes: Optional[str] = ""


class RecipePayload(BaseModel):
    title: str
    source_url: Optional[str] = None
    yield_text: Optional[str] = None
    servings: Optional[float] = None
    time: TimeBlock = Field(default_factory=TimeBlock)
    ingredients: List[IngredientItem]
    steps: List[str]
