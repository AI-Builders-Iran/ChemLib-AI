# tests/test_ocr.py
from unittest.mock import MagicMock, patch

from src.loaders.ocr import ocr_pdf_page


@patch("src.loaders.ocr.pytesseract.image_to_string")
@patch("src.loaders.ocr.convert_from_path")
def test_ocr_pdf_page_returns_text(mock_convert, mock_ocr):
    mock_convert.return_value = [MagicMock()]
    mock_ocr.return_value = "متن تست فارسی"

    result = ocr_pdf_page(
        file="fake.pdf",
        page_number=0)

    assert result == "متن تست فارسی"
    mock_convert.assert_called_once_with(
        "fake.pdf", first_page=1, last_page=1, dpi=300
    )


@patch("src.loaders.ocr.convert_from_path")
def test_ocr_pdf_page_no_images_returns_empty(mock_convert):
    mock_convert.return_value = []
    result = ocr_pdf_page("fake.pdf", page_number=0)
    assert result == ""
