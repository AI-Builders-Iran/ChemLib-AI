"""Detects a Compare-Sources request typed directly into the normal chat.

The backend already has a full Compare API (``RAGService.compare_sources`` /
``POST /api/v1/compare``); this module is the small piece of integration that
lets a user trigger it from the same chat instead of a separate screen —
e.g. "Compare these sources: Paper A and Paper B" or
"این دو منبع را با هم مقایسه کن".

Detection is a simple regex + fuzzy-name match against the documents
currently visible in the chat (the library, or the user's private
documents) — no new NLU/model, consistent with the rest of this MVP.
"""

from __future__ import annotations

import difflib
import re

from .helpers import display_name

# English: "compare [these [two] source(s)[:]] A and/vs/versus B"
_EN_COMPARE = re.compile(
    r"compare\s+(?:these\s+(?:two\s+)?sources?\s*[:\-]?\s*)?(.+?)\s+(?:and|vs\.?|versus)\s+(.+?)[.?!]*$",
    re.IGNORECASE,
)

# Persian: "مقایسه: A و B" / "A و B را مقایسه کن" / "A را با B مقایسه کن"
_FA_LABELED = re.compile(r"مقایسه[^:،]*[:،]\s*(.+?)\s+(?:و|با)\s+(.+)")
_FA_WITH = re.compile(r"(.+?)\s+را\s+با\s+(.+?)\s+مقایسه")
_FA_AND = re.compile(r"(.+?)\s+و\s+(.+?)\s+(?:را\s+)?مقایسه")

# No two names given, just "compare these two sources" / "این دو منبع را با هم مقایسه کن":
# only usable when exactly two documents are in scope, so there is no ambiguity.
_BARE_COMPARE = re.compile(
    r"(این\s+دو\s+منبع|با\s+هم\s+مقایسه|compare\s+these\s+(?:two\s+)?sources?)", re.IGNORECASE
)

_STRIP_CHARS = " \t\"'«»:،.؟!?"


def _extract_pair(question: str) -> tuple[str, str] | None:
    for pattern in (_FA_LABELED, _FA_WITH, _FA_AND):
        match = pattern.search(question)
        if match:
            return match.group(1).strip(_STRIP_CHARS), match.group(2).strip(_STRIP_CHARS)

    match = _EN_COMPARE.search(question)
    if match:
        return match.group(1).strip(_STRIP_CHARS), match.group(2).strip(_STRIP_CHARS)

    return None


def _match_document(name: str, documents):
    name_norm = name.strip(_STRIP_CHARS).lower()
    if not name_norm:
        return None

    labels = {d.document_id: display_name(d.source_file).lower() for d in documents}
    raws = {d.document_id: d.source_file.lower() for d in documents}

    for document in documents:
        label, raw = labels[document.document_id], raws[document.document_id]
        if name_norm == label or name_norm == raw:
            return document

    for document in documents:
        label, raw = labels[document.document_id], raws[document.document_id]
        if name_norm in label or name_norm in raw or label in name_norm:
            return document

    close = difflib.get_close_matches(name_norm, list(labels.values()), n=1, cutoff=0.4)
    if close:
        matched_id = next(doc_id for doc_id, label in labels.items() if label == close[0])
        return next(d for d in documents if d.document_id == matched_id)

    return None


def detect_compare(question: str, documents):
    """Returns ``(doc_a, doc_b)`` (``IndexedDocument``s) if ``question`` asks
    to compare two of the currently available ``documents``, else ``None``.
    """
    if len(documents) < 2:
        return None

    pair = _extract_pair(question)
    if pair is not None:
        raw_a, raw_b = pair
        doc_a = _match_document(raw_a, documents)
        doc_b = _match_document(raw_b, documents)
        if doc_a is not None and doc_b is not None and doc_a.document_id != doc_b.document_id:
            return doc_a, doc_b

    if len(documents) == 2 and _BARE_COMPARE.search(question):
        return documents[0], documents[1]

    return None
