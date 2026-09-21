"""Backend access for the UI: cached heavy objects, ingestion and status checks.

The embedding model (BGE-M3) and the Chroma client are expensive to create, so
they live in ``st.cache_resource`` and are shared by every browser session of
the running Streamlit process.

Project modules are imported inside the functions on purpose: ``app.py`` loads
``.env`` first, and some modules (OCR) read environment variables at import time.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

import streamlit as st

from rag.schemas import IngestFileResult

from . import archive

logger = logging.getLogger(__name__)

# docai_ui -> streamlit_app -> app -> project root
ROOT_DIR = Path(__file__).resolve().parents[3]
VECTOR_DB_DIR = ROOT_DIR / "vector_database" / "chroma_db"

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# Kept under the old name: the admin/chat views import it from here.
IngestOutcome = IngestFileResult

ProgressCallback = Callable[[int, int, str], None]

PRIVATE_STORE_KEY = "dx_private_store"


class LLMNotConfiguredError(RuntimeError):
    """No LLM provider could be created (missing API keys)."""


# ---------------------------------------------------------------------------
# Cached backend objects (shared by all sessions)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="در حال بارگذاری مدل جست‌وجو. بار اول چند دقیقه طول می‌کشد…")
def get_embedder():
    from src.embedding.embedding import Embedder

    return Embedder()


@st.cache_resource(show_spinner=False)
def get_vector_store():
    from src.retrieval.vector_store import ChromaVectorStore

    VECTOR_DB_DIR.parent.mkdir(parents=True, exist_ok=True)
    return ChromaVectorStore(persist_directory=str(VECTOR_DB_DIR), embedder=get_embedder())


@st.cache_resource(show_spinner=False)
def get_providers():
    """Gemini is primary, OpenRouter the fallback; at least one key is required."""
    from src.extraction.providers.gemini_provider import GeminiProvider
    from src.extraction.providers.openrouter_provider import OpenRouterProvider

    providers = []
    problems: list[str] = []
    for name, factory in (("Gemini", GeminiProvider), ("OpenRouter", OpenRouterProvider)):
        try:
            providers.append(factory())
        except Exception as exc:  # noqa: BLE001 - a missing key is the common case
            problems.append(f"{name}: {exc}")

    if not providers:
        raise LLMNotConfiguredError(" | ".join(problems))
    return providers


def make_rag_service(store):
    """A RAG service over any store (the library, or one user's private store)."""
    from rag.rag_service import RAGService

    return RAGService(vector_store=store, providers=get_providers())


@st.cache_resource(show_spinner=False)
def get_rag_service():
    return make_rag_service(get_vector_store())


@st.cache_data(ttl=30, show_spinner=False)
def library_documents():
    """Documents currently indexed (cached briefly; call ``refresh_library`` after changes)."""
    return get_vector_store().list_documents()


def refresh_library() -> None:
    library_documents.clear()


# ---------------------------------------------------------------------------
# Private, temporary documents (one browser session, memory only)
# ---------------------------------------------------------------------------

def private_store():
    """This session's in-memory store; created on first use, never persisted."""
    from src.retrieval.session_store import SessionVectorStore

    if PRIVATE_STORE_KEY not in st.session_state:
        st.session_state[PRIVATE_STORE_KEY] = SessionVectorStore(get_embedder())
    return st.session_state[PRIVATE_STORE_KEY]


def private_documents():
    store = st.session_state.get(PRIVATE_STORE_KEY)
    return store.list_documents() if store is not None else []


def clear_private_store() -> None:
    store = st.session_state.pop(PRIVATE_STORE_KEY, None)
    if store is not None:
        store.clear()


# ---------------------------------------------------------------------------
# Ingestion (library admin, or a user's private store when ``store`` is given)
# ---------------------------------------------------------------------------

def _pipeline(store):
    from rag.ingestion import IngestionPipeline

    return IngestionPipeline(vector_store=store if store is not None else get_vector_store())


def _failed(name: str, detail: str) -> IngestFileResult:
    return IngestFileResult(filename=name, status="failed", detail=detail)


def ingest_upload(filename: str, data: bytes, overwrite: bool, store=None) -> IngestFileResult:
    """Index one uploaded file. Never raises: problems come back in the result."""
    safe_name = Path(filename).name
    if Path(safe_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        return _failed(safe_name, "Unsupported file type.")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / safe_name  # keep the original name: it is the source label
            path.write_bytes(data)
            return _pipeline(store).ingest_safe(path, overwrite=overwrite)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingestion failed for %s", safe_name)
        return _failed(safe_name, str(exc))


def ingest_zip(
    filename: str,
    data: bytes,
    overwrite: bool,
    store=None,
    on_progress: ProgressCallback | None = None,
) -> list[IngestFileResult]:
    """Index every PDF/DOCX/TXT inside an uploaded ZIP (a folder of documents)."""
    name = Path(filename).name
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if not archive.extract_supported(data, tmp_dir):
                return [_failed(name, "No PDF, DOCX or TXT files were found in the archive.")]
            return _pipeline(store).ingest_directory(
                tmp_dir, recursive=True, overwrite=overwrite, on_progress=on_progress
            )
    except archive.ArchiveError as exc:
        return [_failed(name, str(exc))]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Archive ingestion failed for %s", name)
        return [_failed(name, str(exc))]


def ingest_folder(
    path_text: str,
    recursive: bool,
    overwrite: bool,
    on_progress: ProgressCallback | None = None,
) -> list[IngestFileResult]:
    """Index a folder on the machine running the app (library admin only).

    Raises ``NotADirectoryError`` if the path is not an existing folder.
    """
    # Windows' "Copy as path" wraps the path in quotes.
    folder = Path(path_text.strip().strip('"').strip("'")).expanduser()
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    return _pipeline(None).ingest_directory(
        folder, recursive=recursive, overwrite=overwrite, on_progress=on_progress
    )


def delete_document(document_id: str) -> int:
    count = get_vector_store().delete_document(document_id)
    refresh_library()
    return count


def system_checks() -> list[tuple[str, bool]]:
    """Configuration checklist shown to the admin (label, ready?)."""
    poppler_dir = os.getenv("POPPLER_PATH")
    poppler_ok = Path(poppler_dir).is_dir() if poppler_dir else shutil.which("pdftoppm") is not None

    return [
        ("کلید Gemini (پاسخ‌گویی و OCR)", bool(os.getenv("GEMINI_API_KEY"))),
        ("کلید OpenRouter (پشتیبان، اختیاری)", bool(os.getenv("OPENROUTER_API_KEY"))),
        ("Poppler (برای PDFهای اسکن‌شده)", poppler_ok),
    ]
