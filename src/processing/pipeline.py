from langchain_core.documents import Document

from src.layout.blocks import BLOCK_TEXT

from .cleaners.base import BaseCleaner


class DocumentProcessor:
    def __init__(self, cleaners: list[BaseCleaner]):
        self.cleaners = cleaners

    def process(self, documents: list[Document]) -> list[Document]:
        """Clean plain-text blocks as before; leave structured blocks untouched.

        A table/formula/figure block (``block_type`` != "text", see
        ``src.layout``) is Markdown/LaTeX/a caption, not prose — the Persian
        spacing/line-wrap cleaners in particular are written for paragraphs
        and would risk corrupting a table's pipe characters or a multi-line
        formula. Plain text (``block_type`` == "text", or missing — DOCX/TXT
        loaders predate this field) goes through the full cleaner chain
        exactly as before.
        """
        processed_docs = []

        for docs in documents:
            if docs.metadata.get("block_type", BLOCK_TEXT) != BLOCK_TEXT:
                processed_docs.append(docs)
                continue

            text = docs.page_content

            for cleaner in self.cleaners:
                text = cleaner.clean(text)

            processed_docs.append(
                Document(
                    page_content=text,
                    metadata=docs.metadata,
                )
            )
        return processed_docs
