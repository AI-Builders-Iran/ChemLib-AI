from datetime import date
from pydantic import BaseModel

from .common import DocumentType

#-------------schema extracting invoice--------------------
class Invoice(BaseModel):
    document_type: DocumentType = DocumentType.INVOICE
    invoice_number: str
    vendor: str
    date: date
    total: float