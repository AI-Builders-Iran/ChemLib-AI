"""Page-level access to a PDF: its own text layer and a rendered image.

PyMuPDF is used when installed: fast, and it renders pages without Poppler.
Without it, ``pypdf`` reads the text and ``pdf2image`` (Poppler) renders images.
"""

from __future__ import annotations

import importlib.util
import os
from abc import ABC, abstractmethod
from pathlib import Path

DEFAULT_DPI = 300


class PageSource(ABC):
    """One open PDF. Pages are 0-based."""

    @property
    @abstractmethod
    def page_count(self) -> int: ...

    @abstractmethod
    def text(self, index: int) -> str:
        """The page's embedded text layer (empty for pure scans)."""

    @abstractmethod
    def image(self, index: int, dpi: int = DEFAULT_DPI):
        """The page rendered as a PIL image."""

    def close(self) -> None:  # noqa: B027 - optional hook
        pass

    def __enter__(self) -> PageSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class PyMuPDFSource(PageSource):
    def __init__(self, path: Path | str):
        try:
            import pymupdf  # current name
        except ImportError:
            import fitz as pymupdf  # older PyMuPDF releases

        self._doc = pymupdf.open(str(path))
        if self._doc.needs_pass:
            self._doc.close()
            raise ValueError("The PDF is password protected.")

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def text(self, index: int) -> str:
        return self._doc[index].get_text("text", sort=True)

    def image(self, index: int, dpi: int = DEFAULT_DPI):
        from PIL import Image

        pixmap = self._doc[index].get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

    def close(self) -> None:
        self._doc.close()


class PypdfSource(PageSource):
    def __init__(self, path: Path | str):
        from pypdf import PdfReader

        self._path = str(path)
        self._reader = PdfReader(self._path)
        if self._reader.is_encrypted:
            raise ValueError("The PDF is password protected.")

    @property
    def page_count(self) -> int:
        return len(self._reader.pages)

    def text(self, index: int) -> str:
        return self._reader.pages[index].extract_text() or ""

    def image(self, index: int, dpi: int = DEFAULT_DPI):
        from pdf2image import convert_from_path

        images = convert_from_path(
            self._path,
            first_page=index + 1,
            last_page=index + 1,
            dpi=dpi,
            poppler_path=os.getenv("POPPLER_PATH") or None,
        )
        if not images:
            raise RuntimeError(f"Could not render page {index + 1}")
        return images[0]


def pymupdf_installed() -> bool:
    return importlib.util.find_spec("pymupdf") is not None or importlib.util.find_spec("fitz") is not None


def open_pdf(path: Path | str) -> PageSource:
    """PyMuPDF if available, otherwise pypdf + pdf2image."""
    if pymupdf_installed():
        return PyMuPDFSource(path)
    return PypdfSource(path)
