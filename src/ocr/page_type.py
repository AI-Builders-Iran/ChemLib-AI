"""Cheap, model-free page-type heuristic used to decide whether a scanned
page (one with no usable text layer) is worth sending to OCR.

    PDF Page -> Page Analysis -> Text / Table / Complex Figure -> OCR or Skip

Categories:

* ``TABLE`` — grid/ruling-line evidence found; the page is always OCR'd,
  never skipped, even though it isn't running prose.
* ``FIGURE`` — looks like a diagram, chemical structure, chart or photo with
  little/no running text and no table grid; skipped for this MVP (no OCR
  call, no API cost).
* ``TEXT`` — everything else (including blank pages, left to the existing
  blank-page check); OCR'd as before.

This is intentionally simple — no layout model, no ML, just pixel-density
heuristics on a down-scaled grayscale image. ``src.layout.engines``
(PP-StructureV3) already does a much better job of finding tables/figures
when it's installed, but that is a heavy, opt-in dependency the MVP does not
require. This heuristic only needs to be "good enough" to avoid burning OCR
calls on pages that are obviously not text — it is expected to misclassify
some edge cases (e.g. a borderless table, or a figure that happens to fill
most of the page), which is an acceptable trade-off at this stage.
"""

from __future__ import annotations

import numpy as np

TABLE = "table"
FIGURE = "figure"
TEXT = "text"

# 0-255 grayscale; a pixel darker than this counts as "ink".
_DARK_THRESHOLD = 200

# A row/column whose ink fraction is at least this high looks like a ruling
# line rather than sparse text or a curve.
_LINE_MIN_RATIO = 0.6

# A ruling line is one long *unbroken* dark run across (most of) a row or
# column. Overall row/column darkness fraction is NOT used for this, because
# a dense paragraph of text can reach a similar average darkness while still
# being made of many short, separated glyph strokes with white gaps between
# words/letters.
_MIN_LINES_FOR_TABLE = 3


def _has_ruling_lines(dark: np.ndarray) -> bool:
    """True if enough rows/columns contain one long, unbroken dark run
    (a ruling line) rather than many short, separated dark runs (text)."""
    row_lines = sum(1 for row in dark if _max_run_ratio(row) >= _LINE_MIN_RATIO)
    col_lines = sum(1 for col in dark.T if _max_run_ratio(col) >= _LINE_MIN_RATIO)
    return (row_lines + col_lines) >= _MIN_LINES_FOR_TABLE


def _max_run_ratio(line: np.ndarray) -> float:
    """Longest contiguous run of True values in a 1D boolean array, as a
    fraction of the array's length (0.0 for an all-False line)."""
    if not line.any():
        return 0.0
    padded = np.concatenate(([False], line, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]
    return float((ends - starts).max()) / line.size

# Running text normally spans most of the page; a figure/diagram is usually
# a smaller, more centered block with wide blank margins around it.
_TEXT_COVERAGE_WIDTH = 0.55
_TEXT_COVERAGE_HEIGHT = 0.40

_MAX_THUMBNAIL = 500  # keep the heuristic fast: no need for the full-res render


def classify_page(image) -> str:
    """Classify a rendered PIL page image as TABLE, FIGURE, or TEXT."""
    gray = image.convert("L")
    gray.thumbnail((_MAX_THUMBNAIL, _MAX_THUMBNAIL))
    array = np.asarray(gray)
    dark = array < _DARK_THRESHOLD

    if not dark.any():
        # Nothing on the page at all — let the existing is_blank_image() /
        # OCR-pipeline blank check handle it; don't call it a figure.
        return TEXT

    if _has_ruling_lines(dark):
        return TABLE

    rows = np.where(dark.any(axis=1))[0]
    cols = np.where(dark.any(axis=0))[0]
    height, width = dark.shape
    ink_width_ratio = (cols[-1] - cols[0] + 1) / width
    ink_height_ratio = (rows[-1] - rows[0] + 1) / height

    if ink_width_ratio >= _TEXT_COVERAGE_WIDTH and ink_height_ratio >= _TEXT_COVERAGE_HEIGHT:
        return TEXT

    return FIGURE
