"""Safe ZIP extraction for folder uploads."""

import io
import zipfile

import pytest

from docai_ui import archive


def make_zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buffer.getvalue()


def test_extracts_only_supported_documents_keeping_subfolders(tmp_path):
    data = make_zip({
        "book.pdf": b"%PDF",
        "notes/chapter1.txt": b"hello",
        "notes/deep/extra.docx": b"PK",
        "photo.png": b"png",
        "readme.md": b"md",
    })

    written = archive.extract_supported(data, tmp_path)

    assert sorted(written) == ["book.pdf", "notes/chapter1.txt", "notes/deep/extra.docx"]
    assert (tmp_path / "notes" / "chapter1.txt").read_bytes() == b"hello"
    assert not (tmp_path / "photo.png").exists()


def test_unsafe_and_junk_members_are_skipped(tmp_path):
    data = make_zip({
        "../evil.txt": b"x",
        "/abs/evil.txt": b"x",
        "a/../../evil2.txt": b"x",
        "C:/drive.txt": b"x",
        "__MACOSX/._junk.txt": b"x",
        ".hidden.txt": b"x",
        "~$lock.docx": b"x",
        "ok.txt": b"fine",
    })

    written = archive.extract_supported(data, tmp_path / "out")

    assert written == ["ok.txt"]
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "evil2.txt").exists()


def test_not_a_zip_is_rejected(tmp_path):
    with pytest.raises(archive.ArchiveError, match="not a valid ZIP"):
        archive.extract_supported(b"this is not a zip", tmp_path)


def test_too_many_documents_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "MAX_MEMBERS", 2)
    data = make_zip({f"{i}.txt": b"x" for i in range(3)})

    with pytest.raises(archive.ArchiveError, match="more than 2"):
        archive.extract_supported(data, tmp_path)


def test_size_limit_is_enforced_on_real_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "MAX_TOTAL_BYTES", 10)
    data = make_zip({"a.txt": b"x" * 100})

    with pytest.raises(archive.ArchiveError, match="too large"):
        archive.extract_supported(data, tmp_path)


def test_persian_names_written_without_the_utf8_flag_are_repaired():
    name = "شیمی_آلی.pdf"

    utf8_in_cp437 = zipfile.ZipInfo("x")
    utf8_in_cp437.filename = name.encode("utf-8").decode("cp437")
    utf8_in_cp437.flag_bits = 0
    assert archive.decode_member_name(utf8_in_cp437) == name

    windows_1256 = zipfile.ZipInfo("x")
    windows_1256.filename = "کتاب.txt".encode("cp1256").decode("cp437")
    windows_1256.flag_bits = 0
    assert archive.decode_member_name(windows_1256) == "کتاب.txt"


def test_names_with_the_utf8_flag_are_left_alone():
    info = zipfile.ZipInfo("x")
    info.filename = "شیمی.txt"
    info.flag_bits = 0x800

    assert archive.decode_member_name(info) == "شیمی.txt"
