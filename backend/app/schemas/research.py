"""Structured-output contract the LLM's research-note response must satisfy."""
from pydantic import BaseModel, Field, field_validator


class ResearchNoteSchema(BaseModel):
    thesis: str = Field(min_length=10)
    catalysts: list[str] = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    fair_value_low: float
    fair_value_high: float

    @field_validator("fair_value_high")
    @classmethod
    def high_at_least_low(cls, v: float, info) -> float:
        low = info.data.get("fair_value_low")
        if low is not None and v < low:
            raise ValueError("fair_value_high must be >= fair_value_low")
        return v
