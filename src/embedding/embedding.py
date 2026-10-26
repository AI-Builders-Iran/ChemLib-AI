"""Local, free embedding model (BGE-M3) via LangChain's HuggingFaceEmbeddings.

Loading this model is the expensive part of the whole RAG stack — it means
downloading-or-reading-from-cache and placing in memory a ~2GB multilingual
transformer, which can take anywhere from several seconds to over a minute.
That must never happen just because something held a reference to an
``Embedder`` (e.g. a ``ChromaVectorStore`` built to list documents, or a
``RAGService`` built but not yet queried) — only an actual embed call
(indexing a document, or running a similarity search for a real question)
may trigger it. ``Embedder`` is itself cheap to construct; the model is
loaded lazily, thread-safely, on first real use, and reused after that.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


def _select_device() -> str:
    """"cuda" if a working, CUDA-enabled torch is available, else "cpu".

    Never raises: any import or detection failure quietly falls back to CPU,
    which is always a safe, supported choice for this project.
    """
    override = os.getenv("EMBEDDING_DEVICE")
    if override:
        return override
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:  # noqa: BLE001 - torch missing/broken CUDA driver, etc.
        pass
    return "cpu"


class Embedder:
    """Local, free embedding model (BGE-M3) via LangChain's HuggingFaceEmbeddings.

    Construction is cheap (just records the model name) — the actual model
    is loaded on first call to :meth:`embed`, :meth:`embed_query`, or a
    first real call through :attr:`langchain_embeddings`'s lazy proxy.
    """

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._model_name = model_name
        self._embedding: Embeddings | None = None
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> Embeddings:
        if self._embedding is None:
            with self._lock:
                if self._embedding is None:
                    from langchain_huggingface import HuggingFaceEmbeddings

                    device = _select_device()
                    logger.info(
                        "[RAG] Initializing embedding model (%s, device=%s)…", self._model_name, device
                    )
                    t0 = time.monotonic()
                    self._embedding = HuggingFaceEmbeddings(
                        model_name=self._model_name,
                        encode_kwargs={"normalize_embeddings": True},
                        model_kwargs={"device": device},
                    )
                    logger.info("[RAG] Embedding model ready in %.1fs.", time.monotonic() - t0)
        return self._embedding

    @property
    def langchain_embeddings(self) -> Embeddings:
        """A LangChain ``Embeddings``-compatible object for ``VectorStore``.

        Returns a lightweight proxy immediately — holding or passing this
        around (e.g. into a ``Chroma`` collection just to list documents)
        never loads the model. The model loads on the proxy's first actual
        ``embed_query``/``embed_documents`` call.
        """
        return _LazyEmbeddingsProxy(self)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks."""
        return self._ensure_loaded().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        return self._ensure_loaded().embed_query(text)


class _LazyEmbeddingsProxy(Embeddings):
    """Satisfies LangChain's ``Embeddings`` interface without eagerly loading
    anything; every call is forwarded to the owning ``Embedder``, which loads
    the real model on first use and reuses it after that."""

    def __init__(self, owner: Embedder):
        self._owner = owner

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._owner.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._owner.embed_query(text)
