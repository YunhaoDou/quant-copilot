"""Structured-output contract the LLM's per-headline impact classification must satisfy."""
from pydantic import BaseModel, Field


class HeadlineImpactSchema(BaseModel):
    index: int = Field(ge=0)
    impact: str = Field(pattern="^(high|medium|low)$")
    reason: str = Field(min_length=5)


class NewsSentimentSchema(BaseModel):
    items: list[HeadlineImpactSchema]
