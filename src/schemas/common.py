from enum import Enum
from pydantic import BaseModel

#-------------support document type in perossesing--------------------
class DocumentType(str, Enum):
    CONTRACT = "contract"
    INVOICE = "invoice"
    GENERAL = "general"

#-------------schema extracting for other document--------------------
class GeneralDocument(BaseModel):
    document_type: DocumentType = DocumentType.GENERAL