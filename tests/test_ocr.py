from unittest.mock import MagicMock, patch

from rag.schemas import OCRResult
from src.loaders.ocr import ocr_pdf_page


@patch("src.loaders.ocr.GeminiProvider")
@patch("src.loaders.ocr.convert_from_path")
def test_ocr_pdf_page_returns_text(mock_convert, mock_provider_cls):
    mock_convert.return_value = [MagicMock()]
    mock_provider_cls.return_value.extract_image.return_value = OCRResult(text="متن تست فارسی")

    result = ocr_pdf_page(file="fake.pdf", page_number=0)

    assert result == "متن تست فارسی"
    mock_convert.assert_called_once_with(
        "fake.pdf", first_page=1, last_page=1, dpi=300, poppler_path=None
    )


@patch("src.loaders.ocr.convert_from_path")
def test_ocr_pdf_page_no_images_returns_empty(mock_convert):
    mock_convert.return_value = []
    result = ocr_pdf_page("fake.pdf", page_number=0)
    assert result == ""


@patch("src.loaders.ocr.time.sleep")  # skip real backoff delay in tests
@patch("src.loaders.ocr.GeminiProvider")
@patch("src.loaders.ocr.convert_from_path")
def test_ocr_pdf_page_gemini_failure_returns_empty_not_raise(
    mock_convert, mock_provider_cls, mock_sleep
):
    mock_convert.return_value = [MagicMock()]
    mock_provider_cls.return_value.extract_image.side_effect = Exception("503 UNAVAILABLE")

    result = ocr_pdf_page("fake.pdf", page_number=0)

    assert result == ""
