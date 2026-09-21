"""RAG chat and compare operations, backed by structured-output LLM providers."""

import logging
from typing import Type, TypeVar

from pydantic import BaseModel

from rag.prompts import ComparePromptBuilder, RAGPromptBuilder, no_answer_message
from rag.schemas import (
    ChatResponse,
    ChunkResult,
    CompareAnswer,
    CompareBookSection,
    CompareResponse,
    RAGAnswer,
    SourceItem,
)
from src.extraction.providers.base import LLMProvider
from src.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

CHAT_TOP_K = 5
COMPARE_TOP_K = 4
# Chroma similarity_search_with_relevance_scores returns a 0..1 relevance
# score. Below this threshold we treat retrieval as "nothing relevant found"
# and skip the LLM call entirely (cheaper and avoids hallucinated answers).
SIMILARITY_THRESHOLD = 0.2

T = TypeVar("T", bound=BaseModel)


def provider_label(provider) -> str:
    """Short display name: GeminiProvider -> "Gemini"."""
    return provider.__class__.__name__.removesuffix("Provider")


class AllProvidersFailedError(RuntimeError):
    """Every configured LLM provider raised. ``failed`` lists their display names."""

    def __init__(self, errors: list[str], failed: list[str]) -> None:
        super().__init__("All LLM providers failed. " + " | ".join(errors))
        self.failed = failed


class RAGService:
    """
    Retrieval-augmented chat and compare.

    Providers are tried in order (same fallback pattern as
    src.extraction.extractor.DocumentExtractor): the first provider is
    primary, later ones are used only if an earlier one raises.
    """

    def __init__(self, vector_store: ChromaVectorStore, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("At least one LLM provider is required.")

        self._vector_store = vector_store
        self._providers = providers
        self._prompt_builder = RAGPromptBuilder()
        self._compare_prompt_builder = ComparePromptBuilder()

    def answer_question(self, question: str, document_id: str | None = None) -> ChatResponse:
        chunks = self._vector_store.query(question, k=CHAT_TOP_K, document_id=document_id)

        if not self._is_grounded(chunks):
            return ChatResponse(answer=no_answer_message(question), grounded=False, sources=[])

        prompt = self._prompt_builder.build(question, chunks)
        result, fallback = self._extract_with_fallback(prompt, RAGAnswer)

        # The model itself may decide the retrieved context is insufficient.
        if not result.grounded:
            return ChatResponse(
                answer=result.answer.strip() or no_answer_message(question),
                grounded=False,
                sources=[],
                **fallback,
            )

        # Show only the chunks the model says it used; fall back to every
        # retrieved chunk if it cited none (or cited ids we did not send).
        cited_ids = set(result.citations)
        cited_chunks = [c for c in chunks if c.chunk_id in cited_ids]
        sources = self._sources_from_chunks(cited_chunks or chunks)

        return ChatResponse(answer=result.answer, grounded=True, sources=sources, **fallback)

    def compare_sources(self, question: str, source_a: str, source_b: str) -> CompareResponse:
        """
        source_a / source_b are document_id values, as returned by ingestion.
        """
        chunks_a = self._vector_store.query(question, k=COMPARE_TOP_K, document_id=source_a)
        chunks_b = self._vector_store.query(question, k=COMPARE_TOP_K, document_id=source_b)

        prompt = self._compare_prompt_builder.build(
            question, source_a, chunks_a, source_b, chunks_b
        )
        result: CompareAnswer = self._extract(prompt, CompareAnswer)

        return CompareResponse(
            book_a=CompareBookSection(
                title=source_a,
                definition=result.definition_a,
                explanation=result.explanation_a,
                sources=self._sources_from_chunks(chunks_a),
            ),
            book_b=CompareBookSection(
                title=source_b,
                definition=result.definition_b,
                explanation=result.explanation_b,
                sources=self._sources_from_chunks(chunks_b),
            ),
            comparison=result.comparison,
        )

    def _extract(self, prompt: str, schema: Type[T]) -> T:
        return self._extract_with_fallback(prompt, schema)[0]

    def _extract_with_fallback(self, prompt: str, schema: Type[T]) -> tuple[T, dict]:
        """Try providers in order; also report which backup answered, if any.

        The second value is a dict of ``ChatResponse`` fields (empty when the
        primary provider answered), so callers can splat it into the response.
        """
        errors: list[str] = []
        failed: list[str] = []
        for provider in self._providers:
            try:
                result = provider.extract(prompt=prompt, schema=schema)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider.__class__.__name__}: {exc}")
                failed.append(provider_label(provider))
                logger.warning("RAG provider failed: %s", errors[-1])
                continue

            if not failed:
                return result, {}
            return result, {
                "fallback_provider": provider_label(provider),
                "fallback_model": getattr(provider, "model_name", None),
                "failed_providers": failed,
            }

        raise AllProvidersFailedError(errors, failed)

    @staticmethod
    def _is_grounded(chunks: list[ChunkResult]) -> bool:
        if not chunks:
            return False
        print("MAX SCORE:", max(c.score for c in chunks))
        return max((c.score for c in chunks), default=0.0) >= SIMILARITY_THRESHOLD

    @staticmethod
    def _sources_from_chunks(chunks: list[ChunkResult]) -> list[SourceItem]:
        seen: set[tuple[str, int | None, str]] = set()
        unique: list[SourceItem] = []

        for c in chunks:
            key = (c.source_file, c.page, c.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            unique.append(SourceItem(source_file=c.source_file, page=c.page, chunk_id=c.chunk_id))

        return unique