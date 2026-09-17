from pydantic import BaseModel


class ChunkResult(BaseModel):
    text: str
    source_file: str
    page: int | None
    chunk_id: str
    score: float


class RAGAnswer(BaseModel):
    answer: str
    grounded: str
    citations: list[str]


class ChatRequest(BaseModel):
    question: str
    document_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    grounded: bool
    sources: list[ChunkResult]
