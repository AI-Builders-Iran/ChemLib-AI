from pathlib import Path

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path


# ============================================================
# Configuration
# ============================================================

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

POPPLER_PATH = (
    r"C:\Users\hosse\Downloads\Release-24.08.0-0"
    r"\poppler-24.08.0\Library\bin"
)

PDF_PATH = r"C:\Users\hosse\Downloads\test2.pdf"

LANGUAGE = "fas+eng"
DPI = 300

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


# ============================================================
# Image Preprocessing
# ============================================================

def preprocess_image(image):
    """
    Convert PIL image to grayscale and apply basic preprocessing.
    """

    # PIL -> NumPy
    img = np.array(image)

    # RGB -> Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Denoising
    gray = cv2.fastNlMeansDenoising(
        gray,
        None,
        h=10,
        templateWindowSize=7,
        searchWindowSize=21,
    )

    # Contrast normalization
    gray = cv2.normalize(
        gray,
        None,
        0,
        255,
        cv2.NORM_MINMAX,
    )

    return gray


# ============================================================
# Load PDF Page
# ============================================================

def load_pdf_page(
    file: Path | str,
    page_number: int,
    dpi: int = 300,
):
    """
    Render one PDF page.

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
        raise ValueError(
            f"Could not render page {page_number}"
        )

    return images[0]


# ============================================================
# OCR Test
# ============================================================

def test_psm(
    image,
    language: str = LANGUAGE,
):
    """
    Run OCR with different PSM configurations.
    """

    # Preprocess image
    processed = preprocess_image(image)

    # Different Page Segmentation Modes
    configs = {
        "psm_3": "--oem 3 --psm 3",
        "psm_4": "--oem 3 --psm 4",
        "psm_6": "--oem 3 --psm 6",
    }

    # Run each configuration
    for name, config in configs.items():

        text = pytesseract.image_to_string(
            processed,
            lang=language,
            config=config,
        )

        print("\n" + "=" * 60)
        print(name)
        print("=" * 60)

        print(text)


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    # Test page 0
    page_number = 0

    print("=" * 60)
    print(f"Loading PDF page {page_number}")
    print("=" * 60)

    image = load_pdf_page(
        file=PDF_PATH,
        page_number=page_number,
        dpi=DPI,
    )

    print("Page loaded successfully.")
    print(f"Image size: {image.size}")

    # Run OCR tests
    test_psm(
        image=image,
        language=LANGUAGE,
    )