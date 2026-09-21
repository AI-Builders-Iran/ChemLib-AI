"""Library-management methods of ChromaVectorStore, against an in-memory fake of Chroma."""

import pytest

from src.retrieval import vector_store as vs


class FakeChroma:
    """Just enough of langchain_chroma.Chroma: get / delete over id + metadata rows."""

    def __init__(self, **kwargs):
        self.rows: dict[str, dict] = {}
        self.delete_calls: list[list[str]] = []
        self.queries: list[str] = []

    def add(self, chunk_id: str, document_id: str, source_file: str) -> None:
        self.rows[chunk_id] = {"document_id": document_id, "source_file": source_file}

    def get(self, ids=None, where=None, limit=None, offset=None, include=None):
        items = list(self.rows.items())
        if where:
            items = [(i, m) for i, m in items if all(m.get(k) == v for k, v in where.items())]
        items = items[offset or 0:]
        if limit is not None:
            items = items[:limit]
        return {"ids": [i for i, _ in items], "metadatas": [m for _, m in items]}

    def similarity_search_with_relevance_scores(self, query, k=5, filter=None):
        self.queries.append(query)
        return []

    def delete(self, ids=None, **kwargs):
        self.delete_calls.append(list(ids))
        for chunk_id in ids:
            self.rows.pop(chunk_id, None)


class FakeEmbedder:
    langchain_embeddings = object()


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(vs, "Chroma", FakeChroma)
    instance = vs.ChromaVectorStore(persist_directory="unused", embedder=FakeEmbedder())
    fake = instance._store
    fake.add("b_c0", "b", "Beta.pdf")
    fake.add("a_c0", "a", "alpha.pdf")
    fake.add("a_c1", "a", "alpha.pdf")
    fake.add("a_c2", "a", "alpha.pdf")
    return instance


def test_list_documents_counts_chunks_and_sorts_by_file_name(store):
    documents = store.list_documents()

    assert [(d.document_id, d.source_file, d.chunks) for d in documents] == [
        ("a", "alpha.pdf", 3),
        ("b", "Beta.pdf", 1),
    ]


def test_list_documents_walks_every_page(store, monkeypatch):
    monkeypatch.setattr(vs, "_PAGE_SIZE", 2)

    assert sum(d.chunks for d in store.list_documents()) == 4


def test_list_documents_of_an_empty_library(monkeypatch):
    monkeypatch.setattr(vs, "Chroma", FakeChroma)
    empty = vs.ChromaVectorStore(persist_directory="unused", embedder=FakeEmbedder())

    assert empty.list_documents() == []


def test_has_document(store):
    assert store.has_document("a") is True
    assert store.has_document("missing") is False


def test_delete_document_removes_only_that_document(store):
    removed = store.delete_document("a")

    assert removed == 3
    assert store.has_document("a") is False
    assert store.has_document("b") is True


def test_delete_document_works_in_batches(store, monkeypatch):
    monkeypatch.setattr(vs, "_DELETE_BATCH", 2)

    store.delete_document("a")

    assert [len(call) for call in store._store.delete_calls] == [2, 1]


def test_delete_unknown_document_is_a_no_op(store):
    assert store.delete_document("missing") == 0
    assert store._store.delete_calls == []


def test_query_is_normalised_like_the_indexed_documents(store):
    store.query("اسيد و كربن ؟ ٢")

    assert store._store.queries == ["اسید و کربن؟ 2"]
