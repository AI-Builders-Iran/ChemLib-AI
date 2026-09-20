from langchain_chroma import Chroma
from langchain_core.documents import Document

from rag.schemas import ChunkResult
from src.embedding.embedding import Embedder

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

VECTOR_DB_PATH = PROJECT_ROOT.parent / "vector_database" / "chroma_db"

class ChromaVectorStore:

    def __init__(
            self,
            persist_directory: str | Path = VECTOR_DB_PATH,
            collection_name: str = "chemistry_library",
            embedder: Embedder | None = None,
    ):
        self._embedder = embedder or Embedder()
        self._store = Chroma(
            collection_name=collection_name,
            embedding_function=self._embedder._embedding,
            persist_directory=persist_directory,
        )

    def add(self, chunks: list[ChunkResult]) -> None:
        """Embed and store a batch of chunks. LangChain Chroma embeds internally."""
        documents = [
            Document(
                page_content=chunk.text,
                metadata={
                    "source_file": chunk.source_file,
                    "page": chunk.page if chunk.page is not None else -1,
                    "document_id": chunk.chunk_id.split("_")[0],
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

        results = self._store.similarity_search_with_relevance_scores(
            query=question, k=k, filter=filter_dict,
        )

        return [
            ChunkResult(
                text=doc.page_content,
                source_file=doc.metadata["source_file"],
                page=doc.metadata["page"] if doc.metadata["page"] != -1 else None,
                chunk_id=doc.metadata.get("chunk_id", ""),
                score=score,
            )
            for doc, score in results
        ]


if __name__ == "__main__":
    store = ChromaVectorStore()

    chunks = [
        ChunkResult(
            text="آب در دمای صد درجه سانتی‌گراد می‌جوشد.",
            source_file="chem_intro.pdf",
            page=12,
            chunk_id="chemintro_c1",
            score=0.0,
        ),
        ChunkResult(
            text="فرمول شیمیایی گلوکز C6H12O6 است.",
            source_file="chem_intro.pdf",
            page=20,
            chunk_id="chemintro_c2",
            score=0.0,
        ),
    ]

    store.add(chunks)

    results = store.query("نقطه جوش آب چند درجه است؟", k=1)
    for r in results:
        print(r.text, "| score:", r.score, "| page:", r.page)
