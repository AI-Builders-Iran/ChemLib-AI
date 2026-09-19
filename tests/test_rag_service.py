from unittest.mock import Mock

import pytest

from src.rag.llm_engine import LLMError
from src.rag.prompts import NO_ANSWER_MESSAGE
from src.rag.rag_service import RAGService
from src.rag.vector_store import ChunkResult, MockVectorStore, VectorStore


class RecordingVectorStore(VectorStore):
    def __init__(
        self,
        chunks_by_document: dict[str | None, list[ChunkResult]],
    ) -> None:
        self.chunks_by_document = chunks_by_document
        self.calls: list[tuple[str, int, str | None]] = []

    def query(
        self,
        question: str,
        k: int = 5,
        document_id: str | None = None,
    ) -> list[ChunkResult]:
        self.calls.append((question, k, document_id))

        if document_id is not None:
            return self.chunks_by_document.get(document_id, [])[:k]

        all_chunks: list[ChunkResult] = []

        for chunks in self.chunks_by_document.values():
            all_chunks.extend(chunks)

        return all_chunks[:k]


def chunk(
    text: str,
    document_id: str = "chem_book_a",
    title: str = "Materials Science Book A",
    page: int | None = 124,
    score: float | None = 0.82,
) -> ChunkResult:
    return ChunkResult(
        text=text,
        title=title,
        page=page,
        document_id=document_id,
        score=score,
    )


def test_successful_answer_returns_sources_and_grounded_true() -> None:
    store = RecordingVectorStore(
        {
            None: [
                chunk(
                    "خوردگی گالوانیکی بین دو فلز ناهمسان رخ می‌دهد."
                )
            ]
        }
    )

    llm = Mock()
    llm.generate.return_value = (
        "خوردگی گالوانیکی تماس دو فلز در الکترولیت است."
    )

    service = RAGService(
        vector_store=store,
        llm=llm,
    )

    result = service.answer_question(
        "خوردگی گالوانیکی چیست؟"
    )

    assert result.grounded is True
    assert "گالوانیکی" in result.answer

    assert len(result.sources) == 1
    assert result.sources[0].document_id == "chem_book_a"
    assert result.sources[0].page == 124
    assert result.sources[0].title == "Materials Science Book A"

    assert store.calls == [
        ("خوردگی گالوانیکی چیست؟", 5, None)
    ]

    llm.generate.assert_called_once()


def test_no_answer_when_nothing_is_retrieved() -> None:
    store = RecordingVectorStore(
        {
            None: []
        }
    )

    llm = Mock()

    service = RAGService(
        vector_store=store,
        llm=llm,
    )

    result = service.answer_question(
        "تاریخ انقلاب فرانسه چیست؟"
    )

    assert result.grounded is False
    assert result.answer == NO_ANSWER_MESSAGE
    assert result.sources == []

    llm.generate.assert_not_called()


def test_no_answer_when_similarity_is_below_threshold() -> None:
    store = RecordingVectorStore(
        {
            None: [
                chunk(
                    "متن نامرتبط",
                    score=0.12,
                )
            ]
        }
    )

    llm = Mock()

    service = RAGService(
        vector_store=store,
        llm=llm,
    )

    result = service.answer_question(
        "آنتروپی چیست؟"
    )

    assert result.grounded is False
    assert result.answer == NO_ANSWER_MESSAGE
    assert result.sources == []

    llm.generate.assert_not_called()


def test_chat_uses_top_k_five() -> None:
    store = RecordingVectorStore(
        {
            None: [
                chunk(
                    "متن مرتبط با خوردگی",
                    score=0.90,
                )
            ]
        }
    )

    llm = Mock()
    llm.generate.return_value = "پاسخ بر اساس منبع."

    service = RAGService(
        vector_store=store,
        llm=llm,
    )

    service.answer_question("خوردگی چیست؟")

    assert store.calls == [
        ("خوردگی چیست؟", 5, None)
    ]


def test_compare_queries_each_source_separately() -> None:
    store = RecordingVectorStore(
        {
            "chem_book_a": [
                chunk(
                    "تعریف خوردگی در کتاب A",
                    document_id="chem_book_a",
                    title="Materials Science Book A",
                    page=10,
                    score=0.86,
                )
            ],
            "chem_book_b": [
                chunk(
                    "تعریف خوردگی در کتاب B",
                    document_id="chem_book_b",
                    title="Materials Science Book B",
                    page=88,
                    score=0.84,
                )
            ],
        }
    )

    llm = Mock()
    llm.generate.return_value = """
### Materials Science Book A
تعریف: تخریب فلز در کتاب A
توضیح: جزئیات A

### Materials Science Book B
تعریف: تخریب فلز در کتاب B
توضیح: جزئیات B

### مقایسه
هر دو تخریب مواد را توصیف می‌کنند.
"""

    service = RAGService(
        vector_store=store,
        llm=llm,
    )

    result = service.compare_sources(
        "مفهوم خوردگی را مقایسه کن",
        source_a="chem_book_a",
        source_b="chem_book_b",
    )

    assert store.calls == [
        (
            "مفهوم خوردگی را مقایسه کن",
            4,
            "chem_book_a",
        ),
        (
            "مفهوم خوردگی را مقایسه کن",
            4,
            "chem_book_b",
        ),
    ]

    assert result.book_a.definition == (
        "تخریب فلز در کتاب A"
    )

    assert result.book_b.definition == (
        "تخریب فلز در کتاب B"
    )

    assert "تخریب مواد" in result.comparison

    assert result.book_a.sources[0].document_id == (
        "chem_book_a"
    )

    assert result.book_b.sources[0].document_id == (
        "chem_book_b"
    )

    assert result.book_a.sources[0].page == 10
    assert result.book_b.sources[0].page == 88


def test_compare_uses_four_chunks_per_source() -> None:
    store = RecordingVectorStore(
        {
            "chem_book_a": [
                chunk(
                    f"متن مرتبط {i}",
                    document_id="chem_book_a",
                    page=i,
                    score=0.80,
                )
                for i in range(1, 7)
            ],
            "chem_book_b": [
                chunk(
                    f"متن مرتبط B {i}",
                    document_id="chem_book_b",
                    page=i,
                    score=0.80,
                )
                for i in range(1, 7)
            ],
        }
    )

    llm = Mock()
    llm.generate.return_value = """
### Materials Science Book A
تعریف: تعریف A
توضیح: توضیح A

### Materials Science Book B
تعریف: تعریف B
توضیح: توضیح B

### مقایسه
مقایسه A و B
"""

    service = RAGService(
        vector_store=store,
        llm=llm,
    )

    service.compare_sources(
        "خوردگی را مقایسه کن",
        source_a="chem_book_a",
        source_b="chem_book_b",
    )

    assert store.calls == [
        ("خوردگی را مقایسه کن", 4, "chem_book_a"),
        ("خوردگی را مقایسه کن", 4, "chem_book_b"),
    ]


def test_llm_errors_propagate() -> None:
    store = RecordingVectorStore(
        {
            None: [
                chunk("متن مرتبط")
            ]
        }
    )

    llm = Mock()
    llm.generate.side_effect = LLMError("boom")

    service = RAGService(
        vector_store=store,
        llm=llm,
    )

    with pytest.raises(LLMError):
        service.answer_question("خوردگی چیست؟")


def test_mock_vector_store_filters_by_document_id() -> None:
    store = MockVectorStore.demo()

    results = store.query(
        "خوردگی گالوانیکی",
        k=5,
        document_id="chem_book_b",
    )

    assert results
    assert all(
        item.document_id == "chem_book_b"
        for item in results
    )