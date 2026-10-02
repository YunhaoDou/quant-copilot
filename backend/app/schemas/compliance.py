"""Structured-output contract the LLM's grounded compliance answer must satisfy."""
from pydantic import BaseModel, Field


class ComplianceAnswerSchema(BaseModel):
    answer: str = Field(min_length=10)
    citations: list[str] = Field(min_length=1)
