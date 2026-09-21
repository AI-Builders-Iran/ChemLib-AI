"""
DocumentAI FastAPI backend.

Two feature sets share this app:

1) Structured extraction (invoice/contract/general) — unchanged from the
   original pipeline:
    POST /api/v1/extract

2) Chemistry library RAG — chat and compare over an indexed document set:
    POST /api/v1/ingest   -> index a PDF/DOCX/TXT into the vector store
                             (library-admin only: send the ADMIN_PASSWORD in the
                             X-Admin-Password header when ADMIN_PASSWORD is set)
    POST /api/v1/ingest/batch -> index several files (a "folder") in one call,
                             same admin protection as /ingest
    POST /api/v1/chat     -> ask a grounded question
    POST /api/v1/compare  -> compare a concept across two ingested sources

Run locally:
    uvicorn app.api.api_app:app --reload --port 8000

Then open http://localhost:8000/docs for the interactive Swagger UI.
"""

from __future__ import annotations

import hmac
import os
import tempfile
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi import Form
from fastapi.middleware.cors import CORSMiddleware

# Load .env before the project modules are imported: some of them (e.g. OCR's
# POPPLER_PATH) read environment variables at import time.
load_dotenv()

from rag.ingestion import IngestionPipeline
from rag.rag_service import RAGService
from rag.schemas import (
    ChatRequest,
    ChatResponse,
    CompareRequest,
    CompareResponse,
    IngestFileResult,
    IngestResponse,
)
from src.extraction.extractor import DocumentExtractor
from src.extraction.providers.base import LLMProvider
from src.extraction.providers.gemini_provider import GeminiProvider
from src.extraction.providers.openrouter_provider import OpenRouterProvider
from src.pipeline import DocumentPipeline
from src.retrieval.vector_store import ChromaVectorStore
from src.schemas.common import DocumentType
from src.utils import model_to_dict

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class Provider(str, Enum):
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


app = FastAPI(
    title="DocumentAI API",
    description=(
        "Structured document extraction (invoice/contract) plus a RAG "
        "chat & compare API over an indexed chemistry library."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Extraction (unchanged feature)
# ---------------------------------------------------------------------------

def build_extractor(provider: Provider, api_key: str | None) -> DocumentExtractor:
    """Builds a DocumentExtractor for the chosen provider.

    If ``api_key`` is given, it is used for this request only. Otherwise the
    provider falls back to its own environment variable
    (GEMINI_API_KEY / OPENROUTER_API_KEY).
    """
    try:
        if provider == Provider.GEMINI:
            llm_provider = GeminiProvider(api_key=api_key or None)
        else:
            llm_provider = OpenRouterProvider(api_key=api_key or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DocumentExtractor(providers=[llm_provider])


@app.post("/api/v1/extract", tags=["Extraction"])
async def extract_document(
    file: UploadFile = File(..., description="The document file (PDF, DOCX, or TXT)."),
    document_type: DocumentType = Form(
        default=DocumentType.GENERAL, description="Type of document to extract."
    ),
    provider: Provider = Form(
        default=Provider.GEMINI, description="LLM provider to use for extraction."
    ),
    api_key: str | None = Form(
        default=None,
        description=(
            "Your API key for the selected provider. Leave empty to use the "
            "server's GEMINI_API_KEY / OPENROUTER_API_KEY environment "
            "variable instead. Never stored or logged."
        ),
    ),
):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{extension}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    extractor = build_extractor(provider, api_key)
    pipeline = DocumentPipeline(extractor=extractor)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        tmp_path.write_bytes(await file.read())

        try:
            result = pipeline.run(tmp_path, document_type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    return {
        "document_type": document_type.value,
        "provider": provider.value,
        "filename": file.filename,
        "data": model_to_dict(result),
    }


def require_admin(x_admin_password: str | None = Header(default=None)) -> None:
    """Protects library-management endpoints.

    When ADMIN_PASSWORD is set, the caller must send it in the
    ``X-Admin-Password`` header. When it is not set (local development),
    the endpoint stays open.
    """
    expected = os.getenv("ADMIN_PASSWORD")
    if not expected:
        return
    supplied = (x_admin_password or "").encode("utf-8")
    if not hmac.compare_digest(supplied, expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Admin password required.")


# ---------------------------------------------------------------------------
# RAG: ingest / chat / compare
# ---------------------------------------------------------------------------
# The embedding model and vector store are expensive to load (multi-second
# model load), so they are created once per process, not per request.

_vector_store: ChromaVectorStore | None = None
_rag_service: RAGService | None = None


def get_vector_store() -> ChromaVectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = ChromaVectorStore()
    return _vector_store


def get_rag_service() -> RAGService:
    """Gemini is primary; OpenRouter is added as a fallback only if configured."""
    global _rag_service
    if _rag_service is None:
        providers: list[LLMProvider] = [GeminiProvider()]
        try:
            providers.append(OpenRouterProvider())
        except ValueError:
            pass  # OPENROUTER_API_KEY not set — fallback simply unavailable
        _rag_service = RAGService(vector_store=get_vector_store(), providers=providers)
    return _rag_service


@app.post(
    "/api/v1/ingest",
    response_model=IngestResponse,
    tags=["RAG"],
    dependencies=[Depends(require_admin)],
)
async def ingest_document(
    file: UploadFile = File(..., description="PDF/DOCX/TXT to index into the library."),
):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{extension}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / file.filename
        tmp_path.write_bytes(await file.read())

        try:
            pipeline = IngestionPipeline(vector_store=get_vector_store())
            document_id, chunks_indexed = pipeline.ingest(tmp_path)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc

    return IngestResponse(
        document_id=document_id,
        filename=file.filename,
        chunks_indexed=chunks_indexed,
    )


@app.post(
    "/api/v1/ingest/batch",
    response_model=list[IngestFileResult],
    tags=["RAG"],
    dependencies=[Depends(require_admin)],
)
async def ingest_batch(
    files: list[UploadFile] = File(..., description="PDF/DOCX/TXT files to index (a whole folder can be sent)."),
    overwrite: bool = Form(False, description="Replace documents whose file name is already indexed."),
):
    """Index many files in one request. One bad file does not stop the others;
    every file gets its own result (added / replaced / skipped / empty / failed)."""
    results: list[IngestFileResult] = []
    accepted: set[str] = set()

    with tempfile.TemporaryDirectory() as tmp_dir:
        for upload in files:
            name = Path(upload.filename or "").name
            extension = Path(name).suffix.lower()

            if extension not in SUPPORTED_EXTENSIONS:
                results.append(
                    IngestFileResult(filename=name or "(no name)", status="failed",
                                     detail=f"Unsupported file type '{extension}'.")
                )
            elif name in accepted:
                results.append(
                    IngestFileResult(filename=name, status="duplicate_name",
                                     detail="Same file name sent twice in this request.")
                )
            else:
                accepted.add(name)
                (Path(tmp_dir) / name).write_bytes(await upload.read())

        try:
            pipeline = IngestionPipeline(vector_store=get_vector_store())
            results.extend(pipeline.ingest_directory(tmp_dir, recursive=False, overwrite=overwrite))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Batch ingestion failed: {exc}") from exc

    return results


@app.post("/api/v1/chat", response_model=ChatResponse, tags=["RAG"])
async def chat(request: ChatRequest):
    try:
        return get_rag_service().answer_question(request.question, request.document_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Chat failed: {exc}") from exc


@app.post("/api/v1/compare", response_model=CompareResponse, tags=["RAG"])
async def compare(request: CompareRequest):
    try:
        return get_rag_service().compare_sources(request.question, request.source_a, request.source_b)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Compare failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

@app.get("/", tags=["Meta"])
def root():
    return {"service": "DocumentAI API", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok"}


@app.get("/api/v1/document-types", tags=["Meta"])
def list_document_types():
    return {"document_types": [t.value for t in DocumentType]}
