"""Chat behaviour of RAGService, with a fake vector store and fake LLM providers."""

import pytest

from rag.prompts import (
    NO_ANSWER_MESSAGE_EN,
    NO_ANSWER_MESSAGE_FA,
    RAGPromptBuilder,
    _format_context,
)
from rag.rag_service import SIMILARITY_THRESHOLD, RAGService
from rag.schemas import ChunkResult, RAGAnswer


def chunk(chunk_id: str, page: int | None = 0, score: float = 0.9, source: str = "book.pdf") -> ChunkResult:
    return ChunkResult(
        text=f"text of {chunk_id}",
        source_file=source,
        page=page,
        chunk_id=chunk_id,
        document_id="doc1",
        score=score,
    )


class FakeStore:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def query(self, question, k=5, document_id=None):
        self.calls.append({"question": question, "k": k, "document_id": document_id})
        return self.chunks


class FakeProvider:
    def __init__(self, answer: RAGAnswer | None = None, error: Exception | None = None):
        self.answer = answer
        self.error = error
        self.prompts: list[str] = []

    def extract(self, prompt, schema):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.answer


def service(chunks, provider) -> tuple[RAGService, FakeStore]:
    store = FakeStore(chunks)
    return RAGService(vector_store=store, providers=provider if isinstance(provider, list) else [provider]), store


def test_no_chunks_returns_no_answer_in_question_language_without_calling_llm():
    provider = FakeProvider(RAGAnswer(answer="x", grounded=True))
    svc, _ = service([], provider)

    fa = svc.answer_question("پیوند کووالانسی چیست؟")
    en = svc.answer_question("What is a covalent bond?")

    assert (fa.answer, fa.grounded, fa.sources) == (NO_ANSWER_MESSAGE_FA, False, [])
    assert (en.answer, en.grounded, en.sources) == (NO_ANSWER_MESSAGE_EN, False, [])
    assert provider.prompts == []


def test_low_similarity_is_treated_as_not_grounded():
    provider = FakeProvider(RAGAnswer(answer="x", grounded=True))
    svc, _ = service([chunk("c1", score=SIMILARITY_THRESHOLD - 0.01)], provider)

    response = svc.answer_question("question")

    assert response.grounded is False
    assert provider.prompts == []


def test_grounded_answer_is_returned_with_only_the_cited_sources():
    chunks = [chunk("c1", page=3), chunk("c2", page=9), chunk("c3", page=15)]
    provider = FakeProvider(RAGAnswer(answer="The answer.", grounded=True, citations=["c2"]))
    svc, _ = service(chunks, provider)

    response = svc.answer_question("question")

    assert response.answer == "The answer."
    assert response.grounded is True
    assert [(s.chunk_id, s.page) for s in response.sources] == [("c2", 9)]


def test_all_retrieved_chunks_are_sources_when_the_model_cites_nothing_usable():
    chunks = [chunk("c1", page=3), chunk("c2", page=9)]
    provider = FakeProvider(RAGAnswer(answer="The answer.", grounded=True, citations=["unknown-id"]))
    svc, _ = service(chunks, provider)

    response = svc.answer_question("question")

    assert [s.chunk_id for s in response.sources] == ["c1", "c2"]


def test_model_can_declare_the_context_insufficient():
    provider = FakeProvider(RAGAnswer(answer="Not in the sources.", grounded=False, citations=["c1"]))
    svc, _ = service([chunk("c1")], provider)

    response = svc.answer_question("question")

    assert response.grounded is False
    assert response.answer == "Not in the sources."
    assert response.sources == []


def test_document_scope_is_passed_to_retrieval():
    provider = FakeProvider(RAGAnswer(answer="a", grounded=True))
    svc, store = service([chunk("c1")], provider)

    svc.answer_question("question", document_id="doc1")

    assert store.calls[0]["document_id"] == "doc1"


def test_second_provider_is_used_when_the_first_fails():
    failing = FakeProvider(error=RuntimeError("quota exceeded"))
    backup = FakeProvider(RAGAnswer(answer="From backup.", grounded=True, citations=["c1"]))
    svc, _ = service([chunk("c1")], [failing, backup])

    response = svc.answer_question("question")

    assert response.answer == "From backup."


def test_error_when_every_provider_fails():
    svc, _ = service([chunk("c1")], [FakeProvider(error=RuntimeError("a")), FakeProvider(error=RuntimeError("b"))])

    with pytest.raises(RuntimeError, match="All LLM providers failed"):
        svc.answer_question("question")


def test_context_block_exposes_chunk_id_source_and_one_based_page():
    context = _format_context([chunk("c1", page=0, source="a.pdf"), chunk("c2", page=None, source="b.txt")])

    assert "[chunk_id=c1; source=a.pdf; page=1]" in context
    assert "[chunk_id=c2; source=b.txt; page=n/a]" in context
    assert "text of c1" in context


def test_prompt_contains_question_and_context():
    prompt = RAGPromptBuilder().build("What is X?", [chunk("c1")])

    assert "What is X?" in prompt
    assert "chunk_id=c1" in prompt
