"""Puts the spaces back into English OCR text that came out glued together.

RapidOCR's default (Chinese+English) recognition model often drops the spaces
between English words: ``Ithasbeenknownforalongtime``. Embeddings and keyword
matching cannot use that, so glued lines are re-segmented with ``wordninja``
(a tiny pure-Python word splitter: ``pip install wordninja``).

Only lines that look glued are touched, and only runs of Latin letters, so
digits, punctuation, formulas and Persian text are left as they are.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_LATIN_RUN = re.compile(r"[A-Za-z]+")

GLUED_RUN = 22  # a line with a run of Latin letters this long has lost its spaces
MIN_RUN = 6  # inside such a line, runs shorter than this are left alone

_segmenter = None
_segmenter_loaded = False


def _default_segmenter():
    global _segmenter, _segmenter_loaded
    if not _segmenter_loaded:
        _segmenter_loaded = True
        try:
            import wordninja

            _segmenter = wordninja.split
        except ImportError:
            logger.warning(
                "wordninja is not installed: glued English OCR text cannot be repaired "
                "(pip install wordninja)"
            )
    return _segmenter


def looks_glued(line: str) -> bool:
    return any(len(run) >= GLUED_RUN for run in _LATIN_RUN.findall(line))


def restore_english_spaces(text: str, segmenter=None) -> str:
    """Re-segment glued English lines. ``segmenter(str) -> list[str]`` (default: wordninja)."""
    split = segmenter or _default_segmenter()
    if split is None:
        return text

    def fix(match: re.Match) -> str:
        run = match.group()
        if len(run) < MIN_RUN:
            return run
        pieces = split(run)
        return " ".join(pieces) if "".join(pieces) == run else run  # never lose characters

    lines = [
        _LATIN_RUN.sub(fix, line) if looks_glued(line) else line
        for line in text.split("\n")
    ]
    return "\n".join(lines)
