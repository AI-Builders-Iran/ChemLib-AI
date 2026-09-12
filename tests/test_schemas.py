from datetime import date

from pydantic import ValidationError
import pytest

from src.schemas.common import DocumentType, GeneralDocument
from src.schemas.contract import Contract
from src.schemas.invoice import Invoice

#-------------test general document with default document type--------------------
def test_general_document():
    document = GeneralDocument()

    assert document.document_type == DocumentType.GENERAL


#-------------test valid invoice--------------------
def test_invoice():
    invoice = Invoice(
        invoice_number="INV-1024",
        vendor="ABC Company",
        date="2026-08-20",
        total=12500000,
    )

    assert invoice.document_type == DocumentType.INVOICE
    assert invoice.invoice_number == "INV-1024"
    assert invoice.vendor == "ABC Company"
    assert invoice.date == date(2026, 8, 20)
    assert invoice.total == 12500000


#-------------test valid contract--------------------
def test_contract():
    contract = Contract(
        contract_title="قرارداد مشارکت",
        parties=["طرف اول", "طرف دوم"],
        subject="مشارکت در ارائه خدمات",
    )

    assert contract.document_type == DocumentType.CONTRACT
    assert contract.contract_title == "قرارداد مشارکت"
    assert len(contract.parties) == 2

#-------------test invalid invoice--------------------
def test_invalid_invoice():
    with pytest.raises(ValidationError):
        Invoice(
            invoice_number="INV-1024",
            vendor="ABC Company",
            date="invalid-date",
            total=12500000,
        )