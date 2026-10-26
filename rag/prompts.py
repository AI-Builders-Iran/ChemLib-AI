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
    match what a reader sees in a PDF viewer. ``type`` tells the model when a
    chunk is a table (Markdown) or formula (LaTeX) rather than prose, so it
    reads/quotes it correctly instead of treating it as a paragraph.
    """
    blocks: list[str] = []
    for chunk in chunks:
        page = str(chunk.page + 1) if chunk.page is not None else "n/a"
        header = (
            f"[chunk_id={chunk.chunk_id}; type={chunk.block_type}; "
            f"source={chunk.source_file}; page={page}]"
        )
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


# ---------------------------------------------------------------------------
# Document summarization
# ---------------------------------------------------------------------------

_LATIN_LETTER = re.compile(r"[A-Za-z]")
_ARABIC_SCRIPT_LETTER = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def detect_language(text: str) -> str:
    """"fa" when the text is mostly Persian/Arabic-script letters, otherwise "en".

    A ratio, not "any Persian character" (as ``no_answer_message`` uses for short
    questions): an English paper with one Persian word, or a Persian chemistry text full of
    formulas and Latin terms, must each be classified by what most of the text is.
    """
    arabic = len(_ARABIC_SCRIPT_LETTER.findall(text))
    latin = len(_LATIN_LETTER.findall(text))
    if arabic + latin == 0:
        return "en"
    return "fa" if arabic / (arabic + latin) >= 0.4 else "en"


_LANGUAGE_NAME = {"fa": "Persian (فارسی)", "en": "English"}

# Templates are dedented once and filled with ``str.format`` afterwards, so a document's own
# line breaks never disturb the indentation of the instructions (``dedent`` after
# interpolation, as the chat prompts do, stops working as soon as inserted text has a
# line starting at column 0). ``str.format`` does not re-parse the inserted values, so braces
# in the document text are safe.
_RULES = """
Rules:
- Use ONLY the text provided. Do not add outside knowledge, examples, numbers, names,
  dates or conclusions that are not in the text.
- Copy chemical formulas, units, numerical values and technical terms exactly as written.
- The text may come from OCR and contain noise or broken lines; ignore the noise and
  never guess what a garbled passage meant.
- Markers like [page 12] only show where text came from; do not copy them.
- Write in {language}.
"""

_SINGLE_PASS = """
You are a scientific assistant for a chemistry faculty library.
Summarize the document below (file name: {source_file}).

Produce:
- title: the document's own title if the text states one, otherwise a short descriptive title
- overview: a coherent summary of 1-3 paragraphs covering the main subject, the main
  content and the conclusions
- key_points: 5-10 short, self-contained points (findings, methods, results, conclusions)
- key_terms: up to 12 important terms or concepts, each as "term: short explanation
  taken from the text"
""" + _RULES + """
Document text:
{text}
"""

_MAP_SECTION = """
You are a scientific assistant for a chemistry faculty library.
The text below is section {index} of {total} of a longer document (file name: {source_file}).
Summarize ONLY this section; other sections are summarized separately.

Produce:
- summary: a dense, factual paragraph of what this section says
- key_points: up to 8 short points (findings, methods, results, definitions)
- key_terms: up to 8 important terms, each as "term: short explanation taken from the text"
If the section has no substantive content (blank, only page furniture, unreadable OCR),
return an empty summary and empty lists.
""" + _RULES + """
Section text:
{text}
"""

_MERGE_PARTIALS = """
You are a scientific assistant for a chemistry faculty library.
Below are summaries of consecutive parts of one long document (file name: {source_file}).
Merge them into ONE summary of that stretch of the document, in order, without repeating
yourself.

Produce summary (a dense paragraph), key_points (up to 10) and key_terms (up to 12).
Use only what the part summaries say.
""" + _RULES + """
Part summaries:
{parts}
"""

_FINAL_FROM_PARTIALS = """
You are a scientific assistant for a chemistry faculty library.
Below are summaries of consecutive parts of one document (file name: {source_file}), in
reading order. Write the summary of the WHOLE document from them.

Produce:
- title: the document's own title if the summaries state one, otherwise a short descriptive title
- overview: a coherent summary of 1-3 paragraphs (main subject, main content, conclusions),
  not a part-by-part list
- key_points: 5-10 short, self-contained points covering the whole document
- key_terms: up to 12 important terms or concepts, each as "term: short explanation"
Use only what the part summaries say.
""" + _RULES + """
Part summaries:
{parts}
"""


def _render(template: str, language: str, **values: object) -> str:
    return dedent(template).strip().format(language=_LANGUAGE_NAME[language], **values)


class SummaryPromptBuilder:
    """Prompts for summarizing one document: single pass, map (per section), merge, final reduce."""

    def single_pass(self, source_file: str, text: str, language: str) -> str:
        return _render(_SINGLE_PASS, language, source_file=source_file, text=text)

    def map_section(self, source_file: str, text: str, language: str, index: int, total: int) -> str:
        return _render(_MAP_SECTION, language, source_file=source_file, text=text, index=index, total=total)

    def merge_partials(self, source_file: str, parts: str, language: str) -> str:
        return _render(_MERGE_PARTIALS, language, source_file=source_file, parts=parts)

    def final_from_partials(self, source_file: str, parts: str, language: str) -> str:
        return _render(_FINAL_FROM_PARTIALS, language, source_file=source_file, parts=parts)
