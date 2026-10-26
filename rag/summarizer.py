"""Document summarization on top of the chunks the library already stores.

Why chunks and not the file: a document that was ingested has already been through
loading, OCR, cleaning and chunking, and its chunks are in the vector store (library) or in
the tab's in-memory store (private documents). Summarizing from those chunks means no second
extraction, no second OCR pass and no embedding at all.

Strategy
--------
* Short text (<= ``single_pass_chars``): one LLM call that returns the final summary.
* Long text: **map-reduce**.
    1. map    - the chunks are packed, in reading order, into sections of about
                ``section_chars`` characters and each section is summarized separately;
    2. reduce - the section summaries are merged into the final summary. If the section
                summaries are themselves too long for one call they are merged in groups
                first (a bounded, hierarchical reduce), so the final call never overflows
                the model's context window however long the document is.
  Map-reduce is used rather than ``refine`` because the map calls are independent (they can
  run concurrently and one failing section does not poison the rest) and no call ever needs
  more than ``max_section_chars`` of input. ``refine`` is strictly sequential and a single
  failure or a drifting running summary affects everything after it.

Cost control
------------
The number of map calls is capped (``max_map_calls``). Sections grow up to
``max_section_chars`` before the cap bites; if a document is still too long, sections are
sampled evenly and the response says so (``coverage`` < 1 and a warning) instead of
silently pretending the whole document was read. Finished summaries are cached by the
text's fingerprint, so asking again for the same unchanged document makes no LLM call.

This module knows nothing about the UI, the vector store or any provider: it receives
chunks and an ``extract(prompt, schema)`` callable (``RAGService`` passes its own, which
already does the provider fallback).
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel

from rag.prompts import SummaryPromptBuilder, detect_language
from rag.schemas import ChunkResult, FinalSummary, PartialSummary, SummaryResponse, chunk_order

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
ExtractFn = Callable[[str, Type[T]], T]

MAX_KEY_POINTS = 12
MAX_KEY_TERMS = 15
MAX_REDUCE_DEPTH = 4  # merge rounds before giving up on shrinking the section summaries further
_OVERLAP_SCAN_CHARS = 400  # chunk overlap is 200 chars; look a little further to be safe
_MIN_OVERLAP_CHARS = 20


# ---------------------------------------------------------------------------
# Errors - each one maps to a distinct, user-presentable situation
# ---------------------------------------------------------------------------

class SummarizationError(RuntimeError):
    """The LLM could not produce a usable summary (provider failure, empty/invalid output)."""


class DocumentNotFoundError(LookupError):
    """No chunks are stored for the requested document id."""


class EmptyDocumentError(ValueError):
    """The document has no usable text (nothing was extracted, or far too little to summarize)."""


# ---------------------------------------------------------------------------
# Configuration (all overridable from .env, see .env)
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class SummarizerConfig:
    single_pass_chars: int = 24_000  # up to this much text: one call, no map-reduce
    section_chars: int = 12_000  # target size of one map section
    max_section_chars: int = 30_000  # a section never grows beyond this
    max_map_calls: int = 30  # hard cap on map calls (cost control)
    reduce_chars: int = 24_000  # largest input of one merge/final call
    concurrency: int = 3  # map calls running at once (1 = sequential)
    min_chars: int = 40  # less text than this is treated as an empty document

    @classmethod
    def from_env(cls) -> "SummarizerConfig":
        defaults = cls()
        return cls(
            single_pass_chars=_env_int("SUMMARY_SINGLE_PASS_CHARS", defaults.single_pass_chars),
            section_chars=_env_int("SUMMARY_SECTION_CHARS", defaults.section_chars),
            max_section_chars=_env_int("SUMMARY_MAX_SECTION_CHARS", defaults.max_section_chars),
            max_map_calls=_env_int("SUMMARY_MAX_MAP_CALLS", defaults.max_map_calls),
            reduce_chars=_env_int("SUMMARY_REDUCE_CHARS", defaults.reduce_chars),
            concurrency=_env_int("SUMMARY_CONCURRENCY", defaults.concurrency),
            min_chars=defaults.min_chars,
        )


# ---------------------------------------------------------------------------
# Result cache - keyed by what was summarized, not by document id
# ---------------------------------------------------------------------------

_CACHE_SIZE = 32
_cache: "OrderedDict[str, SummaryResponse]" = OrderedDict()
_cache_lock = threading.Lock()


def _cache_get(key: str) -> SummaryResponse | None:
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
        return hit


def _cache_put(key: str, value: SummaryResponse) -> None:
    with _cache_lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# ---------------------------------------------------------------------------
# Text assembly
# ---------------------------------------------------------------------------

@dataclass
class _Block:
    text: str
    page_from: int | None
    page_to: int | None

    @property
    def chars(self) -> int:
        return len(self.text)


def _trim_overlap(previous: str, current: str) -> str:
    """Drop from ``current`` the start that repeats the end of ``previous``.

    Ingestion chunks text with a 200-character overlap; without this, every chunk boundary
    would feed the LLM the same sentence twice.
    """
    tail = previous[-_OVERLAP_SCAN_CHARS:]
    for size in range(min(len(tail), len(current)), _MIN_OVERLAP_CHARS - 1, -1):
        if tail.endswith(current[:size]):
            return current[size:].lstrip()
    return current


def _page_label(page: int | None) -> str:
    # Pages are stored 0-based by the PDF loader; readers count from 1.
    return "" if page is None else str(page + 1)


def _build_blocks(chunks: list[ChunkResult]) -> list[_Block]:
    """Chunks in reading order -> text blocks with page markers and chunk overlap removed."""
    blocks: list[_Block] = []
    previous_text = ""
    previous_page: int | None = None
    first = True

    for chunk in chunks:
        text = chunk.text.strip()
        if not text:
            continue
        # Only plain text chunks overlap; a table or formula is stored whole.
        if chunk.block_type == "text" and previous_text:
            text = _trim_overlap(previous_text, text)
        previous_text = chunk.text.strip() if chunk.block_type == "text" else ""
        if not text:
            continue

        label = _page_label(chunk.page)
        if label and (first or chunk.page != previous_page):
            text = f"[page {label}]\n{text}"
        previous_page = chunk.page
        first = False
        blocks.append(_Block(text=text, page_from=chunk.page, page_to=chunk.page))

    return blocks


def _join(blocks: list[_Block]) -> str:
    return "\n\n".join(block.text for block in blocks)


def _pack_sections(blocks: list[_Block], limit: int) -> list[list[_Block]]:
    """Greedy, order-preserving packing of blocks into sections of at most ~``limit`` chars."""
    sections: list[list[_Block]] = []
    current: list[_Block] = []
    size = 0
    for block in blocks:
        if current and size + block.chars + 2 > limit:
            sections.append(current)
            current, size = [], 0
        current.append(block)
        size += block.chars + 2
    if current:
        sections.append(current)
    return sections


def _page_span(blocks: list[_Block]) -> str:
    pages = [p for b in blocks for p in (b.page_from, b.page_to) if p is not None]
    if not pages:
        return ""
    low, high = min(pages) + 1, max(pages) + 1
    return f"page {low}" if low == high else f"pages {low}-{high}"


def _clean_list(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items or []:
        text = " ".join(str(item).split())
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) == limit:
            break
    return cleaned


def _format_partial(index: int, span: str, partial: PartialSummary) -> str:
    header = f"Part {index}" + (f" ({span})" if span else "")
    lines = [header + ":", partial.summary.strip()]
    if partial.key_points:
        lines.append("Key points: " + "; ".join(partial.key_points))
    if partial.key_terms:
        lines.append("Key terms: " + "; ".join(partial.key_terms))
    return "\n".join(line for line in lines if line)


# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------

class DocumentSummarizer:
    """Summarizes one document from its chunks. Stateless apart from the shared result cache."""

    def __init__(self, extract: ExtractFn, config: SummarizerConfig | None = None) -> None:
        self._extract = extract
        self._config = config or SummarizerConfig.from_env()
        self._prompts = SummaryPromptBuilder()

    # -- public ------------------------------------------------------------

    def summarize(
        self, chunks: list[ChunkResult], *, document_id: str, source_file: str
    ) -> SummaryResponse:
        """Summarize the document made of ``chunks``.

        Raises:
            EmptyDocumentError: no chunks, no text, or almost no text.
            SummarizationError: the LLM failed or returned nothing usable.
        """
        cfg = self._config
        ordered = sorted(chunks, key=chunk_order)
        blocks = _build_blocks(ordered)
        total_chars = sum(block.chars for block in blocks)
        if not blocks or total_chars < cfg.min_chars:
            raise EmptyDocumentError(
                "No readable text was extracted from this document, so there is nothing to summarize."
            )

        text = _join(blocks)
        language = detect_language(text)

        cache_key = self._cache_key(text, language)
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.info("Summary cache hit for %s", source_file)
            return cached.model_copy(
                update={"document_id": document_id, "source_file": source_file, "cached": True, "llm_calls": 0}
            )

        if total_chars <= cfg.single_pass_chars:
            result = self._single_pass(source_file, text, language, len(ordered))
        else:
            result = self._map_reduce(source_file, blocks, language, len(ordered), total_chars)

        response = result.model_copy(update={"document_id": document_id})
        _cache_put(cache_key, response)
        return response

    # -- strategies ---------------------------------------------------------

    def _single_pass(self, source_file: str, text: str, language: str, chunk_count: int) -> SummaryResponse:
        prompt = self._prompts.single_pass(source_file, text, language)
        final = self._call(prompt, FinalSummary, "summary")
        return self._response(
            final, source_file, language,
            strategy="single_pass", chunks_used=chunk_count, sections_total=1, sections_summarized=1,
            coverage=1.0, llm_calls=1, warnings=[],
        )

    def _map_reduce(
        self, source_file: str, blocks: list[_Block], language: str, chunk_count: int, total_chars: int
    ) -> SummaryResponse:
        cfg = self._config
        warnings: list[str] = []

        # Grow sections (up to the hard limit) so the document fits in max_map_calls calls.
        section_limit = min(cfg.max_section_chars, max(cfg.section_chars, math.ceil(total_chars / cfg.max_map_calls)))
        blocks = self._cap_block_size(blocks, cfg.max_section_chars, warnings)
        sections = _pack_sections(blocks, section_limit)
        sections_total = len(sections)

        selected = list(range(sections_total))
        if sections_total > cfg.max_map_calls:
            # Even sampling keeps the beginning, the end and a spread of the middle.
            step = (sections_total - 1) / (cfg.max_map_calls - 1) if cfg.max_map_calls > 1 else 0
            selected = sorted({round(i * step) for i in range(cfg.max_map_calls)})
            warnings.append(
                f"The document is very long: {len(selected)} of {sections_total} sections were summarized "
                f"(raise SUMMARY_MAX_MAP_CALLS to cover more, at a higher cost)."
            )

        outcomes = self._map(source_file, sections, selected, language)

        partials: list[tuple[str, PartialSummary]] = []
        covered_chars = 0
        failures: list[str] = []
        for index, outcome in zip(selected, outcomes):
            if isinstance(outcome, Exception):
                failures.append(str(outcome))
                continue
            section_chars = sum(b.chars for b in sections[index])
            covered_chars += section_chars
            # An "empty" section (page furniture, unreadable OCR) is valid: it simply adds nothing.
            if outcome.summary.strip() or outcome.key_points:
                partials.append((_page_span(sections[index]), outcome))

        llm_calls = len(selected)
        if failures:
            if len(failures) == len(selected):
                raise SummarizationError(f"Every section failed to summarize. Last error: {failures[-1]}")
            warnings.append(
                f"{len(failures)} of {len(selected)} sections could not be summarized and are missing "
                f"from the result (last error: {failures[-1]})."
            )
        if not partials:
            raise SummarizationError("The model found no substantive content in the document text.")

        texts = [_format_partial(i, span, partial) for i, (span, partial) in enumerate(partials, start=1)]
        texts, merge_calls = self._shrink(source_file, texts, language)
        llm_calls += merge_calls

        final = self._call(
            self._prompts.final_from_partials(source_file, "\n\n".join(texts), language), FinalSummary, "final summary"
        )
        llm_calls += 1

        return self._response(
            final, source_file, language,
            strategy="map_reduce", chunks_used=chunk_count, sections_total=sections_total,
            sections_summarized=len(selected) - len(failures),
            coverage=round(min(1.0, covered_chars / max(total_chars, 1)), 3),
            llm_calls=llm_calls, warnings=warnings,
        )

    # -- helpers ------------------------------------------------------------

    def _map(
        self, source_file: str, sections: list[list[_Block]], selected: list[int], language: str
    ) -> list[PartialSummary | Exception]:
        total = len(selected)

        def run(position: int, index: int) -> PartialSummary | Exception:
            prompt = self._prompts.map_section(source_file, _join(sections[index]), language, position, total)
            try:
                return self._call(prompt, PartialSummary, f"section {position}/{total}")
            except SummarizationError as exc:
                logger.warning("Section %d/%d of %s failed: %s", position, total, source_file, exc)
                return exc

        jobs = list(enumerate(selected, start=1))
        workers = max(1, min(self._config.concurrency, len(jobs)))
        if workers == 1:
            return [run(position, index) for position, index in jobs]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(lambda job: run(*job), jobs))

    def _shrink(self, source_file: str, texts: list[str], language: str) -> tuple[list[str], int]:
        """Merge section summaries in groups until they fit one final call. Returns (texts, calls made)."""
        limit = self._config.reduce_chars
        calls = 0
        for _ in range(MAX_REDUCE_DEPTH):
            if sum(len(t) for t in texts) <= limit or len(texts) < 2:
                break
            groups = self._group(texts, limit)
            if len(groups) >= len(texts):  # nothing to merge: every summary already fills a call
                break
            merged: list[str] = []
            for number, group in enumerate(groups, start=1):
                if len(group) == 1:
                    merged.append(group[0])
                    continue
                result = self._call(
                    self._prompts.merge_partials(source_file, "\n\n".join(group), language), PartialSummary, "merge"
                )
                calls += 1
                merged.append(_format_partial(number, "", result))
            texts = merged
        if sum(len(t) for t in texts) > limit:
            logger.warning("Section summaries for %s are still long after the merge rounds", source_file)
        return texts, calls

    @staticmethod
    def _group(texts: list[str], limit: int) -> list[list[str]]:
        groups: list[list[str]] = []
        current: list[str] = []
        size = 0
        for text in texts:
            if current and size + len(text) > limit:
                groups.append(current)
                current, size = [], 0
            current.append(text)
            size += len(text)
        if current:
            groups.append(current)
        return groups

    @staticmethod
    def _cap_block_size(blocks: list[_Block], limit: int, warnings: list[str]) -> list[_Block]:
        """A single stored block (e.g. one huge table) larger than a section is cut to the limit."""
        capped: list[_Block] = []
        cut = 0
        for block in blocks:
            if block.chars > limit:
                cut += 1
                block = _Block(text=block.text[:limit], page_from=block.page_from, page_to=block.page_to)
            capped.append(block)
        if cut:
            warnings.append(f"{cut} very large block(s) (such as a huge table) were truncated before summarizing.")
        return capped

    def _call(self, prompt: str, schema: Type[T], what: str) -> T:
        try:
            return self._extract(prompt, schema)
        except Exception as exc:  # noqa: BLE001 - provider/network/format errors all become one typed error
            raise SummarizationError(f"The model call for the {what} failed: {exc}") from exc

    def _cache_key(self, text: str, language: str) -> str:
        cfg = self._config
        parameters = (
            cfg.single_pass_chars, cfg.section_chars, cfg.max_section_chars, cfg.max_map_calls, cfg.reduce_chars, language
        )
        digest = hashlib.sha256()
        digest.update(text.encode("utf-8"))
        digest.update(repr(parameters).encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _response(final: FinalSummary, source_file: str, language: str, **fields) -> SummaryResponse:
        overview = (final.overview or "").strip()
        if not overview:
            raise SummarizationError("The model returned an empty summary.")
        return SummaryResponse(
            document_id="",
            source_file=source_file,
            title=(final.title or "").strip() or Path(source_file).stem.replace("_", " "),
            language=language,
            overview=overview,
            key_points=_clean_list(final.key_points, MAX_KEY_POINTS),
            key_terms=_clean_list(final.key_terms, MAX_KEY_TERMS),
            **fields,
        )
