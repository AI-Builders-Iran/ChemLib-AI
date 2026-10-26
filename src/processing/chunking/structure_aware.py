from langchain_core.documents import Document

from src.layout.blocks import BLOCK_TEXT

from .base import BaseChunker
from .recursive import RecursiveChunker


class StructureAwareChunker(BaseChunker):
    """Splits plain text as before; keeps structured blocks whole.

    A ``Document`` produced by the layout segmenter (``block_type`` =
    "table" / "formula" / "figure", see ``src.layout``) is never split —
    cutting a Markdown table or a LaTeX formula mid-structure would defeat
    the point of extracting it separately. It always becomes exactly one
    chunk. Plain text (``block_type`` = "text", or missing — DOCX/TXT loaders
    and any Document predating this field default to it) is delegated to
    ``RecursiveChunker`` unchanged, so behaviour for files without a layout
    segmenter is identical to before.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        text_chunker: BaseChunker | None = None,
    ):
        self._text_chunker = text_chunker or RecursiveChunker(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    def chunk(self, document: Document) -> list[Document]:
        block_type = document.metadata.get("block_type", BLOCK_TEXT)
        if block_type != BLOCK_TEXT:
            return [document] if document.page_content.strip() else []
        return self._text_chunker.chunk(document)
