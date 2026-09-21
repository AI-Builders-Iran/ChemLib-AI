"""Load -> clean -> chunk -> embed -> store a document into the vector store."""

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from rag.schemas import ChunkResult, IngestFileResult
from src.loaders.document_loader import DocumentLoader
from src.processing.chunking.recursive import RecursiveChunker
from src.processing.cleaners.text import TextCleaner
from src.processing.cleaners.unicode import UnicodeCleaner
from src.processing.cleaners.whitespace import WhitespaceCleaner
from src.processing.pipeline import DocumentProcessor
from src.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# (index starting at 1, total files, file name) - lets a UI show progress.
ProgressCallback = Callable[[int, int, str], None]


def make_document_id(file: Path) -> str:
    """Deterministic short id derived from the file name (safe for non-ASCII names)."""
    digest = hashlib.sha1(file.name.encode("utf-8")).hexdigest()[:10]
    return digest


class IngestionPipeline:
    """Runs the full ingestion pipeline for one file and indexes it."""

    def __init__(self, vector_store=None) -> None:
        # Any store with add/has_document/delete_document works (ChromaVectorStore or
        # the in-memory SessionVectorStore).
        self._processor = DocumentProcessor(
            cleaners=[UnicodeCleaner(), TextCleaner(), WhitespaceCleaner()]
        )
        self._chunker = RecursiveChunker()
        # `is not None`, not `or`: an empty SessionVectorStore has len() == 0 and would be
        # falsy, silently swapping the private store for the shared Chroma library.
        self._vector_store = vector_store if vector_store is not None else ChromaVectorStore()

    def ingest(self, file: str | Path, document_id: str | None = None) -> tuple[str, int]:
        """
        Ingest one file into the vector store.

        Returns:
            (document_id, chunks_indexed)
        """
        file = Path(file)
        document_id = document_id or make_document_id(file)

        raw_documents = DocumentLoader.load(file)
        cleaned_documents = self._processor.process(raw_documents)

        chunk_results: list[ChunkResult] = []
        chunk_index = 0

        for document in cleaned_documents:
            for chunk_document in self._chunker.chunk(document):
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
                    )
                )

        if chunk_results:
            self._vector_store.add(chunk_results)

        return document_id, len(chunk_results)

    # ------------------------------------------------------------------
    # Batch helpers: one file that never raises, and whole folders
    # ------------------------------------------------------------------

    def ingest_safe(self, file: str | Path, overwrite: bool = False) -> IngestFileResult:
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

            _, chunks = self.ingest(file, document_id)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop a batch
            logger.exception("Ingestion failed for %s", file.name)
            return IngestFileResult(
                filename=file.name, status="failed", detail=str(exc), old_version_removed=removed
            )

        if chunks == 0:
            return IngestFileResult(filename=file.name, status="empty", old_version_removed=removed)
        return IngestFileResult(
            filename=file.name,
            status="replaced" if removed else "added",
            chunks=chunks,
        )

    def ingest_directory(
        self,
        directory: str | Path,
        *,
        recursive: bool = True,
        overwrite: bool = False,
        on_progress: ProgressCallback | None = None,
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
            results.append(self.ingest_safe(path, overwrite=overwrite))

        return results