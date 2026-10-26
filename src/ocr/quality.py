"""Cheap, model-free checks on extracted text and page images.

They answer three questions:

* Does this PDF page already have a *usable* text layer, or must it be OCR'd?
  (:func:`has_text_layer`; a text layer can exist and still be garbage, e.g.
  reversed Persian from a legacy font.)
* Is this OCR output believable? (:func:`assess_text_quality`)
* Is this page blank, so no OCR call is worth paying for? (:func:`is_blank_image`)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Very common function words. Real prose contains many of them; garbled or
# reversed text almost none. Forms are already canonical (ی ک, no diacritics).
_FA_COMMON = frozenset(
    "و در به از که این را با است برای آن یک می شود هم یا تا بر های ها کرد شده شد نیز اما اگر پس بود بین دو هر چه خود ما".split()
)
_EN_COMMON = frozenset(
    "the of and to in is that for with as by on are this an be or from at it which not can".split()
)

_WORD = re.compile(r"[^\W\d_]+")

# ---------------------------------------------------------------------------
# Scientific / chemistry text detection
#
# Chemistry pages are full of formulas (CH3CH2CN, H2SO4), isotope labels
# (13C NMR), units (cm-1, ppm) and symbols (arrow, degree). They contain few
# dictionary words and a lot of digits, so the prose-oriented checks below
# (``few_letters``, ``no_common_words``) would reject perfectly good OCR.
# We measure how "chemical" the text is (``chem_density``) and relax only those
# two prose checks in proportion to it. Garbage, repeated-character, glued-word
# and fragmented-word checks are NOT relaxed.
# ---------------------------------------------------------------------------
_ELEMENTS = frozenset(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr "
    "Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu "
    "Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr D".split()
)
_SUBSCRIPTS = str.maketrans("\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089", "0123456789")
_MINUS = "\u2212\u2013\u2010"  # unicode minus, en dash, hyphen
# Candidate token: element-like symbols with optional counts/parentheses/charge.
_FORMULA_CANDIDATE = re.compile(r"^(?:\(?[A-Z][a-z]?\d*\)?\d*){2,}[+\-]?\d*$")
_SYMBOL_IN_FORMULA = re.compile(r"[A-Z][a-z]?")
_ISOTOPE = re.compile(r"^\d{1,3}[A-Z][a-z]?$")  # 13C, 1H, 15N
_UNIT = re.compile(
    rf"^(?:cm[{_MINUS}-]?\d?|ppm|ppb|mhz|hz|mol(?:/l)?|mmol|kj/mol|kcal/mol|ml|mg|nm|ev|\u00b0c|\u00b0|mol/l|g/mol)$",
    re.IGNORECASE,
)
_CHEM_KEYWORDS = frozenset(
    "nmr ir uv ms hplc gc ph pka ppm mol molar reagent catalyst solvent yield mp bp".split()
)
_SCI_SYMBOLS = frozenset("\u2192\u21cc\u21c4\u2191\u2193\u00b1\u00d7\u00b0\u03b4\u0394\u03bb\u03bd\u03bc\u03c0\u03c3\u03b5\u03b1\u03b2\u03b3\u2212\u207a\u207b\u00b2\u00b3=+/()[]%")

MIN_CHEM_TOKENS = 2        # at least this many chemistry-looking tokens...
SCIENTIFIC_DENSITY = 0.10  # ...making up at least this share of all tokens => "scientific text"
FULL_RELAX_DENSITY = 0.15  # at/above this density the prose checks are fully relaxed
MAX_REPEAT_RUN = 8         # same character this many times in a row is not text
MAX_DOMINANT_CHAR_SHARE = 0.4  # one character making up this much of the page is not text
_CANONICAL = str.maketrans({"\u064A": "\u06CC", "\u0649": "\u06CC", "\u0643": "\u06A9"})
_MARKS = re.compile("[\u064B-\u065F\u0670\u0640]")

MIN_TEXT_CHARS = 20
MAX_PLAUSIBLE_WORD = 22  # longer letter runs are almost surely words glued together
DEFAULT_MIN_QUALITY = 0.6


@dataclass(frozen=True)
class TextQuality:
    """``score`` is 1.0 for clean text and drops per problem listed in ``reasons``."""

    score: float
    reasons: tuple[str, ...] = ()  # penalties applied (why the score dropped)
    notes: tuple[str, ...] = ()  # informational signals (e.g. chemistry text detected)
    chem_density: float = 0.0  # share of tokens that look like chemistry (0..1)

    def acceptable(self, minimum: float = DEFAULT_MIN_QUALITY) -> bool:
        return self.score >= minimum


def _canonical(text: str) -> str:
    return _MARKS.sub("", unicodedata.normalize("NFKC", text).translate(_CANONICAL))


def _is_arabic_script(char: str) -> bool:
    return "\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f"


def _normalize_token(token: str) -> str:
    return token.strip(".,;:!?\"'").translate(_SUBSCRIPTS)


def _is_formula(token: str) -> bool:
    """CH3CH2CN / C6H5NO2 / NaOH / H2SO4: every symbol is a real element and
    the token has a digit or a lowercase symbol (so plain words such as NO or
    IN written in capitals are not counted)."""
    if len(token) < 2 or not _FORMULA_CANDIDATE.match(token):
        return False
    symbols = _SYMBOL_IN_FORMULA.findall(token)
    if not symbols or any(sym not in _ELEMENTS for sym in symbols):
        return False
    return any(ch.isdigit() for ch in token) or any(len(sym) == 2 for sym in symbols)


def count_chemistry_tokens(text: str) -> tuple[int, int]:
    """(chemistry-looking tokens, all tokens): formulas, isotope labels such as
    ``13C``, units such as ``cm-1`` and keywords such as ``NMR``."""
    tokens = [t for t in (_normalize_token(raw) for raw in text.split()) if t]
    hits = 0
    for token in tokens:
        if (
            _is_formula(token)
            or _ISOTOPE.match(token) and token.lstrip("0123456789") in _ELEMENTS
            or _UNIT.match(token)
            or token.lower() in _CHEM_KEYWORDS
        ):
            hits += 1
    return hits, len(tokens)


def chemistry_density(text: str) -> float:
    hits, total = count_chemistry_tokens(text)
    return hits / total if total else 0.0


def _has_repeated_garbage(visible: list[str]) -> bool:
    """A long run of one character (``||||||||``, ``.........``) or one character
    dominating the page: typical OCR failure on lines, borders and noise."""
    text = "".join(visible)
    if re.search(r"(.)\1{%d,}" % (MAX_REPEAT_RUN - 1), text):
        return True
    if len(text) >= 30:
        top = max(text.count(c) for c in set(text))
        return top / len(text) > MAX_DOMINANT_CHAR_SHARE
    return False


def assess_text_quality(text: str) -> TextQuality:
    """Score how much ``text`` looks like real Persian/English prose OR scientific
    (chemistry) text (0 to 1). Every deduction is named in ``reasons``."""
    text = _canonical(text)
    visible = [c for c in text if not c.isspace()]
    if not visible:
        return TextQuality(0.0, ("empty",))

    penalty = 0.0
    reasons: list[str] = []
    notes: list[str] = []

    density = chemistry_density(text)
    hits, _ = count_chemistry_tokens(text)
    scientific = hits >= MIN_CHEM_TOKENS and density >= SCIENTIFIC_DENSITY
    # 0 = plain prose (full prose checks) ... 1 = clearly chemistry (prose checks off)
    relax = min(1.0, density / FULL_RELAX_DENSITY) if scientific else 0.0
    if scientific:
        notes.append(f"chemistry_text(density={density:.2f})")

    garbage = sum(
        1 for c in visible if c == "\ufffd" or unicodedata.category(c) in ("Cc", "Cs", "Co")
    )
    if garbage / len(visible) > 0.01:
        penalty += min(0.7, 15 * garbage / len(visible))
        reasons.append("garbage_characters")

    if _has_repeated_garbage(visible):
        penalty += 0.5
        reasons.append("repeated_characters")

    letters = [c for c in visible if c.isalpha()]
    letter_ratio = len(letters) / len(visible)
    if scientific:
        # Digits, units and scientific symbols are legitimate content in chemistry
        # text; judge the share of *meaningful* characters instead of letters only.
        meaningful = sum(1 for c in visible if c.isalnum() or c in _SCI_SYMBOLS)
        content_ratio = meaningful / len(visible)
        if content_ratio < 0.5:
            penalty += min(0.5, 0.5 - content_ratio)
            reasons.append("few_letters")
        elif letter_ratio < 0.5:
            notes.append("few_letters_waived(numeric/scientific content)")
    elif letter_ratio < 0.5:
        penalty += min(0.5, 0.5 - letter_ratio)
        reasons.append("few_letters")

    words = _WORD.findall(text)

    # Words glued together (OCR that dropped the spaces): implausibly long letter runs.
    if words:
        long_letters = sum(len(w) for w in words if len(w) > MAX_PLAUSIBLE_WORD)
        if long_letters / sum(len(w) for w in words) > 0.25:
            penalty += 0.5
            reasons.append("missing_spaces")

    if len(words) >= 15 and letters:
        if sum(map(len, words)) / len(words) < 2.0:
            penalty += 0.5
            reasons.append("fragmented_words")

        arabic = sum(1 for c in letters if _is_arabic_script(c))
        latin = sum(1 for c in letters if c.isascii())

        if arabic >= 0.6 * len(letters):
            hits_fa = sum(1 for w in words if w in _FA_COMMON)
            reversed_hits = sum(1 for w in words if w[::-1] in _FA_COMMON)
            if reversed_hits >= 3 and reversed_hits > 2 * hits_fa:
                penalty += 0.6
                reasons.append("reversed_text")
            elif len(words) >= 30 and hits_fa / len(words) < 0.03:
                penalty += _no_common_words_penalty(relax, notes, reasons)
        elif latin >= 0.6 * len(letters) and len(words) >= 30:
            if sum(1 for w in words if w.lower() in _EN_COMMON) / len(words) < 0.03:
                penalty += _no_common_words_penalty(relax, notes, reasons)

    return TextQuality(
        max(0.0, round(1.0 - penalty, 3)), tuple(reasons), tuple(notes), round(density, 3)
    )


def _no_common_words_penalty(relax: float, notes: list[str], reasons: list[str]) -> float:
    """0.35 for prose with no common words; scaled down for chemistry-heavy text
    (a page of formulas and spectra legitimately has few dictionary words)."""
    penalty = 0.35 * (1.0 - relax)
    if relax >= 1.0:
        notes.append("no_common_words_waived(chemistry text)")
    else:
        reasons.append("no_common_words")
        if relax > 0:
            notes.append(f"no_common_words_reduced(x{1.0 - relax:.2f})")
    return penalty


def latin_letter_ratio(text: str) -> float:
    """Share of letters that are plain Latin (1.0 for English, ~0 for Persian)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isascii()) / len(letters)


def has_text_layer(
    text: str, min_chars: int = MIN_TEXT_CHARS, min_quality: float = DEFAULT_MIN_QUALITY
) -> tuple[bool, TextQuality]:
    """Is the PDF page's own text usable, so OCR can be skipped?"""
    quality = assess_text_quality(text)
    enough = sum(1 for c in text if c.isalnum()) >= min_chars
    return enough and quality.acceptable(min_quality), quality


def is_blank_image(image, threshold: float = 3.0) -> bool:
    """True for an (almost) uniform page: nothing to read, so skip OCR."""
    from PIL import ImageStat

    gray = image.convert("L")
    gray.thumbnail((256, 256))
    return ImageStat.Stat(gray).stddev[0] < threshold
