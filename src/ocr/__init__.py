"""Multi-stage OCR for scanned PDF pages.

Pipeline: text layer first (no OCR), then only for pages without a usable text
layer: blank-page check -> OCR engines in priority order -> quality gate ->
fall back to the next engine. See ``pipeline.OCRPipeline``.
"""

from .engines import OCREngine, build_default_engines, engine_status
from .page_type import FIGURE, TABLE, TEXT, classify_page
from .pipeline import DEFAULT_OCR_MODE, OCR_MODES, OCRPipeline, PageOCR, build_default_pipeline
from .quality import TextQuality, assess_text_quality, has_text_layer, is_blank_image

__all__ = [
    "DEFAULT_OCR_MODE",
    "FIGURE",
    "OCR_MODES",
    "OCREngine",
    "OCRPipeline",
    "PageOCR",
    "TABLE",
    "TEXT",
    "TextQuality",
    "assess_text_quality",
    "build_default_engines",
    "build_default_pipeline",
    "classify_page",
    "engine_status",
    "has_text_layer",
    "is_blank_image",
]
