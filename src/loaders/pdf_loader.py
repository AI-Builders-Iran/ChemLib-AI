from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from .base import BaseLoader
from .ocr import ocr_pdf_page

MIN_TEXT_LENGTH = 20


class PDFLoader(BaseLoader):

    def load(self, file: Path | str) -> list[Document]:
        """Load PDF; pages with little/no extractable text fall back to OCR."""
        loader = PyPDFLoader(file_path=str(file))
        raw_documents = loader.load()

        result: list[Document] = []
        for doc in raw_documents:
            text = doc.page_content.strip()

            if len(text) < MIN_TEXT_LENGTH:
                page_number = doc.metadata.get("page", 0)
                text = ocr_pdf_page(file, page_number)
                doc = Document(page_content=text, metadata=doc.metadata)

            result.append(doc)

        return result
