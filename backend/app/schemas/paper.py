"""Request/response schemas for M4 paper trading."""
from typing import Literal

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    starting_cash: float = Field(gt=0, default=100_000.0)


class OrderCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    order_type: Literal["market", "limit", "stop"] = "market"
    limit_price: float | None = Field(default=None, gt=0)
