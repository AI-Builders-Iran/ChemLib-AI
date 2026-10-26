"""Load -> clean -> chunk -> embed -> store a document into the vector store."""

import hashlib
import logging
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from rag.schemas import ChunkResult, IngestFileResult
from src.loaders.document_loader import DocumentLoader
from src.processing.chunking.structure_aware import StructureAwareChunker
from src.processing.cleaners.persian import (
    LineWrapCleaner,
    PersianCharacterCleaner,
    PersianSpacingCleaner,
)
from src.processing.cleaners.text import TextCleaner
from src.processing.cleaners.unicode import UnicodeCleaner
from src.processing.cleaners.whitespace import WhitespaceCleaner
from src.processing.pipeline import DocumentProcessor
from src.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# (index starting at 1, total files, file name) - lets a UI show progress.
ProgressCallback = Callable[[int, int, str], None]

# (stage, current, total): stage is "reading" / "ocr" (current/total = page numbers),
# "chunking", "embedding" (chunks done / chunks total) or "saving". Lets a UI show where a long
# document is; it never decides anything. Exceptions raised by the callback are ignored.
StageCallback = Callable[[str, int, int], None]

EMBED_BATCH_SIZE = 64  # chunks embedded + written per call: bounded memory, real progress, small rollbacks


class IngestionStageError(RuntimeError):
    """Ingestion failed in a known stage ("loading", "embedding", ...); ``str()`` is user-readable."""

    def __init__(self, stage: str, reason: str):
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


def make_document_id(file: Path) -> str:
    """Deterministic short id derived from the file name (safe for non-ASCII names)."""
    digest = hashlib.sha1(file.name.encode("utf-8")).hexdigest()[:10]
    return digest


class IngestionPipeline:
    """Runs the full ingestion pipeline for one file and indexes it."""

    def __init__(
        self,
        vector_store=None,
        persian: bool = True,
        ocr_mode: str | None = None,
        layout_engine: str | None = None,
    ) -> None:
        """
        Args:
            vector_store: any store with add/has_document/delete_document
                (ChromaVectorStore, or the in-memory SessionVectorStore).
            persian: apply the Persian cleaners (canonical letters and digits,
                half-spaces, wrapped-line joining). Documents indexed with them
                must be searched with ``normalize_query``, which the stores do.
            ocr_mode: for scanned PDF pages, "online_first" (cloud OCR, local as
                fallback) or "local_only" (nothing leaves the machine). Default:
                the OCR_MODE environment variable, then "online_first".
            layout_engine: "ppstructure" (default) or "none" — whether to also
                pull tables/formulas/figures out as their own chunks via
                PP-StructureV3. Default: the LAYOUT_ENGINE environment
                variable, then "ppstructure" (falls back to "none" if
                paddleocr/paddlepaddle aren't installed). See ``src.layout``.
        """
        self._ocr_mode = ocr_mode
        self._layout_engine = layout_engine
        self.last_extraction: Counter = Counter()  # how the last file's pages were read
        self.last_report = None  # PDFLoadReport of the last PDF (None for DOCX/TXT)
        self.last_metrics: dict = {}  # real measurements of the last ingest() call
        cleaners = [UnicodeCleaner(), TextCleaner()]
        if persian:
            cleaners += [PersianCharacterCleaner(), PersianSpacingCleaner(), LineWrapCleaner()]
        cleaners.append(WhitespaceCleaner())

        self._processor = DocumentProcessor(cleaners=cleaners)
        self._chunker = StructureAwareChunker()
        self._vector_store = vector_store or ChromaVectorStore()

    @staticmethod
    def _notify(on_stage: StageCallback | None, stage: str, current: int = 0, total: int = 0) -> None:
        if on_stage is None:
            return
        try:
            on_stage(stage, current, total)
        except Exception:  # noqa: BLE001 - a UI callback must never break ingestion
            logger.warning("Stage callback failed (ignored)", exc_info=True)

    def ingest(
        self,
        file: str | Path,
        document_id: str | None = None,
        on_stage: StageCallback | None = None,
    ) -> tuple[str, int]:
        """
        Ingest one file into the vector store.

        Returns:
            (document_id, chunks_indexed)

        Raises:
            IngestionStageError: the file could not be loaded, or embedding/saving failed
                (in that case chunks already written for this document are removed again,
                so a failed ingestion never leaves a half-indexed document behind).
        """
        file = Path(file)
        document_id = document_id or make_document_id(file)
        started = time.monotonic()
        metrics: dict = {"stage_seconds": {}}
        self.last_metrics = metrics
        self.last_report = None

        t0 = time.monotonic()
        try:
            raw_documents, report = DocumentLoader.load_with_report(
                file,
                ocr_mode=self._ocr_mode,
                layout_engine=self._layout_engine,
                on_progress=lambda stage, page, total: self._notify(on_stage, stage, page, total),
            )
        except Exception as exc:  # noqa: BLE001 - unreadable/corrupt/unsupported file
            raise IngestionStageError("loading", f"{type(exc).__name__}: {exc}") from exc
        metrics["stage_seconds"]["load"] = round(time.monotonic() - t0, 2)
        self.last_report = report
        self.last_extraction = Counter(d.metadata.get("extraction") for d in raw_documents or [])

        t0 = time.monotonic()
        self._notify(on_stage, "chunking")
        chunk_results = self._build_chunks(file, document_id, raw_documents or [])
        metrics["stage_seconds"]["chunking"] = round(time.monotonic() - t0, 2)

        t0 = time.monotonic()
        self._store_chunks(file, document_id, chunk_results, on_stage)
        metrics["stage_seconds"]["embedding"] = round(time.monotonic() - t0, 2)

        metrics["chunks"] = len(chunk_results)
        metrics["embeddings"] = len(chunk_results)
        metrics["seconds"] = round(time.monotonic() - started, 2)
        logger.info(
            "Ingested %s: chunks=%d, stages: load %.1fs, chunking %.1fs, embedding+store %.1fs, total %.1fs",
            file.name, len(chunk_results), *(metrics["stage_seconds"][k] for k in ("load", "chunking", "embedding")),
            metrics["seconds"],
        )
        return document_id, len(chunk_results)

    def _build_chunks(self, file: Path, document_id: str, raw_documents: list) -> list[ChunkResult]:
        try:
            cleaned_documents = self._processor.process(raw_documents)
        except Exception as exc:  # noqa: BLE001
            raise IngestionStageError("cleaning", f"{type(exc).__name__}: {exc}") from exc

        chunk_results: list[ChunkResult] = []
        chunk_index = 0

        for document in cleaned_documents:
            try:
                chunk_documents = self._chunker.chunk(document)
            except Exception as exc:  # noqa: BLE001 - one odd page must not lose the whole file
                logger.warning(
                    "Chunking failed file=%s page=%s stage=chunking reason=%s: %s (page skipped)",
                    file.name, document.metadata.get("page"), type(exc).__name__, exc,
                )
                continue

            for chunk_document in chunk_documents:
                text = chunk_document.page_content.strip()
                if not text:
                    continue

                chunk_id = f"{document_id}_c{chunk_index}"
                chunk_index += 1

                page = chunk_document.metadata.get("page")
                chunk_results.append(
                    ChunkResult(
                        text=text,
                        source_file=file.name,
                        page=page,
                        chunk_id=chunk_id,
                        document_id=document_id,
                        score=0.0,
                        block_type=chunk_document.metadata.get("block_type", "text"),
                    )
                )
        return chunk_results

    def _store_chunks(
        self, file: Path, document_id: str, chunk_results: list[ChunkResult], on_stage: StageCallback | None
    ) -> None:
        """Embed + write in batches. If a batch fails, remove what this call already wrote."""
        total = len(chunk_results)
        written = 0
        try:
            for start in range(0, total, EMBED_BATCH_SIZE):
                self._notify(on_stage, "embedding", start, total)
                self._vector_store.add(chunk_results[start:start + EMBED_BATCH_SIZE])
                written = min(start + EMBED_BATCH_SIZE, total)
            self._notify(on_stage, "saving", total, total)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Ingestion failed for document=%s stage=embedding/vector-store reason=%s: %s "
                "(chunks written so far: %d/%d; rolling back)",
                file.name, type(exc).__name__, exc, written, total, exc_info=True,
            )
            if written or total:
                try:
                    self._vector_store.delete_document(document_id)
                except Exception:  # noqa: BLE001
                    logger.error("Rollback failed for document=%s: the index may hold partial data", file.name, exc_info=True)
            raise IngestionStageError("embedding", f"{type(exc).__name__}: {exc}") from exc

    # ------------------------------------------------------------------
    # Batch helpers: one file that never raises, and whole folders
    # ------------------------------------------------------------------

    def ingest_safe(
        self, file: str | Path, overwrite: bool = False, on_stage: StageCallback | None = None
    ) -> IngestFileResult:
        """Index one file and report the outcome instead of raising.

        A file whose id is already stored is skipped unless ``overwrite`` is set,
        in which case the old version is deleted first.
        """
        file = Path(file)
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return IngestFileResult(
                filename=file.name, status="failed", detail=f"Unsupported file type '{file.suffix}'."
            )

        removed = False
        try:
            document_id = make_document_id(file)
            exists = self._vector_store.has_document(document_id)
            if exists and not overwrite:
                return IngestFileResult(filename=file.name, status="skipped")
            if exists:
                self._vector_store.delete_document(document_id)
                removed = True

            _, chunks = self.ingest(file, document_id, on_stage=on_stage)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop a batch
            stage = getattr(exc, "stage", "ingestion")
            logger.error(
                "PDF ingestion failed for file=%s stage=%s reason=%s", file.name, stage, exc, exc_info=True
            )
            return IngestFileResult(
                filename=file.name, status="failed", detail=str(exc), old_version_removed=removed
            )

        report = self.last_report
        metrics = {
            "pages": getattr(report, "total_pages", 0),
            "text_layer_pages": getattr(report, "text_layer_pages", 0),
            "failed_pages": len(set(getattr(report, "failed_pages", []) or []) | set(getattr(report, "errored_pages", []) or [])),
            "figure_regions_skipped": getattr(report, "skipped_figure_regions", 0),
            "tables": getattr(report, "structured_blocks", Counter()).get("table", 0) if report else 0,
            "embeddings": self.last_metrics.get("embeddings", 0),
            "seconds": self.last_metrics.get("seconds", 0.0),
            "stage_seconds": dict(self.last_metrics.get("stage_seconds", {})),
        }

        ocr_pages = {
            method.removeprefix("ocr:"): count
            for method, count in self.last_extraction.items()
            if method and method.startswith("ocr:")
        }
        unread = self.last_extraction.get("none", 0)
        skipped_figures = self.last_extraction.get("skipped:figure", 0)

        if chunks == 0:
            return IngestFileResult(
                filename=file.name, status="empty", old_version_removed=removed,
                ocr_pages=ocr_pages, unread_pages=unread, skipped_figure_pages=skipped_figures, **metrics,
            )
        return IngestFileResult(
            filename=file.name,
            status="replaced" if removed else "added",
            chunks=chunks,
            ocr_pages=ocr_pages,
            unread_pages=unread,
            skipped_figure_pages=skipped_figures,
            **metrics,
        )

    def ingest_directory(
        self,
        directory: str | Path,
        *,
        recursive: bool = True,
        overwrite: bool = False,
        on_progress: ProgressCallback | None = None,
        on_stage: StageCallback | None = None,
    ) -> list[IngestFileResult]:
        """Index every supported file (PDF/DOCX/TXT) in a folder.

        Hidden files, Word lock files (``~$...``) and macOS ``__MACOSX`` entries are
        ignored. Document ids come from the file name, so a second file with the same
        name in another sub-folder is reported as ``duplicate_name`` and not indexed.
        """
        directory = Path(directory)
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        candidates = directory.rglob("*") if recursive else directory.iterdir()
        files = sorted(
            path
            for path in candidates
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
            and not path.name.startswith((".", "~$"))
            and "__MACOSX" not in path.relative_to(directory).parts
        )

        results: list[IngestFileResult] = []
        seen: dict[str, Path] = {}

        for index, path in enumerate(files, start=1):
            if on_progress:
                on_progress(index, len(files), path.name)

            document_id = make_document_id(path)
            if document_id in seen:
                results.append(
                    IngestFileResult(
                        filename=path.name,
                        status="duplicate_name",
                        detail=f"Same file name as {seen[document_id].relative_to(directory)}",
                    )
                )
                continue

            seen[document_id] = path
            results.append(self.ingest_safe(path, overwrite=overwrite, on_stage=on_stage))

        return results
