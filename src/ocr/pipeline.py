"""Run OCR engines in priority order and keep the first result that passes quality checks."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field

from .engines import OCREngine, build_default_engines
from .quality import assess_text_quality, is_blank_image, latin_letter_ratio

logger = logging.getLogger(__name__)

# Stricter than the text-layer check (0.6): a text layer that merely looks unusual is
# still real text, but OCR output with no common words at all is almost surely junk.
DEFAULT_MIN_QUALITY = 0.6
DEFAULT_MIN_CONFIDENCE = 0.65
MIN_LATIN_RATIO = 0.85  # an English-only engine must return mostly Latin letters

# online_first: cloud engines, then local ones as the fallback.
# local_only: local engines only; no page image leaves the machine.
OCR_MODES = ("online_first", "local_only")
DEFAULT_OCR_MODE = "online_first"


@dataclass
class Attempt:
    engine: str
    quality: float = 0.0
    confidence: float | None = None
    accepted: bool = False
    error: str = ""
    seconds: float = 0.0  # engine inference time
    reasons: tuple[str, ...] = ()  # quality penalties, for logs


@dataclass
class PageOCR:
    text: str
    engine: str  # engine that produced ``text``; "blank" or "none" when there is none
    quality: float
    low_quality: bool = False  # no engine passed the checks; ``text`` is the best of a bad lot
    failed: bool = False  # nothing usable at all (no engine, or every engine errored)
    attempts: list[Attempt] = field(default_factory=list)


def _run_lock(engine: OCREngine) -> threading.Lock:
    """One lock per engine instance. Engine instances are shared by every
    upload (see ``engines.get_engine``), and neither ONNX/RapidOCR wrappers nor
    PaddleOCR are documented as safe for concurrent ``predict`` calls, so
    concurrent uploads take turns on the same engine instead of loading a
    second copy of the model."""
    return engine.__dict__.setdefault("_run_lock", threading.Lock())


class OCRPipeline:
    """Primary engine + fallbacks with a quality gate between them.

    An engine's result is accepted when its text passes ``assess_text_quality``
    and, if the engine reports confidence, the confidence is high enough.
    Otherwise the next engine is tried. When none passes, the best result is
    returned and flagged ``low_quality`` instead of being thrown away.
    """

    def __init__(
        self,
        engines: list[OCREngine],
        min_quality: float = DEFAULT_MIN_QUALITY,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        strict_english_only: bool = True,
    ):
        """
        ``strict_english_only``: results of English-only engines (RapidOCR) that
        fail the checks are dropped instead of kept as "best of a bad lot".
        Otherwise a Persian page whose online OCR failed would end up indexed
        as Latin gibberish. Turn it off when local OCR is all there is.
        """
        self._engines = engines
        self._min_quality = min_quality
        self._min_confidence = min_confidence
        self._strict_english_only = strict_english_only

    @property
    def engine_names(self) -> list[str]:
        return [engine.name for engine in self._engines]

    def recognize(self, image) -> PageOCR:
        if is_blank_image(image):
            return PageOCR(text="", engine="blank", quality=1.0)

        attempts: list[Attempt] = []
        best: tuple[float, str, str] | None = None  # (rank, text, engine)

        for engine in self._engines:
            started = time.monotonic()
            try:
                with _run_lock(engine):
                    output = engine.recognize(image)
            except Exception as exc:  # noqa: BLE001 - fall through to the next engine
                logger.warning(
                    "OCR engine '%s' failed after %.1fs (%s: %s); trying next engine",
                    engine.name, time.monotonic() - started, type(exc).__name__, exc,
                )
                attempts.append(Attempt(engine=engine.name, error=str(exc)))
                continue
            seconds = time.monotonic() - started

            if output is None or output.text is None:  # defensive: a misbehaving engine
                logger.warning("OCR engine '%s' returned no result; trying next engine", engine.name)
                attempts.append(Attempt(engine=engine.name, error="no result", seconds=seconds))
                continue

            quality = assess_text_quality(output.text)
            confident = output.confidence is None or output.confidence >= self._min_confidence
            accepted = quality.acceptable(self._min_quality) and confident
            reject_reasons = list(quality.reasons)
            if not confident:
                reject_reasons.append(f"low_confidence<{self._min_confidence}")
            if accepted and engine.english_only and latin_letter_ratio(output.text) < MIN_LATIN_RATIO:
                accepted = False  # not English text: this engine cannot read the page
                reject_reasons.append("not_latin_text")
            attempts.append(
                Attempt(engine.name, quality.score, output.confidence, accepted, seconds=seconds,
                        reasons=tuple(reject_reasons))
            )

            if accepted:
                logger.info(
                    "OCR engine '%s' accepted (quality %.2f, min %.2f, confidence %s, %.1fs%s)",
                    engine.name, quality.score, self._min_quality, _fmt_conf(output.confidence), seconds,
                    "; " + ", ".join(quality.notes) if quality.notes else "",
                )
                return PageOCR(output.text, engine.name, quality.score, attempts=attempts)

            logger.info(
                "OCR engine '%s' rejected (quality %.2f, min %.2f, confidence %s, %.1fs, reasons: %s%s); trying next",
                engine.name, quality.score, self._min_quality, _fmt_conf(output.confidence), seconds,
                ", ".join(reject_reasons) or "unknown",
                "; " + ", ".join(quality.notes) if quality.notes else "",
            )
            rank = quality.score * (output.confidence if output.confidence is not None else 1.0)
            droppable = engine.english_only and self._strict_english_only
            if output.text.strip() and not droppable and (best is None or rank > best[0]):
                best = (rank, output.text, engine.name)

        if best is not None:
            return PageOCR(best[1], best[2], round(best[0], 3), low_quality=True, attempts=attempts)
        return PageOCR(text="", engine="none", quality=0.0, low_quality=True, failed=True, attempts=attempts)


def _fmt_conf(confidence: float | None) -> str:
    return "n/a" if confidence is None else f"{confidence:.2f}"


def build_default_pipeline(mode: str | None = None) -> OCRPipeline:
    """Pipeline for an OCR mode (``online_first`` or ``local_only``).

    ``mode`` defaults to ``OCR_MODE`` (then ``online_first``). Engines come from
    ``OCR_ENGINES``; thresholds from ``OCR_MIN_QUALITY`` / ``OCR_MIN_CONFIDENCE``.
    """
    mode = mode or os.getenv("OCR_MODE") or DEFAULT_OCR_MODE
    if mode not in OCR_MODES:
        raise ValueError(f"Unknown OCR mode '{mode}'. Use one of: {', '.join(OCR_MODES)}")

    engines = build_default_engines()
    if mode == "local_only":
        engines = [e for e in engines if not e.online]
    else:  # online engines first, local ones as the fallback (order inside each group kept)
        engines = [e for e in engines if e.online] + [e for e in engines if not e.online]

    return OCRPipeline(
        engines,
        min_quality=float(os.getenv("OCR_MIN_QUALITY", DEFAULT_MIN_QUALITY)),
        min_confidence=float(os.getenv("OCR_MIN_CONFIDENCE", DEFAULT_MIN_CONFIDENCE)),
        strict_english_only=(mode != "local_only"),
    )
