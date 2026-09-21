"""Small pure helpers for the UI (no Streamlit imports, easy to unit-test)."""

from __future__ import annotations

import zlib
from collections.abc import Iterable
from pathlib import Path

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# Number of colour classes (.t0 ... .t5) defined in theme.py.
TILE_COLOR_COUNT = 6


def to_fa_digits(value: int | str) -> str:
    """Render Latin digits as Persian digits: 12 -> ۱۲."""
    return str(value).translate(_FA_DIGITS)


def page_label(page: int | None) -> str:
    """Human page number for a stored page index.

    The PDF loader stores pages 0-based; readers expect the first page to be 1.
    Sources without pages (TXT/DOCX) get an empty label.
    """
    if page is None:
        return ""
    return to_fa_digits(page + 1)


def element_symbol(name: str) -> str:
    """Two-letter 'element symbol' for a source, like a periodic-table cell.

    ``Organic_Chemistry.pdf`` -> ``Or``;  ``شیمی_آلی.pdf`` -> ``شی``.
    """
    stem = Path(name).stem or name
    letters = [ch for ch in stem if ch.isalpha()]
    if not letters:
        letters = [ch for ch in stem if ch.isalnum()]
    if not letters:
        return "؟"

    first, second = letters[0], letters[1] if len(letters) > 1 else ""
    if first.isascii():  # Latin: capital + lowercase, like Na, Cl
        return first.upper() + second.lower()
    return first + second


def display_name(name: str) -> str:
    """Readable book label: no extension, underscores as spaces (so long names wrap at words)."""
    stem = Path(name).stem or name
    return stem.replace("_", " ").strip()


def tile_color_index(key: str) -> int:
    """Stable colour slot for a source, so a book keeps its colour everywhere."""
    return zlib.crc32(key.encode("utf-8")) % TILE_COLOR_COUNT


def unique_sources(sources: Iterable[dict]) -> list[dict]:
    """Collapse chunk-level sources into unique (file, page) pairs, sorted."""
    seen: set[tuple[str, int | None]] = set()
    unique: list[dict] = []
    for source in sources:
        key = (source["file"], source.get("page"))
        if key in seen:
            continue
        seen.add(key)
        unique.append({"file": source["file"], "page": source.get("page")})
    unique.sort(key=lambda s: (s["file"].lower(), -1 if s["page"] is None else s["page"]))
    return unique
