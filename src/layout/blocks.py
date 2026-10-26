"""The unit of structured content a layout segmenter finds on a page.

A page is still read as flat text by the existing OCR/text-layer pipeline
(``src.loaders.pdf_loader``) — that does not change. A ``LayoutSegmenter``
runs *in addition*, looking only for regions worth treating specially:
tables, formulas and figures. Everything else stays inside the plain text
block, so a segmenter that finds nothing (:class:`NullLayoutSegmenter`)
reproduces today's behaviour exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Keep in sync with block_type values used as chunk metadata throughout
# rag/ingestion.py, src/retrieval/vector_store.py and rag/prompts.py.
BLOCK_TEXT = "text"
BLOCK_TABLE = "table"
BLOCK_FORMULA = "formula"
BLOCK_FIGURE = "figure"


@dataclass
class Block:
    """One structured region detected on a page.

    ``content`` is already the text that should be embedded and shown to the
    LLM: a Markdown table for ``table``, a LaTeX expression for ``formula``,
    a short natural-language caption for ``figure``.
    """

    block_type: str
    content: str
    bbox: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1), page pixels
    confidence: float | None = None
    image_path: str | None = None  # figures only: the cropped region saved to disk
    extra: dict = field(default_factory=dict)
