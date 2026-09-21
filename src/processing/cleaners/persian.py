"""Persian-aware cleaners for the RAG ingestion pipeline.

Text extracted from Persian PDFs/DOCX is messy in predictable ways: Arabic
letter variants (ي ك), mixed digit systems, stray diacritics and kashida,
invisible bidi characters, missing half-spaces (نیم‌فاصله) and hard line breaks
in the middle of sentences. Embeddings and keyword overlap work better on one
canonical spelling, and users type questions in yet another variant, so the
character-level rules are shared with :func:`normalize_query`.

Order in the pipeline: NFKC (UnicodeCleaner) -> TextCleaner -> the cleaners here
-> WhitespaceCleaner.
"""

from __future__ import annotations

import re
import unicodedata

from .base import BaseCleaner

ZWNJ = "\u200c"

# Arabic-script letters only (no digits, marks or punctuation).
_L = "\u0621-\u064A\u066E-\u06D3\u06FA-\u06FF"

_ARABIC_TO_LATIN_DIGITS = {**{0x0660 + i: ord("0") + i for i in range(10)},
                           **{0x06F0 + i: ord("0") + i for i in range(10)}}
_LATIN_TO_PERSIAN_DIGITS = {ord("0") + i: 0x06F0 + i for i in range(10)}

_CHAR_MAP = str.maketrans({
    "\u064A": "\u06CC",  # ي -> ی
    "\u0649": "\u06CC",  # ى -> ی
    "\u0643": "\u06A9",  # ك -> ک
    "\u0629": "\u0647",  # ة -> ه
    "\u06C0": "\u0647",  # ۀ -> ه
    "\u06D5": "\u0647",  # ە -> ه (NFKC turns ۀ into ە + hamza mark)
    "\u06BE": "\u0647",  # ھ -> ه
    "\u06C1": "\u0647",  # ہ -> ه
    "\u066B": ".",       # Arabic decimal separator
    "\u066C": ",",       # Arabic thousands separator
    "\u066A": "%",       # Arabic percent sign
})
_ALEF_MAP = str.maketrans({"\u0623": "\u0627", "\u0625": "\u0627", "\u0671": "\u0627"})  # أ إ ٱ -> ا

_DIACRITICS = re.compile("[\u064B-\u065F\u0670]")
_KASHIDA = re.compile("\u0640")
_INVISIBLE = re.compile("[\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_LATIN_DIGIT_RUN = re.compile(r"(?<![A-Za-z\d])\d+(?![A-Za-z\d])")  # whole numbers only, not in H2O, C6H12O6, B12

_ZWNJ_RUN = re.compile(f"{ZWNJ}{{2,}}")
_ZWNJ_NOT_BETWEEN_LETTERS = re.compile(f"(?<![{_L}]){ZWNJ}|{ZWNJ}(?![{_L}])")


def _tidy_zwnj(text: str) -> str:
    """Keep a half-space only when it sits between two Persian letters."""
    if ZWNJ not in text:
        return text
    text = _ZWNJ_RUN.sub(ZWNJ, text)
    return _ZWNJ_NOT_BETWEEN_LETTERS.sub("", text)


class PersianCharacterCleaner(BaseCleaner):
    """Canonical Persian characters, digits and half-spaces.

    Args:
        digits: ``"latin"`` (default) turns ۱۲۳ and ١٢٣ into 123, which keeps
            formulas and units intact; ``"persian"`` turns standalone numbers
            into ۱۲۳ (numbers glued to Latin letters, like H2O, are left alone);
            ``"keep"`` does not touch digits.
        remove_diacritics: drop harakat (َ ُ ِ ّ ْ ً ...). Kashida (ـ) is always removed.
        unify_alef: map أ إ ٱ to ا (آ is kept).
    """

    def __init__(self, digits: str = "latin", remove_diacritics: bool = True, unify_alef: bool = False):
        if digits not in ("latin", "persian", "keep"):
            raise ValueError("digits must be 'latin', 'persian' or 'keep'")
        self._digits = digits
        self._remove_diacritics = remove_diacritics
        self._unify_alef = unify_alef

    def clean(self, text: str) -> str:
        text = _INVISIBLE.sub("", text)
        text = text.translate(_CHAR_MAP)
        if self._unify_alef:
            text = text.translate(_ALEF_MAP)
        if self._remove_diacritics:
            text = _DIACRITICS.sub("", text)
        text = _KASHIDA.sub("", text)

        if self._digits != "keep":
            text = text.translate(_ARABIC_TO_LATIN_DIGITS)
            if self._digits == "persian":
                text = _LATIN_DIGIT_RUN.sub(lambda m: m.group().translate(_LATIN_TO_PERSIAN_DIGITS), text)

        return _tidy_zwnj(text)


_MI_PREFIX = re.compile(rf"(?<![{_L}])(ن?می)[ \t]+(?=[{_L}])")
_AFFIX = re.compile(rf"(?<=[{_L}])[ \t]+(?=(?:ها|های|هایی|ترین|تر)(?![{_L}]))")
_SPACE_BEFORE_PUNCT = re.compile(r"[ \t]+([،؛؟])")
_NO_SPACE_AFTER_PUNCT = re.compile(rf"([،؛؟])(?=[{_L}0-9])")


class PersianSpacingCleaner(BaseCleaner):
    """Restores half-spaces and fixes spacing around Persian punctuation.

    * ``می شود`` -> ``می‌شود``, ``نمی توان`` -> ``نمی‌توان``
    * ``کتاب ها`` -> ``کتاب‌ها``, ``بزرگ تر`` -> ``بزرگ‌تر`` (ها، های، هایی، تر، ترین)
    * ``سلام ،دنیا`` -> ``سلام، دنیا``; ``چیست ؟`` -> ``چیست؟``
    """

    def clean(self, text: str) -> str:
        text = _MI_PREFIX.sub(rf"\1{ZWNJ}", text)
        text = _AFFIX.sub(ZWNJ, text)
        text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
        return _NO_SPACE_AFTER_PUNCT.sub(r"\1 ", text)


_TERMINAL = (".", "!", "?", "؟", ":", "؛", ";", "…")
_CLOSERS = ")]»\"'”"


class LineWrapCleaner(BaseCleaner):
    """Joins lines that PDF extraction broke in the middle of a sentence.

    A line break is removed only when the line before it is long (a wrapped
    line, not a heading or list item), does not end a sentence, and the next
    line starts with a letter. Blank lines (paragraph breaks) are never crossed.
    """

    def __init__(self, min_line_length: int = 35):
        self._min_line_length = min_line_length

    def clean(self, text: str) -> str:
        lines: list[str] = []
        for raw in text.split("\n"):
            line = raw.strip()
            if lines and line and self._continues(lines[-1], line):
                lines[-1] = f"{lines[-1]} {line}"
            else:
                lines.append(line)
        return "\n".join(lines)

    def _continues(self, previous: str, following: str) -> bool:
        if len(previous) < self._min_line_length:
            return False
        if previous.rstrip(_CLOSERS).endswith(_TERMINAL):
            return False
        return following[0].isalpha()


_QUERY_CLEANERS = (PersianCharacterCleaner(), PersianSpacingCleaner())


def normalize_query(text: str) -> str:
    """Canonical form of a user question, matching how documents are cleaned.

    Only character-level rules are applied (letters, digits, half-spaces,
    punctuation spacing); line joining makes no sense for a question.
    """
    text = unicodedata.normalize("NFKC", text)
    for cleaner in _QUERY_CLEANERS:
        text = cleaner.clean(text)
    return text.strip()
