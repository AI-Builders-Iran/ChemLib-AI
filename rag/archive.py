"""Safe extraction of an uploaded ZIP (a "folder") into a temporary directory.

Only PDF/DOCX/TXT members are extracted. Names are sanitised (no absolute paths,
no ``..``), the number and total size of members are capped, and file names that
Windows stored in a legacy code page are decoded back to readable Persian.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path, PurePosixPath

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

MAX_MEMBERS = 2000
MAX_TOTAL_BYTES = 2 * 1024**3  # 2 GB uncompressed


class ArchiveError(ValueError):
    """The archive is unreadable or exceeds the safety limits."""


def decode_member_name(info: zipfile.ZipInfo) -> str:
    """Readable member name.

    Python decodes names without the UTF-8 flag as cp437, which garbles Persian
    names written by Windows Explorer. cp437 is lossless, so re-encode and try
    UTF-8, then Windows-1256 (Arabic/Persian).
    """
    if info.flag_bits & 0x800:
        return info.filename
    raw = info.filename.encode("cp437", errors="ignore")
    for encoding in ("utf-8", "cp1256"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return info.filename


def _safe_relative_path(name: str) -> Path | None:
    """Relative path for a member, or None if it is unsafe or should be skipped."""
    posix = PurePosixPath(name.replace("\\", "/"))
    parts = posix.parts
    if not parts or posix.is_absolute() or any(part in ("..", "") for part in parts):
        return None
    if any(":" in part for part in parts):  # Windows drive letters / alternate streams
        return None
    if any(part.startswith(".") or part == "__MACOSX" for part in parts):
        return None
    if parts[-1].startswith("~$"):
        return None
    return Path(*parts)


def extract_supported(data: bytes, destination: str | Path) -> list[str]:
    """Extract supported documents from ZIP ``data`` into ``destination``.

    Returns the extracted relative paths. Raises ``ArchiveError`` when the file
    is not a ZIP or exceeds the limits.
    """
    destination = Path(destination)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ArchiveError("The file is not a valid ZIP archive.") from exc

    with archive:
        members: list[tuple[zipfile.ZipInfo, Path]] = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            relative = _safe_relative_path(decode_member_name(info))
            if relative is None or relative.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            members.append((info, relative))

        if len(members) > MAX_MEMBERS:
            raise ArchiveError(f"The archive has more than {MAX_MEMBERS} documents.")
        if sum(info.file_size for info, _ in members) > MAX_TOTAL_BYTES:
            raise ArchiveError("The archive is too large once extracted.")

        written: list[str] = []
        total = 0  # counted while copying: headers can lie about the real size
        for info, relative in members:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as sink:
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_TOTAL_BYTES:
                        raise ArchiveError("The archive is too large once extracted.")
                    sink.write(chunk)
            written.append(relative.as_posix())

    return written
