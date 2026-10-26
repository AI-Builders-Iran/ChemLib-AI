"""Direct access to the existing ChemLib-AI backend — no HTTP hop.

``app/api/api_app.py`` is a separate FastAPI surface for external API
consumers and does not even cover document management (list/upload/delete),
so this module calls the Python services directly instead of going through
it. One long-running process serves many browser clients here, same as a
typical Streamlit deployment, but NiceGUI has no ``st.cache_resource``/
``st.session_state`` equivalent built in. Shared, stateless resources
(embedder, vector store, providers, RAG service) are plain lazy module-level
singletons; anything per-user/per-tab belongs in ``state/session.py``, not
here.

Nothing here reimplements RAG/OCR/extraction/ingestion — it only imports and
calls the existing ``rag/`` and ``src/`` packages.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from rag import archive
from rag.schemas import IndexedDocument, IngestFileResult

logger = logging.getLogger(__name__)

# services -> nicegui_app -> app -> project root
ROOT_DIR = Path(__file__).resolve().parents[3]
VECTOR_DB_DIR = ROOT_DIR / "vector_database" / "chroma_db"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

ProgressCallback = Callable[[int, int, str], None]
# (stage, current, total) - see rag.ingestion.StageCallback
StageCallback = Callable[[str, int, int], None]


class LLMNotConfiguredError(RuntimeError):
    """No LLM provider could be created (missing OPENROUTER_API_KEY)."""


# One lock per singleton, not one shared lock: get_vector_store() and
# get_rag_service() each depend on another of these getters, and a single
# shared lock would deadlock the instant one getter calls another while
# already holding it (the same thread re-acquiring a non-reentrant
# threading.Lock blocks forever — this was the actual cause of the reported
# hang, not model-loading time by itself). Each dependency is resolved
# *before* the dependent getter takes its own lock, so no getter ever calls
# another while holding a lock.
_embedder_lock = threading.Lock()
_vector_store_lock = threading.Lock()
_providers_lock = threading.Lock()
_rag_service_lock = threading.Lock()

_embedder = None
_vector_store = None
_providers: list | None = None
_rag_service = None


# ---------------------------------------------------------------------------
# Shared, stateless singletons — constructing one of these must stay cheap.
# Loading the actual embedding model is deferred further still, inside
# Embedder itself (see src/embedding/embedding.py): holding an Embedder
# reference (e.g. inside a Chroma store, for listing/deleting documents)
# never triggers a model load — only a real embed_query()/embed_documents()
# call does, the first time one actually happens.
# ---------------------------------------------------------------------------

def get_embedder():
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                from src.embedding.embedding import Embedder

                logger.info("[RAG] Creating embedder (model load is deferred until first use)…")
                _embedder = Embedder()
    return _embedder


def get_vector_store():
    """The shared library's vector store (persisted on disk).

    Cheap and fast even on the very first call: connecting to Chroma and
    listing/deleting documents by metadata never touches the embedding
    model (see Embedder's lazy proxy) — only an actual similarity query or
    an add_documents() call does.
    """
    global _vector_store
    if _vector_store is None:
        embedder = get_embedder()  # resolved *before* taking our own lock — see note above
        with _vector_store_lock:
            if _vector_store is None:
                from src.retrieval.vector_store import ChromaVectorStore

                logger.info("[RAG] Connecting to the vector store at %s…", VECTOR_DB_DIR)
                VECTOR_DB_DIR.parent.mkdir(parents=True, exist_ok=True)
                _vector_store = ChromaVectorStore(persist_directory=str(VECTOR_DB_DIR), embedder=embedder)
                logger.info("[RAG] Vector store ready.")
    return _vector_store


def get_providers() -> list:
    """OpenRouter is the only configured LLM provider."""
    global _providers
    if _providers is None:
        with _providers_lock:
            if _providers is None:
                from src.extraction.providers.openrouter_provider import OpenRouterProvider

                try:
                    _providers = [OpenRouterProvider()]
                except Exception as exc:  # noqa: BLE001 - a missing key is the common case
                    raise LLMNotConfiguredError(f"OpenRouter: {exc}") from exc
    return _providers


def make_rag_service(store):
    """A RAG service over any store (the library, or one tab's private store)."""
    from rag.rag_service import RAGService

    return RAGService(vector_store=store, providers=get_providers())


def get_rag_service():
    """RAGService bound to the shared library store."""
    global _rag_service
    if _rag_service is None:
        store = get_vector_store()  # resolved *before* taking our own lock — see note above
        with _rag_service_lock:
            if _rag_service is None:
                _rag_service = make_rag_service(store)
    return _rag_service


def new_session_store():
    """A fresh, in-memory-only vector store for one browser tab's private
    documents — never touches the shared library. Cheap: see get_vector_store's
    note, the same laziness applies. Caller owns its lifetime (see
    ``state/session.py``)."""
    from src.retrieval.session_store import SessionVectorStore

    return SessionVectorStore(get_embedder())


# ---------------------------------------------------------------------------
# Library documents
# ---------------------------------------------------------------------------

def library_documents() -> list[IndexedDocument]:
    return get_vector_store().list_documents()


def private_documents(store) -> list[IndexedDocument]:
    return store.list_documents() if store is not None else []


def delete_document(document_id: str, store=None) -> int:
    """Returns the number of chunks removed."""
    return (store or get_vector_store()).delete_document(document_id)


# ---------------------------------------------------------------------------
# Ingestion (library admin, or a tab's private store when ``store`` is given)
# ---------------------------------------------------------------------------

def _pipeline(store, ocr_mode: str | None = None):
    from rag.ingestion import IngestionPipeline

    return IngestionPipeline(vector_store=store if store is not None else get_vector_store(), ocr_mode=ocr_mode)


def _failed(name: str, detail: str) -> IngestFileResult:
    return IngestFileResult(filename=name, status="failed", detail=detail)


def ingest_upload(
    filename: str,
    data: bytes,
    overwrite: bool,
    store=None,
    ocr_mode: str | None = None,
    on_stage: StageCallback | None = None,
) -> IngestFileResult:
    """Index one uploaded file. Never raises: problems come back in the result."""
    safe_name = Path(filename).name
    if Path(safe_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        return _failed(safe_name, "نوع فایل پشتیبانی نمی‌شود.")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / safe_name  # keep the original name: it is the source label
            path.write_bytes(data)
            return _pipeline(store, ocr_mode).ingest_safe(path, overwrite=overwrite, on_stage=on_stage)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingestion failed for %s", safe_name)
        return _failed(safe_name, str(exc))


def ingest_zip(
    filename: str,
    data: bytes,
    overwrite: bool,
    store=None,
    on_progress: ProgressCallback | None = None,
    ocr_mode: str | None = None,
    on_stage: StageCallback | None = None,
) -> list[IngestFileResult]:
    """Index every PDF/DOCX/TXT inside an uploaded ZIP (a folder of documents)."""
    name = Path(filename).name
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if not archive.extract_supported(data, tmp_dir):
                return [_failed(name, "هیچ فایل PDF، DOCX یا TXT در فایل فشرده پیدا نشد.")]
            return _pipeline(store, ocr_mode).ingest_directory(
                tmp_dir, recursive=True, overwrite=overwrite, on_progress=on_progress, on_stage=on_stage
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
    ocr_mode: str | None = None,
) -> list[IngestFileResult]:
    """Index a folder on the machine running the app (library admin only).

    Raises ``NotADirectoryError`` if the path is not an existing folder.
    """
    folder = Path(path_text.strip().strip('"').strip("'")).expanduser()
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    return _pipeline(None, ocr_mode).ingest_directory(
        folder, recursive=recursive, overwrite=overwrite, on_progress=on_progress
    )


# ---------------------------------------------------------------------------
# Document summarization
# ---------------------------------------------------------------------------

def summarize_document(document_id: str, store=None):
    """Summary of one indexed document (the library when ``store`` is None, else a tab's private store).

    Built from the chunks already stored by ingestion: no re-extraction, no OCR, no embedding.
    Blocking (one or many LLM calls) - call it with ``run.io_bound``. Raises
    ``rag.summarizer.DocumentNotFoundError`` / ``EmptyDocumentError`` / ``SummarizationError`` or
    ``LLMNotConfiguredError``; ``summary_error_message`` turns any of them into Persian text.
    """
    service = make_rag_service(store) if store is not None else get_rag_service()
    return service.summarize_document(document_id)


def summary_error_message(exc: Exception) -> str:
    """A user-readable Persian explanation for a failed summary (technical detail goes elsewhere)."""
    from rag.summarizer import DocumentNotFoundError, EmptyDocumentError, SummarizationError

    if isinstance(exc, DocumentNotFoundError):
        return "این سند در فهرست پیدا نشد؛ ممکن است حذف شده باشد. صفحه را به‌روزرسانی کنید."
    if isinstance(exc, EmptyDocumentError):
        return (
            "از این سند متنی استخراج نشده که بتوان خلاصه کرد. اگر فایل اسکن‌شده است، "
            "OCR را فعال کنید و آن را دوباره بارگذاری کنید."
        )
    if isinstance(exc, LLMNotConfiguredError):
        return "مدل زبانی تنظیم نشده است؛ کلید OPENROUTER_API_KEY را در فایل .env بگذارید."
    if isinstance(exc, SummarizationError):
        return "ساخت خلاصه با خطا روبه‌رو شد. چند لحظهٔ دیگر دوباره تلاش کنید."
    return "خلاصه‌سازی در حال حاضر ممکن نیست. چند لحظهٔ دیگر دوباره تلاش کنید."


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

OCR_ENGINE_LABELS = {
    "rapidocr": "OCR محلی: RapidOCR",
    "paddle": "OCR محلی: PaddleOCR",
    "azure": "OCR آنلاین: Azure Document Intelligence",
    "openrouter": "OCR آنلاین: OpenRouter",
}

OCR_MODE_ONLINE_FIRST = "online_first"
OCR_MODE_LOCAL_ONLY = "local_only"
OCR_MODE_LABELS = {
    OCR_MODE_ONLINE_FIRST: "آنلاین، و اگر نشد محلی",
    OCR_MODE_LOCAL_ONLY: "فقط محلی (بدون ارسال به اینترنت)",
}


def default_ocr_mode() -> str:
    return OCR_MODE_LOCAL_ONLY if os.getenv("OCR_MODE") == OCR_MODE_LOCAL_ONLY else OCR_MODE_ONLINE_FIRST


def local_ocr_ready() -> bool:
    from src.ocr import engine_status

    return any(ready for name, ready, _ in engine_status() if name in ("rapidocr", "paddle"))


# ---------------------------------------------------------------------------
# System status (dashboard / settings) — real checks only, nothing fabricated
# ---------------------------------------------------------------------------

def system_checks() -> list[tuple[str, bool]]:
    """Configuration checklist (label, ready?) — identical to the Streamlit admin's."""
    import importlib.util

    from src.loaders.pdf_pages import pymupdf_installed
    from src.ocr import engine_status

    poppler_dir = os.getenv("POPPLER_PATH")
    poppler_ok = Path(poppler_dir).is_dir() if poppler_dir else shutil.which("pdftoppm") is not None

    checks = [
        ("کلید OpenRouter (پاسخ‌گویی و OCR آنلاین)", bool(os.getenv("OPENROUTER_API_KEY"))),
        ("PyMuPDF یا Poppler (خواندن PDFهای اسکن‌شده)", pymupdf_installed() or poppler_ok),
    ]
    checks += [(OCR_ENGINE_LABELS.get(name, name), ready) for name, ready, _ in engine_status()]
    checks.append(("wordninja (فاصله‌گذاری متن OCR محلی)", importlib.util.find_spec("wordninja") is not None))

    from src.layout.engines import PPStructureSegmenter

    checks.append(
        (
            "لایه‌بندی جدول/فرمول/شکل با PP-StructureV3 (نیازمند نصب paddleocr/paddlepaddle)",
            PPStructureSegmenter().available(),
        )
    )
    return checks


def library_stats() -> dict:
    """Real counts from the shared library — nothing here is simulated."""
    try:
        documents = library_documents()
    except Exception:  # noqa: BLE001
        logger.exception("Could not read the library")
        return {"documents": 0, "chunks": 0, "available": False}
    return {"documents": len(documents), "chunks": sum(d.chunks for d in documents), "available": True}
