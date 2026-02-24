from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ItemSummary(BaseModel):
    id: int
    product_name: str
    store: str
    current_price: float
    previous_price: float | None
    price_change: float
    percent_change: float | None
    direction: Literal["up", "down", "same", "new"]
    last_updated: datetime


class PricePoint(BaseModel):
    price: float
    scraped_at: datetime


class ItemHistoryResponse(BaseModel):
    id: int
    product_name: str
    store: str
    history: list[PricePoint]
