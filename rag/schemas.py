from pydantic import BaseModel, Field


class ChunkResult(BaseModel):
    text: str
    source_file: str
    page: int | None = None
    chunk_id: str
    document_id: str
    score: float = 0.0


class OCRResult(BaseModel):
    text: str


class RAGAnswer(BaseModel):
    answer: str
    grounded: bool
    citations: list[str] = Field(default_factory=list)


class SourceItem(BaseModel):
    source_file: str
    page: int | None = None
    chunk_id: str


class ChatRequest(BaseModel):
    question: str
    document_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    grounded: bool
    sources: list[SourceItem]
    # Set only when the primary LLM failed and a backup answered instead.
    fallback_provider: str | None = None  # e.g. "OpenRouter"
    fallback_model: str | None = None  # e.g. "openrouter/auto"
    failed_providers: list[str] = Field(default_factory=list)  # e.g. ["Gemini"]


class CompareAnswer(BaseModel):
    definition_a: str
    explanation_a: str
    definition_b: str
    explanation_b: str
    comparison: str
    grounded: bool


class CompareRequest(BaseModel):
    question: str
    source_a: str
    source_b: str


class CompareBookSection(BaseModel):
    title: str
    definition: str
    explanation: str
    sources: list[SourceItem]


class CompareResponse(BaseModel):
    book_a: CompareBookSection
    book_b: CompareBookSection
    comparison: str


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    chunks_indexed: int


class IndexedDocument(BaseModel):
    """One document currently stored in the vector database (admin/catalog view)."""

    document_id: str
    source_file: str
    chunks: int


class IngestFileResult(BaseModel):
    """Outcome of indexing one file (single upload, folder or archive).

    status: "added" | "replaced" | "skipped" (already indexed) | "empty" (no text
    could be extracted) | "duplicate_name" (same file name twice in one batch) |
    "failed".
    """

    filename: str
    status: str
    chunks: int = 0
    detail: str = ""
    old_version_removed: bool = False