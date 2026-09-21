import unicodedata
from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE
from pathlib import Path

from langchain_core.documents import Document

from .base import BaseLoader

# Arabic-form letters that often appear in Persian text, mapped to the Persian forms
_CHAR_MAP = str.maketrans({
    "\u064A": "\u06CC",  # ي -> ی
    "\u0649": "\u06CC",  # ى -> ی
    "\u0643": "\u06A9",  # ك -> ک
    "\u0640": None,      # tatweel (ـ) removed
    # Persian digits -> ASCII
    **{ord("۰") + i: str(i) for i in range(10)},
    # Arabic-Indic digits -> ASCII
    **{ord("٠") + i: str(i) for i in range(10)},
})


def _decode(raw: bytes) -> tuple[str, str]:
    """Return (text, encoding_used)."""
    if raw.startswith((BOM_UTF16_LE, BOM_UTF16_BE)):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"      # strict: fails on non-UTF-8
    except UnicodeDecodeError:
        return raw.decode("cp1256", errors="replace"), "cp1256"  # legacy Windows Persian


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_CHAR_MAP)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text  # ZWNJ (\u200c) is intentionally kept; it's meaningful in Persian


class TXTLoader(BaseLoader):

    def load(self, file: Path | str) -> list[Document]:
        """Loads a Farsi/English TXT file with automatic encoding detection."""
        path = Path(file)
        text, encoding = _decode(path.read_bytes())
        text = normalize_text(text)
        return [Document(page_content=text, metadata={"source": str(path), "encoding": encoding})]