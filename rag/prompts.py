import re
from textwrap import dedent

from rag.schemas import ChunkResult

_PERSIAN_CHAR_PATTERN = re.compile(r"[\u0600-\u06FF]")

NO_ANSWER_MESSAGE_FA = (
    "اطلاعات کافی برای پاسخ به این سؤال در منابع موجود کتابخانه پیدا نشد."
)
NO_ANSWER_MESSAGE_EN = (
    "There isn't enough information in the available library sources to "
    "answer this question."
)


def no_answer_message(question: str) -> str:
    """Return the no-answer message in the same language as the question.

    Used only on the "not grounded" path, which returns before ever calling
    the LLM (so the LLM never gets a chance to match the question's language
    itself). Detection is a simple heuristic: any Persian/Arabic-script
    character in the question means Persian; otherwise English.
    """
    if _PERSIAN_CHAR_PATTERN.search(question):
        return NO_ANSWER_MESSAGE_FA
    return NO_ANSWER_MESSAGE_EN


def _format_context(chunks: list[ChunkResult]) -> str:
    """Render retrieved chunks as the labelled context block used in prompts.

    Every block carries its ``chunk_id`` so the model can cite exactly the
    chunks it used (the ``citations`` field of ``RAGAnswer``). PDF page
    metadata is stored 0-based by the loader, so it is shown 1-based here to
    match what a reader sees in a PDF viewer.
    """
    blocks: list[str] = []
    for chunk in chunks:
        page = str(chunk.page + 1) if chunk.page is not None else "n/a"
        header = f"[chunk_id={chunk.chunk_id}; source={chunk.source_file}; page={page}]"
        blocks.append(f"{header}\n{chunk.text}")
    return "\n\n".join(blocks)


class RAGPromptBuilder:
    """Builds the prompt for a single grounded question-answer turn."""

    def build(self, question: str, chunks: list[ChunkResult]) -> str:
        context = _format_context(chunks)
        return dedent(f"""
            You are a scientific assistant for a chemistry faculty library.
            Answer ONLY using the context below. Do not use outside knowledge.
            If the context is insufficient to answer, set grounded=false and,
            in the answer field, say so briefly in the same language as the
            question (Persian or English).
            Always list the chunk_ids you actually used in the citations field.
            Answer in the same language the question was asked in.

            Question: {question}

            Context:
            {context}
        """).strip()


class ComparePromptBuilder:
    """Builds the prompt for comparing a concept across two sources."""

    def build(
            self,
            question: str,
            title_a: str,
            chunks_a: list[ChunkResult],
            title_b: str,
            chunks_b: list[ChunkResult],
    ) -> str:
        context_a = _format_context(chunks_a) or "(no relevant content found)"
        context_b = _format_context(chunks_b) or "(no relevant content found)"

        return dedent(f"""
            You are a scientific assistant comparing two sources for a
            chemistry faculty library. Keep the context of each source
            strictly separate — never mix content between them.
            If either source's context is insufficient, say so explicitly
            for that source only; never invent information.
            Answer in the same language the question was asked in
            (Persian or English).

            Source A ({title_a}):
            {context_a}

            Source B ({title_b}):
            {context_b}

            Question: {question}

            Provide a short definition and explanation for each source
            individually (definition_a/explanation_a, definition_b/explanation_b),
            plus a final comparison section. Set grounded=false only if BOTH
            sources lack sufficient information.
        """).strip()
