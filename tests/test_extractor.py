from unittest.mock import Mock

import pytest

from src.extraction.extractor import DocumentExtractor
from src.schemas.common import DocumentType
from src.schemas.invoice import Invoice

#--------test that invoice documents use the invoice schema---------
def test_get_schema_for_invoice() -> None:
    provider = Mock()

    extractor = DocumentExtractor(
        providers=[provider]
    )

    schema = extractor._get_schema(DocumentType.INVOICE)

    assert schema is Invoice

#--------test an unsupported document type raises valueerror---------
def test_unsupported_document_type() -> None:
    provider = Mock()

    extractor = DocumentExtractor(
        providers=[provider]
    )

    with pytest.raises(ValueError):
        extractor._get_schema("unsupported")  # type: ignore[arg-type]

#----------test successful provider result is returned----------
def test_extract_uses_provider_result() -> None:
    expected_result = Invoice(
        invoice_number="INV-1024",
        vendor="ABC Company",
        date="2026-08-20",
        total=12500000,
    )

    provider = Mock()
    provider.extract.return_value = expected_result

    extractor = DocumentExtractor(
        providers=[provider]
    )

    result = extractor.extract(
        document_text="Invoice Number: INV-1024",
        document_type=DocumentType.INVOICE,
    )

    assert result == expected_result
    provider.extract.assert_called_once()

#----------testsecond provider is used when the first one fails----------
def test_fallback_to_second_provider() -> None:
    expected_result = Invoice(
        invoice_number="INV-1024",
        vendor="ABC Company",
        date="2026-08-20",
        total=12500000,
    )

    first_provider = Mock()
    first_provider.extract.side_effect = RuntimeError(
        "Primary provider failed"
    )

    second_provider = Mock()
    second_provider.extract.return_value = expected_result

    extractor = DocumentExtractor(
        providers=[
            first_provider,
            second_provider,
        ]
    )

    result = extractor.extract(
        document_text="Invoice Number: INV-1024",
        document_type=DocumentType.INVOICE,
    )

    assert result == expected_result

    first_provider.extract.assert_called_once()
    second_provider.extract.assert_called_once()