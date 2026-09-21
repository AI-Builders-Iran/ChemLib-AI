"""SessionVectorStore: private, in-memory search that must behave like the library store."""

import math

import numpy as np
import pytest

from rag.schemas import ChunkResult
from src.retrieval.session_store import SessionVectorStore, relevance_score


class FakeEmbedder:
    """Bag-of-keywords vectors: texts sharing keywords are similar."""

    WORDS = ["isotope", "acid", "gas", "bond", "water"]

    def _vec(self, text: str) -> list[float]:
        vec = [float(text.lower().count(word)) for word in self.WORDS]
        return vec if any(vec) else [0.0] * len(self.WORDS)

    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def chunk(chunk_id: str, text: str, document_id: str = "d1", source: str = "a.txt", page=None) -> ChunkResult:
    return ChunkResult(
        text=text, source_file=source, page=page, chunk_id=chunk_id, document_id=document_id, score=0.0
    )


@pytest.fixture
def store():
    s = SessionVectorStore(FakeEmbedder())
    s.add([
        chunk("d1_c0", "isotope isotope neutron", "d1", "atoms.txt", page=3),
        chunk("d1_c1", "acid base acid", "d1", "atoms.txt", page=4),
        chunk("d2_c0", "gas gas pressure", "d2", "gases.txt"),
    ])
    return s


def test_relevance_score_matches_the_library_scale():
    assert relevance_score(1.0) == pytest.approx(1.0)
    assert relevance_score(0.0) == pytest.approx(1 - 2 / math.sqrt(2))
    assert relevance_score(0.46) == pytest.approx(0.2364, abs=1e-3)  # a typical relevant Persian hit


def test_query_returns_the_most_similar_chunk_first_with_metadata(store):
    hits = store.query("what is an isotope", k=3)

    assert hits[0].chunk_id == "d1_c0"
    assert (hits[0].source_file, hits[0].page) == ("atoms.txt", 3)
    assert hits[0].score > hits[1].score
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)  # identical direction


def test_query_can_be_limited_to_one_document(store):
    hits = store.query("gas", k=5, document_id="d1")

    assert {h.document_id for h in hits} == {"d1"}


def test_query_respects_k_and_handles_unknown_document(store):
    assert len(store.query("acid", k=1)) == 1
    assert store.query("acid", document_id="missing") == []


def test_empty_store_returns_nothing():
    assert SessionVectorStore(FakeEmbedder()).query("anything") == []


def test_same_chunk_id_replaces_the_old_chunk(store):
    store.add([chunk("d1_c0", "water water", "d1", "atoms.txt")])

    assert len(store) == 3
    assert store.query("water", k=1)[0].chunk_id == "d1_c0"


def test_listing_checking_and_deleting_documents(store):
    assert [(d.document_id, d.source_file, d.chunks) for d in store.list_documents()] == [
        ("d1", "atoms.txt", 2),
        ("d2", "gases.txt", 1),
    ]
    assert store.has_document("d1") and not store.has_document("nope")

    assert store.delete_document("d1") == 2
    assert not store.has_document("d1")
    assert store.query("gas", k=5)[0].document_id == "d2"
    assert store.delete_document("d1") == 0


def test_clear_forgets_everything(store):
    store.clear()

    assert len(store) == 0
    assert store.list_documents() == []
    assert store.query("acid") == []


def test_chunk_cap_protects_the_server(store):
    small = SessionVectorStore(FakeEmbedder(), max_chunks=2)
    small.add([chunk("a", "acid"), chunk("b", "gas")])

    with pytest.raises(ValueError, match="limited to 2"):
        small.add([chunk("c", "bond")])
    assert len(small) == 2


def test_nothing_is_written_to_disk(store, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store.add([chunk("x", "water")])

    assert list(tmp_path.iterdir()) == []
