"""In-memory vector store for documents that must never reach the shared database.

Used for a user's private, temporary documents: everything lives in this Python
object (held by one browser session) and is gone when the object is dropped.
Nothing is written to disk.

It offers the same methods as ``ChromaVectorStore`` (add / query / list /
has / delete), so ``IngestionPipeline`` and ``RAGService`` work with it unchanged.
"""

from __future__ import annotations

import math

import numpy as np

from rag.schemas import ChunkResult, IndexedDocument

# A private session is small by design; this protects the server's memory and CPU.
MAX_CHUNKS = 5000


def relevance_score(cosine: float) -> float:
    """Map cosine similarity to the score scale ChromaVectorStore reports.

    Chroma (L2 space) returns squared distance 2 - 2*cos for unit vectors, and
    LangChain turns it into ``1 - distance / sqrt(2)``. Using the same formula
    keeps ``SIMILARITY_THRESHOLD`` meaning the same thing for both stores.
    """
    return 1.0 - (2.0 - 2.0 * cosine) / math.sqrt(2.0)


def _unit(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.where(norms == 0, 1.0, norms)


class SessionVectorStore:
    """Exact (brute-force) cosine search over a few thousand chunks, in RAM."""

    def __init__(self, embedder, max_chunks: int = MAX_CHUNKS) -> None:
        self._embedder = embedder
        self._max_chunks = max_chunks
        self._chunks: list[ChunkResult] = []
        self._vectors: np.ndarray | None = None  # shape (n, dim), unit length

    def __len__(self) -> int:
        return len(self._chunks)

    def __bool__(self) -> bool:
        # An empty store is still a store: never let `store or default` replace it.
        return True

    def add(self, chunks: list[ChunkResult]) -> None:
        """Embed and keep a batch of chunks (same chunk id replaces the old one)."""
        if not chunks:
            return

        incoming_ids = {chunk.chunk_id for chunk in chunks}
        kept = [i for i, chunk in enumerate(self._chunks) if chunk.chunk_id not in incoming_ids]
        if len(kept) + len(chunks) > self._max_chunks:
            raise ValueError(
                f"Temporary documents are limited to {self._max_chunks} text chunks per session."
            )

        new_vectors = _unit(np.asarray(self._embedder.embed([c.text for c in chunks]), dtype=np.float32))

        if self._vectors is None or not kept:
            self._chunks, self._vectors = list(chunks), new_vectors
            return

        self._chunks = [self._chunks[i] for i in kept] + list(chunks)
        self._vectors = np.vstack([self._vectors[kept], new_vectors])

    def query(self, question: str, k: int = 5, document_id: str | None = None) -> list[ChunkResult]:
        """Top-k chunks most similar to the question, optionally within one document."""
        if not self._chunks or self._vectors is None:
            return []

        candidates = [
            i for i, chunk in enumerate(self._chunks) if document_id is None or chunk.document_id == document_id
        ]
        if not candidates:
            return []

        query_vector = _unit(np.asarray(self._embedder.embed_query(question), dtype=np.float32))
        similarities = self._vectors[candidates] @ query_vector
        best = np.argsort(-similarities)[:k]

        results: list[ChunkResult] = []
        for position in best:
            chunk = self._chunks[candidates[int(position)]]
            results.append(
                ChunkResult(
                    text=chunk.text,
                    source_file=chunk.source_file,
                    page=chunk.page,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    score=relevance_score(float(similarities[int(position)])),
                )
            )
        return results

    def list_documents(self) -> list[IndexedDocument]:
        found: dict[str, IndexedDocument] = {}
        for chunk in self._chunks:
            entry = found.get(chunk.document_id)
            if entry is None:
                entry = found[chunk.document_id] = IndexedDocument(
                    document_id=chunk.document_id, source_file=chunk.source_file, chunks=0
                )
            entry.chunks += 1
        return sorted(found.values(), key=lambda d: d.source_file.lower())

    def has_document(self, document_id: str) -> bool:
        return any(chunk.document_id == document_id for chunk in self._chunks)

    def delete_document(self, document_id: str) -> int:
        kept = [i for i, chunk in enumerate(self._chunks) if chunk.document_id != document_id]
        removed = len(self._chunks) - len(kept)
        if removed:
            self._chunks = [self._chunks[i] for i in kept]
            self._vectors = self._vectors[kept] if kept and self._vectors is not None else None
        return removed

    def clear(self) -> None:
        """Forget everything."""
        self._chunks = []
        self._vectors = None