from pathlib import Path

from langchain_core.documents import Document

from .base import BaseLoader
from .docx_loader import DOCXLoader
from .pdf_loader import PDFLoader
from .txt_loader import TXTLoader


class DocumentLoader:
    _loaders: dict[str, type[BaseLoader]] = {
        ".pdf": PDFLoader,
        ".docx": DOCXLoader,
        ".txt": TXTLoader
    }

    @classmethod
    def load(
        cls,
        file: Path | str,
        ocr_mode: str | None = None,
        layout_engine: str | None = None,
        on_progress=None,
    ) -> list[Document]:
        return cls.load_with_report(file, ocr_mode, layout_engine, on_progress)[0]

    @classmethod
    def load_with_report(
        cls,
        file: Path | str,
        ocr_mode: str | None = None,
        layout_engine: str | None = None,
        on_progress=None,
    ) -> tuple[list[Document], object | None]:
        """Load a file. ``ocr_mode`` and ``layout_engine`` only matter for PDFs:
        ``ocr_mode`` is "online_first" / "local_only"; ``layout_engine`` is
        "none" / "ppstructure" (default: the LAYOUT_ENGINE env var, then "ppstructure").
        ``on_progress(stage, page, total_pages)`` is called while a PDF is read.
        ``load_with_report`` also returns the PDF's ``PDFLoadReport`` (``None`` for DOCX/TXT).
        """
        file = Path(file)
        extension = file.suffix.lower()
        loader_class = cls._loaders.get(extension)

        if loader_class is None:
            raise ValueError(
                f"Unsupported file type: {extension}"
            )
        loader = (
            loader_class(ocr_mode=ocr_mode, layout_engine=layout_engine)
            if loader_class is PDFLoader
            else loader_class()
        )
        if isinstance(loader, PDFLoader):
            documents = loader.load(file, on_progress=on_progress)
            return documents, loader.last_report  # PDFLoadReport: how each page was read
        return loader.load(file), None


