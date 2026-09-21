from langchain_huggingface import HuggingFaceEmbeddings


class Embedder:
    """Local, free embedding model (BGE-M3) via LangChain's HuggingFaceEmbeddings."""

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._embedding = HuggingFaceEmbeddings(
            model_name=model_name,
            encode_kwargs={"normalize_embeddings": True},
        )

    @property
    def langchain_embeddings(self) -> HuggingFaceEmbeddings:
        """Expose the underlying LangChain Embeddings object for VectorStore."""
        return self._embedding

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks."""
        return self._embedding.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        return self._embedding.embed_query(text)
