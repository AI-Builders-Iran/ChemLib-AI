from langchain_huggingface import HuggingFaceEmbeddings


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._embedding = HuggingFaceEmbeddings(
            model_name=model_name,
            encode_kwargs={"normalize_embeddings": True},
        )

    def embed(self, texts: list[str]) -> list[list[[float]]]:
        """Embed a batch of document chunks. Returns one vector per text."""
        return self._embedding.embed_documents(texts)

    def embed_query(self, texts: list[str]) -> list[float]:
        """Embed a single search query."""
        return self._embedding.embed_query(texts)



