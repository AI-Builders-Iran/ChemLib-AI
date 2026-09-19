# src/loaders/ocr.py
import logging
import os
import time
from pathlib import Path

from pdf2image import convert_from_path

from rag.schemas import OCRResult
from src.extraction.providers.gemini_provider import GeminiProvider

logger = logging.getLogger(__name__)

POPPLER_PATH = os.getenv("POPPLER_PATH")

OCR_PROMPT = (
    "Transcribe all text visible in this image exactly as written. "
    "The text may be in Persian (Farsi) and/or English, or a mix of both. "
    "Preserve line breaks where meaningful. Do not translate, summarize, "
    "or add any commentary — output only the transcribed text."
)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


def ocr_pdf_page(file: Path | str, page_number: int) -> str:
    """Rasterize one PDF page (0-indexed) and OCR it via Gemini Vision."""
    try:
        images = convert_from_path(
            str(file),
            first_page=page_number + 1,
            last_page=page_number + 1,
            dpi=300,
            poppler_path=POPPLER_PATH,
        )
    except Exception as e:
        logger.error(f"PDF rasterization failed for {file} page {page_number}: {e}")
        return ""

    if not images:
        return ""

    provider = GeminiProvider()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = provider.extract_image(image=images[0], schema=OCRResult, prompt=OCR_PROMPT)
            return result.text.strip()
        except Exception as e:
            is_last_attempt = attempt == MAX_RETRIES
            logger.warning(
                f"Gemini OCR attempt {attempt}/{MAX_RETRIES} failed for "
                f"{file} page {page_number}: {e}"
            )
            if is_last_attempt:
                logger.error(f"Gemini OCR permanently failed for {file} page {page_number}: {e}")
                return ""
            time.sleep(RETRY_DELAY_SECONDS * attempt)  # backoff: 5s, 10s

    return ""
