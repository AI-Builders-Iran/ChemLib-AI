from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from src.retrieval.vector_store import ChromaVectorStore


@patch("src.retrieval.vector_store.Chroma")
@patch("src.retrieval.vector_store.Embedder")
def test_query_maps_chroma_results_to_chunk_results(mock_embedder_cls, mock_chroma_cls):
    mock_chroma = mock_chroma_cls.return_value
    mock_chroma.similarity_search_with_relevance_scores.return_value = [
        (
            Document(
                page_content="نمونه متن",
                metadata={
                    "source_file": "a.pdf",
                    "page": 1,
                    "document_id": "docA",
                    "chunk_id": "docA_c1",
                },
            ),
            0.82,
        )
    ]

    store = ChromaVectorStore()
    results = store.query("سؤال نمونه", k=1)

    assert len(results) == 1
    assert results[0].text == "نمونه متن"
    assert results[0].chunk_id == "docA_c1"
    assert results[0].document_id == "docA"
    assert results[0].score == 0.82


@patch("src.retrieval.vector_store.Chroma")
@patch("src.retrieval.vector_store.Embedder")
def test_add_passes_metadata_and_ids(mock_embedder_cls, mock_chroma_cls):
    from rag.schemas import ChunkResult

    mock_chroma = mock_chroma_cls.return_value

    store = ChromaVectorStore()
    store.add([
        ChunkResult(
            text="متن",
            source_file="a.pdf",
            page=3,
            chunk_id="docA_c0",
            document_id="docA",
        )
    ])

    mock_chroma.add_documents.assert_called_once()
    _, kwargs = mock_chroma.add_documents.call_args
    assert kwargs["ids"] == ["docA_c0"]
    assert kwargs["documents"][0].metadata["document_id"] == "docA"
    assert kwargs["documents"][0].metadata["chunk_id"] == "docA_c0"
