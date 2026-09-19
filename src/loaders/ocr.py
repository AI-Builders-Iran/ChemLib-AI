from pathlib import Path

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = (
    r"C:\Users\hosse\Downloads\Release-24.08.0-0"
    r"\poppler-24.08.0\Library\bin"
)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

DEFAULT_LANGUAGE = "fas+eng"


def preprocess_image(image):
    """
    Basic preprocessing for scanned document OCR.
    """

    # PIL -> OpenCV
    img = np.array(image)

    # RGB -> grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Light denoising
    gray = cv2.fastNlMeansDenoising(
        gray,
        None,
        h=10,
        templateWindowSize=7,
        searchWindowSize=21,
    )

    # Improve contrast
    gray = cv2.normalize(
        gray,
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    )

    return gray


def ocr_pdf_page(
        file: Path | str,
        page_number: int,
        language: str = DEFAULT_LANGUAGE,
        dpi: int = 300,
):
    """
    OCR one PDF page.

    page_number is 0-indexed.
    """

    images = convert_from_path(
        str(file),
        first_page=page_number + 1,
        last_page=page_number + 1,
        dpi=dpi,
        poppler_path=POPPLER_PATH,
    )

    if not images:
        return ""

    image = images[0]

    processed = preprocess_image(image)

    text = pytesseract.image_to_string(
        processed,
        lang=language,
        config="--oem 3 --psm 6",
    )

    return text.strip()
