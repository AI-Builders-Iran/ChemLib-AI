"""RAG chat and compare operations. LLM and VectorStore are injected."""

from __future__ import annotations

from dataclasses import dataclass

from src.rag.llm_engine import LLMGenerator
from src.rag.prompts import (
    COMPARE_SYSTEM_PROMPT,
    NO_ANSWER_MESSAGE,
    RAG_SYSTEM_PROMPT,
)
from src.rag.vector_store import ChunkResult, VectorStore
from src.schemas.api_schemas import (
    ChatResponse,
    CompareBookSection,
    CompareResponse,
    SourceItem,
)


CHAT_TOP_K = 5
COMPARE_TOP_K = 4
SIMILARITY_THRESHOLD = 0.35


class SourceNotFoundError(LookupError):
    """A requested library source could not be resolved."""


@dataclass(frozen=True)
class ResolvedSource:
    document_id: str
    title: str


class RAGService:
    def __init__(self, vector_store: VectorStore, llm: LLMGenerator) -> None:
        self._vector_store = vector_store
        self._llm = llm

    def answer_question(self, question: str) -> ChatResponse:
        chunks = self._vector_store.query(
            question,
            k=CHAT_TOP_K,
            document_id=None,
        )

        if not self._is_grounded(chunks):
            return ChatResponse(
                answer=NO_ANSWER_MESSAGE,
                sources=[],
                grounded=False,
            )

        prompt = _fill_template(
            RAG_SYSTEM_PROMPT,
            context=_format_context(chunks),
            question=question.strip(),
        )

        answer = self._llm.generate(prompt)

        return ChatResponse(
            answer=answer,
            sources=_sources_from_chunks(chunks),
            grounded=True,
        )

    def compare_sources(
        self,
        question: str,
        source_a: str,
        source_b: str,
    ) -> CompareResponse:
        """
        Retrieve each source independently and compare their contexts.

        source_a/source_b are resolved document identifiers supplied by
        the API/service layer. VectorStore only receives document_id.
        """
        if not source_a.strip():
            raise SourceNotFoundError("source_a is required.")

        if not source_b.strip():
            raise SourceNotFoundError("source_b is required.")

        chunks_a = self._vector_store.query(
            question,
            k=COMPARE_TOP_K,
            document_id=source_a.strip(),
        )

        chunks_b = self._vector_store.query(
            question,
            k=COMPARE_TOP_K,
            document_id=source_b.strip(),
        )

        title_a = _title_from_chunks(chunks_a, source_a.strip())
        title_b = _title_from_chunks(chunks_b, source_b.strip())

        context_a = _format_context(chunks_a) or NO_ANSWER_MESSAGE
        context_b = _format_context(chunks_b) or NO_ANSWER_MESSAGE

        prompt = _fill_template(
            COMPARE_SYSTEM_PROMPT,
            title_a=title_a,
            context_a=context_a,
            title_b=title_b,
            context_b=context_b,
            question=question.strip(),
        )

        raw = self._llm.generate(prompt)

        parsed = _parse_compare_output(
            raw,
            title_a=title_a,
            title_b=title_b,
        )

        return CompareResponse(
            book_a=CompareBookSection(
                title=title_a,
                definition=parsed["definition_a"],
                explanation=parsed["explanation_a"],
                sources=_sources_from_chunks(chunks_a),
            ),
            book_b=CompareBookSection(
                title=title_b,
                definition=parsed["definition_b"],
                explanation=parsed["explanation_b"],
                sources=_sources_from_chunks(chunks_b),
            ),
            comparison=parsed["comparison"],
        )

    @staticmethod
    def _is_grounded(chunks: list[ChunkResult]) -> bool:
        if not chunks:
            return False

        scored = [
            chunk.score
            for chunk in chunks
            if chunk.score is not None
        ]

        if not scored:
            return True

        return max(scored) >= SIMILARITY_THRESHOLD


def _title_from_chunks(
    chunks: list[ChunkResult],
    fallback_document_id: str,
) -> str:
    """Get the source title from retrieved metadata."""
    for chunk in chunks:
        if chunk.title:
            return chunk.title

    return fallback_document_id


def _format_context(chunks: list[ChunkResult]) -> str:
    blocks: list[str] = []

    for chunk in chunks:
        page = (
            str(chunk.page)
            if chunk.page is not None
            else "unknown"
        )

        header = (
            f"[title={chunk.title}; "
            f"page={page}; "
            f"document_id={chunk.document_id}]"
        )

        blocks.append(
            f"{header}\n{chunk.text}"
        )

    return "\n\n".join(blocks)


def _sources_from_chunks(
    chunks: list[ChunkResult],
) -> list[SourceItem]:
    unique: list[SourceItem] = []
    seen: set[tuple[str, int | None, str]] = set()

    for chunk in chunks:
        key = (
            chunk.document_id,
            chunk.page,
            chunk.title,
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(
            SourceItem(
                title=chunk.title,
                page=chunk.page,
                document_id=chunk.document_id,
            )
        )

    return unique


def _fill_template(
    template: str,
    **values: str,
) -> str:
    filled = template

    for key, value in values.items():
        filled = filled.replace(
            "{" + key + "}",
            value,
        )

    return filled


def _parse_compare_output(
    raw: str,
    title_a: str,
    title_b: str,
) -> dict[str, str]:
    """Best-effort parse of the mandated markdown compare structure."""
    sections = _split_markdown_sections(raw)

    block_a = (
        _section_body(sections, title_a)
        or _nth_section(sections, 0)
    )

    block_b = (
        _section_body(sections, title_b)
        or _nth_section(sections, 1)
    )

    comparison = (
        _section_body(sections, "مقایسه")
        or _section_body(sections, "comparison")
        or _nth_section(sections, 2)
        or raw.strip()
    )

    def_a, exp_a = _definition_explanation(block_a)
    def_b, exp_b = _definition_explanation(block_b)

    return {
        "definition_a": def_a,
        "explanation_a": exp_a,
        "definition_b": def_b,
        "explanation_b": exp_b,
        "comparison": comparison.strip(),
    }


def _split_markdown_sections(
    raw: str,
) -> list[tuple[str, str]]:
    import re

    parts = re.split(
        r"(?m)^###\s+",
        raw.strip(),
    )

    sections: list[tuple[str, str]] = []

    for part in parts:
        part = part.strip()

        if not part:
            continue

        heading, _, body = part.partition("\n")

        sections.append(
            (
                heading.strip(),
                body.strip(),
            )
        )

    return sections


def _section_body(
    sections: list[tuple[str, str]],
    heading: str,
) -> str:
    heading_lower = heading.lower()

    for title, body in sections:
        if (
            title.lower() == heading_lower
            or heading_lower in title.lower()
        ):
            return body

    return ""


def _nth_section(
    sections: list[tuple[str, str]],
    index: int,
) -> str:
    if 0 <= index < len(sections):
        return sections[index][1]

    return ""


def _definition_explanation(
    block: str,
) -> tuple[str, str]:
    import re

    if not block:
        return "", ""

    definition = ""
    explanation = ""

    definition_match = re.search(
        r"تعریف\s*:\s*(.*?)(?=توضیح\s*:|$)",
        block,
        flags=re.DOTALL,
    )

    explanation_match = re.search(
        r"توضیح\s*:\s*(.*)",
        block,
        flags=re.DOTALL,
    )

    if definition_match:
        definition = definition_match.group(1).strip()

    if explanation_match:
        explanation = explanation_match.group(1).strip()

    if not definition and not explanation:
        explanation = block.strip()

    return definition, explanation