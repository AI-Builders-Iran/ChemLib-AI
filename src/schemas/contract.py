from datetime import date

from pydantic import BaseModel
from .common import DocumentType

#-------------schema extracting contract--------------------
class Contract(BaseModel):
    document_type: DocumentType = DocumentType.CONTRACT
    contract_title: str
    parties: list[str]
    subject: str
    start_date: date | None = None
    end_date: date | None = None
    total_value: float | None = None