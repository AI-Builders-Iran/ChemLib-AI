"""Pydantic request/response models for the Chemistry RAG API."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Request body for a normal chemistry question."""

    question: str = Field(..., min_length=1)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value


class SourceItem(BaseModel):
    """A source used to generate an answer."""

    title: str
    page: int | None = None
    document_id: str


class ChatResponse(BaseModel):
    """Response for a normal RAG question."""

    answer: str
    sources: list[SourceItem]
    grounded: bool


class CompareRequest(BaseModel):
    """Request body for comparing two chemistry sources."""

    question: str = Field(..., min_length=1)

    # Optional because the user may mention the two sources
    # directly in the question.
    source_a: str | None = None
    source_b: str | None = None

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        return value

    @field_validator("source_a", "source_b")
    @classmethod
    def blank_source_to_none(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None


class CompareBookSection(BaseModel):
    """Information retrieved from one source."""

    title: str
    definition: str
    explanation: str
    sources: list[SourceItem]


class CompareResponse(BaseModel):
    """Response for a two-source comparison."""

    book_a: CompareBookSection
    book_b: CompareBookSection
    comparison: str