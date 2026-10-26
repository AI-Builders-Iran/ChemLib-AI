"""Detect table/formula/figure regions on a page image.

Same shape as ``src.ocr.engines``: an ABC with ``unavailable_reason()`` /
``available()``, one implementation per backend, selection by an env var.
A segmenter never replaces the flat-text pipeline in ``src.loaders.pdf_loader``
— it only adds extra, more structured blocks *on top of* the page's plain
text for the regions it recognizes as a table, formula or figure.

``LAYOUT_ENGINE`` selects the segmenter (default ``ppstructure`` — table,
formula and figure regions are pulled out as their own citable blocks via
PaddleOCR's PP-StructureV3; falls back to ``none``, today's flat-text-only
behaviour, if paddleocr/paddlepaddle are not installed — see ``README.md``).
Override with ``LAYOUT_ENGINE=none`` in your ``.env`` to go back to flat text.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from .blocks import BLOCK_FIGURE, BLOCK_FORMULA, BLOCK_TABLE, Block
from .figures import describe_figure, figure_processing_enabled

logger = logging.getLogger(__name__)

DEFAULT_LAYOUT_ENGINE = "ppstructure"
LAYOUT_ENGINES = ("none", "ppstructure")

# Labels PP-StructureV3 (and PaddleX layout models in general) use for regions
# we want as their own block; text/title/list/etc. regions are left alone —
# they are already covered by the page's flat OCR/text-layer text.
_TABLE_LABELS = {"table"}
_FORMULA_LABELS = {"formula", "equation", "formula_number"}
_FIGURE_LABELS = {"image", "figure", "chart", "figure_title", "seal"}


class LayoutSegmenter(ABC):
    name: str

    @abstractmethod
    def unavailable_reason(self) -> str | None:
        """None when ready to use; otherwise why not (not installed / not configured)."""

    @abstractmethod
    def segment(self, image, *, figure_dir: Path | None = None) -> list[Block]:
        """Return the table/formula/figure blocks found on ``image``.

        ``figure_dir``: where to save cropped figure images, if any are
        found. May raise; callers should treat a raising segmenter the same
        as ``NullLayoutSegmenter`` (skip structured blocks for that page).
        """

    def available(self) -> bool:
        return self.unavailable_reason() is None


class NullLayoutSegmenter(LayoutSegmenter):
    """Finds nothing. Reproduces today's flat-text-only behaviour exactly."""

    name = "none"

    def unavailable_reason(self) -> str | None:
        return None

    def segment(self, image, *, figure_dir: Path | None = None) -> list[Block]:
        return []


class PPStructureSegmenter(LayoutSegmenter):
    """Layout + table + formula recognition via PaddleOCR's PP-StructureV3.

    Heavy, opt-in dependency (see the commented-out block in
    requirements.txt) — not installed by default. The exact shape of
    ``PPStructureV3().predict(...)`` output has changed across paddleocr
    releases; ``_iter_blocks`` is deliberately defensive (several label/key
    spellings accepted) and any single malformed region is skipped with a
    warning rather than failing the whole page.

    oneDNN (MKL-DNN) is disabled by default: recent paddlepaddle/paddlex CPU
    builds raise ``NotImplementedError: ConvertPirAttribute2RuntimeAttribute
    ... pir::ArrayAttribute<pir::DoubleAttribute>`` from the oneDNN PIR
    executor on some layout-detection ops (seen on Windows CPU installs).
    Set ``PADDLE_ENABLE_MKLDNN=true`` to re-enable it if your install doesn't
    hit that bug (it's faster). ``PADDLE_DEVICE`` (e.g. ``gpu``) is passed
    through as-is if set.
    """

    name = "ppstructure"

    def __init__(self, lang: str | None = None, pipeline=None, caption_provider=None):
        self._lang = lang or os.getenv("PADDLE_OCR_LANG") or "fa"
        self._pipeline = pipeline  # injectable for tests
        self._caption_provider = caption_provider  # passed through to describe_figure
        # PP-StructureV3 is loaded once per process (see build_default_segmenter) and shared by
        # every upload; one prediction at a time keeps GPU memory predictable and avoids
        # relying on the model being thread-safe.
        self._lock = threading.Lock()
        self.last_figures_skipped = 0  # figure regions skipped by the most recent segment() call

    def unavailable_reason(self) -> str | None:
        if self._pipeline is not None:
            return None
        if importlib.util.find_spec("paddleocr") is None or importlib.util.find_spec("paddle") is None:
            return "paddleocr / paddlepaddle are not installed"
        return None

    def _get_pipeline(self):
        if self._pipeline is None:
            from src.utils.paddle_env import set_paddle_env_flags

            set_paddle_env_flags()

            from paddleocr import PPStructureV3

            logger.info("Layout: initializing PP-StructureV3 (first use in this process)...")
            started = time.monotonic()

            kwargs = {"lang": self._lang}
            device = os.getenv("PADDLE_DEVICE")
            if device:
                kwargs["device"] = device
            enable_mkldnn = (os.getenv("PADDLE_ENABLE_MKLDNN") or "false").strip().lower() in ("1", "true", "yes")
            kwargs["enable_mkldnn"] = enable_mkldnn
            try:
                self._pipeline = PPStructureV3(**kwargs)
            except TypeError:
                # Older/newer paddleocr releases may not accept these kwargs at all.
                logger.info("PPStructureV3 doesn't accept device/enable_mkldnn kwargs on this install; using defaults")
                self._pipeline = PPStructureV3(lang=self._lang)
            logger.info("Layout: PP-StructureV3 initialized in %.2fs", time.monotonic() - started)
        return self._pipeline

    def segment(self, image, *, figure_dir: Path | None = None) -> list[Block]:
        import numpy as np

        self.last_figures_skipped = 0
        array = np.array(image.convert("RGB"))
        with self._lock:
            results = self._get_pipeline().predict(array)

        blocks: list[Block] = []
        for page_result in results or []:  # predict() may return None on a failed page
            for region in self._iter_regions(page_result):
                block = self._to_block(region, image, figure_dir)
                if block is not None:
                    blocks.append(block)
        return blocks

    @staticmethod
    def _iter_regions(page_result):
        """``parsing_res_list`` (or the closest equivalent) from one page result."""
        data = page_result
        for attr in ("json", "res"):
            candidate = getattr(data, attr, None)
            if candidate is not None:
                data = candidate
                break
        if isinstance(data, dict):
            data = data.get("res", data)
            data = data.get("parsing_res_list") or data.get("layout_parsing_result") or []
        return data if isinstance(data, (list, tuple)) else []

    def _to_block(self, region: dict, page_image, figure_dir: Path | None) -> Block | None:
        try:
            label = str(
                region.get("block_label") or region.get("label") or region.get("type") or ""
            ).lower()
            content = region.get("block_content") or region.get("content") or ""
            bbox = region.get("block_bbox") or region.get("bbox") or region.get("coordinate")
            bbox = tuple(float(v) for v in bbox) if bbox else None
            score = region.get("score") or region.get("confidence")

            if label in _TABLE_LABELS:
                if not content:
                    return None
                return Block(BLOCK_TABLE, content, bbox=bbox, confidence=score)

            if label in _FORMULA_LABELS:
                if not content:
                    return None
                latex = content if content.strip().startswith("$") else f"$$\n{content.strip()}\n$$"
                return Block(BLOCK_FORMULA, latex, bbox=bbox, confidence=score)

            if label in _FIGURE_LABELS:
                if not figure_processing_enabled():
                    # MVP: figures are not cropped, captioned or sent to any LLM/VLM.
                    # To add production figure handling, implement it behind this flag
                    # (see src/layout/figures.py).
                    self.last_figures_skipped += 1
                    logger.info("Figure region (%s) detected; skipping visual element (MVP mode)", label)
                    return None
                image_path = None
                if bbox is not None:
                    image_path = self._save_crop(page_image, bbox, figure_dir)
                crop = page_image.crop(bbox) if bbox is not None else page_image
                caption = describe_figure(crop, provider=self._caption_provider)
                text = caption or (content if isinstance(content, str) and not content.startswith("<") else "")
                if not text:
                    text = "(figure — no caption available)"
                return Block(BLOCK_FIGURE, text, bbox=bbox, confidence=score, image_path=image_path)

            return None  # text/title/list/etc.: left to the flat-text pipeline
        except Exception as exc:  # noqa: BLE001 - one bad region must not lose the page
            logger.warning("Skipping unparsable layout region: %s", exc)
            return None

    @staticmethod
    def _save_crop(page_image, bbox: tuple[float, float, float, float], figure_dir: Path | None) -> str | None:
        if figure_dir is None:
            return None
        figure_dir.mkdir(parents=True, exist_ok=True)
        path = figure_dir / f"figure_{uuid.uuid4().hex[:8]}.png"
        page_image.crop(bbox).save(path)
        return str(path)


_SEGMENTER_CLASSES: dict[str, type[LayoutSegmenter]] = {
    "none": NullLayoutSegmenter,
    "ppstructure": PPStructureSegmenter,
}


_SEGMENTER_CACHE: dict[str, LayoutSegmenter] = {}
_SEGMENTER_CACHE_LOCK = threading.Lock()


def build_default_segmenter(name: str | None = None) -> LayoutSegmenter:
    """The configured segmenter (``LAYOUT_ENGINE`` env var, default ``ppstructure``).

    One instance per engine name is kept for the whole process: PP-StructureV3
    loads several GPU models, and every uploaded PDF used to build (and load) a
    new one.

    Falls back to ``NullLayoutSegmenter`` (with a logged reason) if the
    requested one is unknown or unavailable, so a missing optional dependency
    never breaks ingestion - it just means pages are indexed as flat text
    only, same as before this feature existed.
    """
    name = (name or os.getenv("LAYOUT_ENGINE") or DEFAULT_LAYOUT_ENGINE).strip().lower()
    cls = _SEGMENTER_CLASSES.get(name)
    if cls is None:
        logger.warning("Unknown LAYOUT_ENGINE '%s'; falling back to 'none'", name)
        return NullLayoutSegmenter()

    with _SEGMENTER_CACHE_LOCK:
        cached = _SEGMENTER_CACHE.get(name)
        if cached is not None:
            return cached
        segmenter = cls()
        reason = segmenter.unavailable_reason()
        if reason:
            logger.info("Layout engine '%s' unavailable (%s); falling back to 'none'", name, reason)
            return NullLayoutSegmenter()
        _SEGMENTER_CACHE[name] = segmenter
        return segmenter
