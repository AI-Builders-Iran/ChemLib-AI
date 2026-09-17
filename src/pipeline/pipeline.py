from pathlib import Path

from langchain_core.documents import Document
from pydantic import BaseModel

from src.extraction.extractor import DocumentExtractor
from src.loaders.document_loader import DocumentLoader
from src.processing.chunking.recursive import RecursiveChunker
from src.processing.pipeline import DocumentProcessor
from src.processing.cleaners import (
    TextCleaner,
    UnicodeCleaner,
    WhitespaceCleaner,
)
from src.schemas.common import DocumentType


class DocumentPipeline:
    """Coordinate local document processing and structured extraction.

    The extractor is required because constructing a real extractor also
    requires at least one configured LLM provider. Processing components have
    useful local defaults and can be replaced in tests or applications.
    """

    def __init__(
        self,
        extractor: DocumentExtractor,
        processor: DocumentProcessor | None = None,
        chunker: RecursiveChunker | None = None,
    ) -> None:
        self.loader = DocumentLoader
        self.processor = processor or DocumentProcessor(
            cleaners=[
                TextCleaner(),
                UnicodeCleaner(),
                WhitespaceCleaner(),
            ]
        )
        self.chunker = chunker or RecursiveChunker()
        self.extractor = extractor

    def run(
        self,
        file_path: str | Path,
        document_type: DocumentType,
    ) -> BaseModel:
        """Load, process, chunk, and extract one logical document.

        All usable chunks are joined in their original order and sent to the
        extractor once. This is the safe MVP behavior for complete schemas
        such as ``Invoice`` and ``Contract``.
        """
        if not isinstance(document_type, DocumentType):
            raise ValueError(f"Unsupported document type: {document_type}")

        documents = self.loader.load(file_path)
        if not documents:
            raise ValueError("Document loader returned no documents.")

        processed_documents = self.processor.process(documents)
        if not processed_documents:
            raise ValueError("Document processor returned no documents.")

        chunks: list[Document] = []
        for document in processed_documents:
            document_chunks = self.chunker.chunk(document)
            if document_chunks:
                chunks.extend(document_chunks)

        usable_chunks = [
            chunk
            for chunk in chunks
            if isinstance(chunk.page_content, str)
            and chunk.page_content.strip()
        ]
        if not usable_chunks:
            raise ValueError("Chunker produced no usable document text.")

        document_text = "\n\n".join(
            chunk.page_content for chunk in usable_chunks
        )
        if not document_text.strip():
            raise ValueError("Document text is empty after processing.")

        return self.extractor.extract(
            document_text=document_text,
            document_type=document_type,
        )
