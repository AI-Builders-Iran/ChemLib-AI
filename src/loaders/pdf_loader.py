import logging
import os
import time
from collections import Counter
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document

from src.layout.blocks import BLOCK_TEXT
from src.layout.figures import figure_processing_enabled
from src.layout.engines import LayoutSegmenter, NullLayoutSegmenter, build_default_segmenter
from src.ocr.page_type import FIGURE as PAGE_FIGURE
from src.ocr.page_type import classify_page
from src.ocr.pipeline import OCRPipeline, build_default_pipeline
from src.ocr.quality import MIN_TEXT_CHARS, has_text_layer, is_blank_image

from .base import BaseLoader
from .pdf_pages import open_pdf

logger = logging.getLogger(__name__)

DEFAULT_FIGURE_DIR = "vector_database/figures"

# (stage, current page 1-based, total pages); stage is "reading" or "ocr".
PageProgress = Callable[[str, int, int], None]


@dataclass
class PDFLoadReport:
    """How each page of the last loaded PDF was read (for logs and the admin UI)."""

    total_pages: int = 0
    text_layer_pages: int = 0
    blank_pages: int = 0
    ocr_pages: Counter = field(default_factory=Counter)  # engine name -> pages
    low_quality_pages: list[int] = field(default_factory=list)  # 1-based page numbers
    failed_pages: list[int] = field(default_factory=list)  # 1-based page numbers
    # Pages intentionally NOT sent to OCR because they look like a figure/
    # diagram/chemical structure with no table grid (see src.ocr.page_type).
    skipped_figure_pages: list[int] = field(default_factory=list)  # 1-based page numbers
    structured_blocks: Counter = field(default_factory=Counter)  # block_type -> count (table/formula/figure)
    # Figure regions the layout engine found and the MVP deliberately skipped (no LLM/VLM call).
    skipped_figure_regions: int = 0
    # Pages whose processing raised: the page is kept as empty text and the rest of the PDF goes on.
    errored_pages: list[int] = field(default_factory=list)  # 1-based page numbers
    # Measured seconds per stage: render / ocr / layout / text_layer (only what actually ran).
    timings: dict[str, float] = field(default_factory=dict)

    def add_time(self, stage: str, seconds: float) -> None:
        self.timings[stage] = self.timings.get(stage, 0.0) + seconds

    def timing_summary(self) -> str:
        total = sum(self.timings.values())
        if total <= 0:
            return "no timings"
        return ", ".join(
            f"{stage} {seconds:.1f}s ({100 * seconds / total:.0f}%)"
            for stage, seconds in sorted(self.timings.items(), key=lambda kv: -kv[1])
        )

    def summary(self) -> str:
        ocr = ", ".join(f"{name}={count}" for name, count in sorted(self.ocr_pages.items())) or "none"
        blocks = ", ".join(f"{name}={count}" for name, count in sorted(self.structured_blocks.items())) or "none"
        return (
            f"{self.total_pages} pages: text layer={self.text_layer_pages}, OCR={ocr}, "
            f"blank={self.blank_pages}, low quality={len(self.low_quality_pages)}, "
            f"failed={len(self.failed_pages)}, errored={len(self.errored_pages)}, "
            f"skipped figure pages={len(self.skipped_figure_pages)}, "
            f"skipped figure regions={self.skipped_figure_regions}, structured blocks={blocks}"
        )


class PDFLoader(BaseLoader):
    """Reads a PDF page by page, OCR-ing only the pages that need it.

    1. Use the page's text layer when it exists and looks like real text.
    2. Otherwise (scan, or a garbage/reversed text layer) render the page.
       If it isn't blank, run a cheap heuristic (``src.ocr.page_type``) to
       tell whether the page is mostly a figure/diagram/chemical structure
       with no table grid — such pages are skipped (no OCR call), which is
       recorded in ``PDFLoadReport.skipped_figure_pages`` and the page's
       ``extraction`` metadata (``"skipped:figure"``). A page with a table
       grid, or plain text, still goes through the OCR pipeline below.
    3. Run the OCR pipeline: blank check, engines in priority order, quality
       gate, fallback. The pipeline is built only when a page first needs it,
       so text-only PDFs never touch an OCR engine or an API key.
    4. Optionally (``layout_engine`` / ``LAYOUT_ENGINE`` env var), also run a
       layout segmenter over the page image to pull out tables, formulas and
       figures as their own, separately-citable blocks — see
       ``src.layout.engines``. This is additive: the flat per-page text above
       is produced exactly as before either way, so turning it off (the
       default) reproduces today's behaviour exactly.
    """

    def __init__(
        self,
        pipeline: OCRPipeline | None = None,
        source_factory=open_pdf,
        min_text_chars: int = MIN_TEXT_CHARS,
        ocr_mode: str | None = None,
        layout_engine: str | LayoutSegmenter | None = None,
        figure_dir: str | Path | None = None,
    ):
        """``ocr_mode``: "online_first" or "local_only" (default: OCR_MODE, then online_first).
        ``layout_engine``: a ``LayoutSegmenter`` instance, an engine name ("none" /
        "ppstructure"), or None (default: ``LAYOUT_ENGINE`` env var, then "none").
        """
        self._ocr_mode = ocr_mode
        self._pipeline = pipeline
        self._source_factory = source_factory
        self._min_text_chars = min_text_chars
        self._segmenter = layout_engine if isinstance(layout_engine, LayoutSegmenter) else None
        self._layout_engine_name = None if isinstance(layout_engine, LayoutSegmenter) else layout_engine
        self._figure_dir = Path(figure_dir or os.getenv("FIGURE_DIR") or DEFAULT_FIGURE_DIR)
        self.last_report = PDFLoadReport()

    def _get_pipeline(self) -> OCRPipeline:
        if self._pipeline is None:
            self._pipeline = build_default_pipeline(self._ocr_mode)
            logger.info("OCR engines (%s): %s", self._ocr_mode or "default", ", ".join(self._pipeline.engine_names) or "none available")
        return self._pipeline

    def _get_segmenter(self) -> LayoutSegmenter:
        if self._segmenter is None:
            self._segmenter = build_default_segmenter(self._layout_engine_name)
            logger.info("Layout engine: %s", self._segmenter.name)
        return self._segmenter

    def load(self, file: Path | str, on_progress: PageProgress | None = None) -> list[Document]:
        """Read every page. One bad page never fails the PDF (it becomes an empty
        page, recorded in ``last_report``); only an unreadable file raises."""
        report = self.last_report = PDFLoadReport()
        documents: list[Document] = []
        segmenter = self._get_segmenter()
        segment_pages = not isinstance(segmenter, NullLayoutSegmenter)
        name = Path(file).name

        with self._source_factory(file) as source:
            report.total_pages = source.page_count

            for index in range(source.page_count):
                page_no = index + 1
                self._notify(on_progress, "reading", page_no, report.total_pages)
                try:
                    page_documents = self._load_page(
                        source, index, file, report, segmenter, segment_pages, on_progress
                    )
                except Exception as exc:  # noqa: BLE001 - isolate the failure to this page
                    logger.error(
                        "PDF ingestion: page failed file=%s page=%d stage=page reason=%s: %s "
                        "(continuing with the next page)", name, page_no, type(exc).__name__, exc,
                        exc_info=True,
                    )
                    report.errored_pages.append(page_no)
                    page_documents = [self._page_document("", file, index, "error:page", 0.0)]
                documents.extend(page_documents)

        logger.info("Loaded %s: %s", name, report.summary())
        logger.info("Timing for %s: %s", name, report.timing_summary())
        return documents

    @staticmethod
    def _notify(on_progress: PageProgress | None, stage: str, page_no: int, total: int) -> None:
        if on_progress is None:
            return
        try:
            on_progress(stage, page_no, total)
        except Exception:  # noqa: BLE001 - a UI callback must never break ingestion
            logger.warning("Progress callback failed (ignored)", exc_info=True)

    @staticmethod
    @contextmanager
    def _timed(report: PDFLoadReport, stage: str):
        started = time.monotonic()
        try:
            yield
        finally:
            report.add_time(stage, time.monotonic() - started)

    @staticmethod
    def _page_document(text: str, file, index: int, method: str, score: float) -> Document:
        return Document(
            page_content=text,
            metadata={
                "source": str(file),
                "page": index,
                "extraction": method,
                "text_quality": round(score, 2),
                "block_type": BLOCK_TEXT,
            },
        )

    def _load_page(
        self, source, index: int, file, report: PDFLoadReport, segmenter: LayoutSegmenter,
        segment_pages: bool, on_progress: PageProgress | None,
    ) -> list[Document]:
        """Documents for one page. The rendered page image is created at most once
        and dropped when the page is done, so only one page image is in memory at a time."""
        page_no = index + 1
        image = None  # rendered lazily, shared by the figure check, OCR and layout
        figure_page = False

        with self._timed(report, "text_layer"):
            text = (source.text(index) or "").strip()
        usable, quality = has_text_layer(text, self._min_text_chars)

        try:
            if usable:
                report.text_layer_pages += 1
                method, score = "text_layer", quality.score
            else:
                with self._timed(report, "render"):
                    image = source.image(index)
                if is_blank_image(image):
                    # Let the OCR pipeline's own (cheaper) blank-page path
                    # handle it, so blank-page reporting stays unchanged.
                    text, method, score = self._ocr_page(source, index, text, report, image, on_progress)
                elif classify_page(image) == PAGE_FIGURE:
                    # Mostly a figure/diagram/chemical structure, no table
                    # grid: skip OCR for this MVP (see src.ocr.page_type).
                    figure_page = True
                    report.skipped_figure_pages.append(page_no)
                    logger.info(
                        "Page %d: classified as a figure/diagram (no table); OCR skipped (MVP mode)", page_no
                    )
                    text, method, score = "", "skipped:figure", 0.0
                else:
                    text, method, score = self._ocr_page(source, index, text, report, image, on_progress)

            documents = [self._page_document(text, file, index, method, score)]

            # A page that is just a figure has nothing the layout engine could add while figures are
            # skipped, so don't spend GPU time on it.
            if segment_pages and not (figure_page and not figure_processing_enabled()):
                if image is None:
                    with self._timed(report, "render"):
                        image = source.image(index)
                documents.extend(self._segment_page(image, index, file, segmenter, report))
            return documents
        finally:
            del image  # release the page bitmap before the next page is rendered

    def _ocr_page(
        self, source, index: int, layer_text: str, report: PDFLoadReport, image=None,
        on_progress: PageProgress | None = None,
    ) -> tuple[str, str, float]:
        page_no = index + 1
        self._notify(on_progress, "ocr", page_no, report.total_pages)
        try:
            if image is None:
                with self._timed(report, "render"):
                    image = source.image(index)
            with self._timed(report, "ocr"):
                result = self._get_pipeline().recognize(image)
        except Exception as exc:  # noqa: BLE001 - rendering or engine set-up failed
            logger.error(
                "PDF ingestion: OCR failed page=%d stage=ocr reason=%s: %s", page_no, type(exc).__name__, exc,
                exc_info=True,
            )
            report.failed_pages.append(page_no)
            return layer_text, "text_layer_unverified" if layer_text else "none", 0.0

        if result.engine == "blank":
            report.blank_pages += 1
            return "", "blank", 1.0

        if result.failed:
            report.failed_pages.append(page_no)
            logger.warning("Page %d: no OCR engine produced text", page_no)
            # A doubtful text layer is still better than losing the page entirely.
            return layer_text, "text_layer_unverified" if layer_text else "none", 0.0

        report.ocr_pages[result.engine] += 1
        if result.low_quality:
            report.low_quality_pages.append(page_no)
            logger.warning("Page %d: OCR quality is low (best engine: %s)", page_no, result.engine)
        return result.text.strip(), f"ocr:{result.engine}", result.quality

    def _segment_page(self, image, index: int, file, segmenter: LayoutSegmenter, report: PDFLoadReport) -> list[Document]:
        """Table/formula/figure blocks for one page, as their own Documents. Never raises."""
        try:
            with self._timed(report, "layout"):
                blocks = segmenter.segment(image, figure_dir=self._figure_dir) or []
            report.skipped_figure_regions += int(getattr(segmenter, "last_figures_skipped", 0) or 0)
        except Exception as exc:  # noqa: BLE001 - a layout failure must not lose the page's plain text
            logger.warning(
                "Layout failed page=%d stage=layout reason=%s: %s; keeping the page's plain text",
                index + 1, type(exc).__name__, exc, exc_info=True,
            )
            return []

        documents = []
        for block in blocks:
            if not block.content.strip():
                continue
            report.structured_blocks[block.block_type] += 1
            metadata = {
                "source": str(file),
                "page": index,
                "extraction": f"layout:{segmenter.name}",
                "block_type": block.block_type,
                "bbox": list(block.bbox) if block.bbox else None,
            }
            if block.image_path:
                metadata["image_path"] = block.image_path
            documents.append(Document(page_content=block.content, metadata=metadata))
        return documents
