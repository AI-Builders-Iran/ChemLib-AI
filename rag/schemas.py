import re

from pydantic import BaseModel, Field


class ChunkResult(BaseModel):
    text: str
    source_file: str
    page: int | None = None
    chunk_id: str
    document_id: str
    score: float = 0.0
    block_type: str = "text"  # "text" | "table" | "formula" | "figure" — see src.layout


_CHUNK_INDEX = re.compile(r"_c(\d+)$")


def chunk_order(chunk: ChunkResult) -> tuple[int, int]:
    """Sort key that restores reading order for the chunks of one document.

    Ingestion numbers chunks sequentially (``<document_id>_c<n>``), so the numeric
    suffix is the order they appear in the file. Chunks without such a suffix go last,
    ordered by page.
    """
    match = _CHUNK_INDEX.search(chunk.chunk_id)
    if match:
        return (0, int(match.group(1)))
    return (1, chunk.page if chunk.page is not None else -1)


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
    block_type: str = "text"
    # Short excerpt of the cited passage, for a citation preview in the UI.
    # Optional and additive: existing API consumers that ignore it are unaffected.
    snippet: str = ""


class ChatRequest(BaseModel):
    question: str
    document_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    grounded: bool
    sources: list[SourceItem]


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
    ocr_pages: dict[str, int] = Field(default_factory=dict)  # engine name -> pages read by OCR
    unread_pages: int = 0  # scanned pages no OCR engine could read
    skipped_figure_pages: int = 0  # scanned pages intentionally not OCR'd (figure/diagram, no table)
    # Processing metrics - only values the pipeline actually measured (0 when not applicable).
    pages: int = 0
    text_layer_pages: int = 0
    failed_pages: int = 0  # pages that errored or that no OCR engine could read
    figure_regions_skipped: int = 0  # figures found inside pages and skipped (MVP: no LLM/VLM call)
    tables: int = 0
    embeddings: int = 0  # chunks embedded and stored
    seconds: float = 0.0  # wall-clock processing time
    stage_seconds: dict[str, float] = Field(default_factory=dict)  # load / chunking / embedding


# ---------------------------------------------------------------------------
# Document summarization
# ---------------------------------------------------------------------------

class PartialSummary(BaseModel):
    """LLM output for one section of a long document (the "map" step), or for a merge of several."""

    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)


class FinalSummary(BaseModel):
    """LLM output for the whole document (the "reduce" step, or a single pass for short documents)."""

    title: str = ""
    overview: str = ""
    key_points: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)


class SummaryRequest(BaseModel):
    document_id: str


class SummaryResponse(BaseModel):
    document_id: str
    source_file: str
    title: str
    language: str  # "fa" | "en" - the language the summary was written in (the document's language)
    overview: str
    key_points: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    strategy: str = "single_pass"  # "single_pass" | "map_reduce"
    chunks_used: int = 0
    sections_total: int = 1  # sections the text was split into (1 for a single pass)
    sections_summarized: int = 1  # sections that actually made it into the summary
    coverage: float = 1.0  # share of the document's text that the summary was built from (0..1)
    llm_calls: int = 0  # 0 when served from the cache
    cached: bool = False
    warnings: list[str] = Field(default_factory=list)
