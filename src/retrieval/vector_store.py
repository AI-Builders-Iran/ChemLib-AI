from langchain_chroma import Chroma
from langchain_core.documents import Document

from rag.schemas import ChunkResult, IndexedDocument
from src.embedding.embedding import Embedder
from src.processing.cleaners.persian import normalize_query

_PAGE_SIZE = 5000    # metadata rows fetched per round-trip when listing documents
_DELETE_BATCH = 500  # ids removed per delete call


class ChromaVectorStore:
    """Chroma-backed semantic store. Embedding happens internally via LangChain."""

    def __init__(
        self,
        persist_directory: str = "vector_database/chroma_db",
        collection_name: str = "chemistry_library",
        embedder: Embedder | None = None,
    ):
        self._embedder = embedder or Embedder()
        self._store = Chroma(
            collection_name=collection_name,
            embedding_function=self._embedder.langchain_embeddings,
            persist_directory=persist_directory,
        )

    def add(self, chunks: list[ChunkResult]) -> None:
        """Embed and store a batch of chunks."""
        documents = [
            Document(
                page_content=chunk.text,
                metadata={
                    "source_file": chunk.source_file,
                    "page": chunk.page if chunk.page is not None else -1,
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                },
            )
            for chunk in chunks
        ]
        ids = [chunk.chunk_id for chunk in chunks]
        self._store.add_documents(documents=documents, ids=ids)

    def query(self, question: str, k: int = 5, document_id: str | None = None) -> list[ChunkResult]:
        """Embed the question and return the top-k most similar chunks."""
        filter_dict = {"document_id": document_id} if document_id else None

        # Search with the same spelling/digits the documents were indexed with.
        results = self._store.similarity_search_with_relevance_scores(
            query=normalize_query(question), k=k, filter=filter_dict,
        )

        return [
            ChunkResult(
                text=doc.page_content,
                source_file=doc.metadata["source_file"],
                page=doc.metadata["page"] if doc.metadata["page"] != -1 else None,
                chunk_id=doc.metadata.get("chunk_id", ""),
                document_id=doc.metadata.get("document_id", ""),
                score=score,
            )
            for doc, score in results
        ]

    # ------------------------------------------------------------------
    # Library management (used by the admin panel)
    # ------------------------------------------------------------------

    def list_documents(self) -> list[IndexedDocument]:
        """Return one entry per indexed document, sorted by file name."""
        found: dict[str, IndexedDocument] = {}
        offset = 0

        while True:
            batch = self._store.get(include=["metadatas"], limit=_PAGE_SIZE, offset=offset)
            metadatas = batch.get("metadatas") or []
            if not metadatas:
                break

            for metadata in metadatas:
                document_id = (metadata or {}).get("document_id", "")
                if not document_id:
                    continue
                entry = found.get(document_id)
                if entry is None:
                    entry = IndexedDocument(
                        document_id=document_id,
                        source_file=metadata.get("source_file", document_id),
                        chunks=0,
                    )
                    found[document_id] = entry
                entry.chunks += 1

            offset += len(metadatas)
            if len(metadatas) < _PAGE_SIZE:
                break

        return sorted(found.values(), key=lambda d: d.source_file.lower())

    def has_document(self, document_id: str) -> bool:
        """True if at least one chunk of ``document_id`` is stored."""
        batch = self._store.get(
            where={"document_id": document_id}, limit=1, include=["metadatas"],
        )
        return bool(batch.get("ids"))

    def delete_document(self, document_id: str) -> int:
        """Remove every chunk of ``document_id``. Returns how many were deleted."""
        batch = self._store.get(where={"document_id": document_id}, include=["metadatas"])
        ids: list[str] = list(batch.get("ids") or [])

        for start in range(0, len(ids), _DELETE_BATCH):
            self._store.delete(ids=ids[start:start + _DELETE_BATCH])

        return len(ids)
