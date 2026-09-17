"""
DocumentAI FastAPI backend.

A small REST API around the real DocumentAI pipeline (Person 1 loading/
cleaning/chunking + Person 2 extraction + Person 3 orchestration):

    POST /api/v1/extract
        multipart/form-data:
            file           -> the PDF/DOCX/TXT document
            document_type  -> "invoice" | "contract" | "general"
            provider       -> "gemini" | "openrouter" (default: "gemini")
            api_key        -> optional, overrides the server's env var for
                               this one request only (never stored/logged)

Run locally:
    uvicorn app.api.api_app:app --reload --port 8000

Then open http://localhost:8000/docs for the interactive Swagger UI, where
you can upload a file and paste your own API key directly from the browser.
"""

from __future__ import annotations

import tempfile
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.extraction.extractor import DocumentExtractor
from src.extraction.providers.gemini_provider import GeminiProvider
from src.extraction.providers.openrouter_provider import OpenRouterProvider
from src.pipeline import DocumentPipeline
from src.schemas.common import DocumentType
from src.utils import model_to_dict

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


class Provider(str, Enum):
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


app = FastAPI(
    title="DocumentAI API",
    description=(
        "Upload an invoice or contract (PDF/DOCX/TXT) and get back "
        "structured, validated JSON extracted by an LLM (Gemini or "
        "OpenRouter)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        # Raised by the provider constructors when no key is available.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return DocumentExtractor(providers=[llm_provider])


@app.get("/", tags=["Meta"])
def root():
    return {"service": "DocumentAI API", "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok"}


@app.get("/api/v1/document-types", tags=["Meta"])
def list_document_types():
    return {"document_types": [t.value for t in DocumentType]}


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
            # File-loading errors or "all providers failed" errors.
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc

    return {
        "document_type": document_type.value,
        "provider": provider.value,
        "filename": file.filename,
        "data": model_to_dict(result),
    }
