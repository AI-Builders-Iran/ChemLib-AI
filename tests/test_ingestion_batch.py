"""Single-file and folder ingestion: outcomes, skipping, replacing, filtering."""

import pytest

from rag import ingestion
from rag.ingestion import IngestionPipeline, make_document_id


class FakeStore:
    def __init__(self, existing_ids=()):
        self.ids = set(existing_ids)
        self.deleted = []

    def has_document(self, document_id):
        return document_id in self.ids

    def delete_document(self, document_id):
        self.deleted.append(document_id)
        self.ids.discard(document_id)
        return 1


def make_pipeline(store, chunks=3, error=None):
    """A real pipeline whose (slow) load/embed step is replaced by a stub."""
    pipeline = IngestionPipeline(vector_store=store)
    calls = []

    def fake_ingest(file, document_id=None):
        calls.append(file.name)
        if error:
            raise error
        return document_id, chunks

    pipeline.ingest = fake_ingest
    pipeline.calls = calls
    return pipeline


def touch(folder, relative):
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return path


def test_new_file_is_added(tmp_path):
    result = make_pipeline(FakeStore()).ingest_safe(touch(tmp_path, "a.txt"))

    assert (result.filename, result.status, result.chunks) == ("a.txt", "added", 3)


def test_existing_file_is_skipped_without_overwrite(tmp_path):
    file = touch(tmp_path, "a.txt")
    pipeline = make_pipeline(FakeStore({make_document_id(file)}))

    result = pipeline.ingest_safe(file)

    assert result.status == "skipped"
    assert pipeline.calls == []


def test_existing_file_is_replaced_with_overwrite(tmp_path):
    file = touch(tmp_path, "a.txt")
    store = FakeStore({make_document_id(file)})

    result = make_pipeline(store).ingest_safe(file, overwrite=True)

    assert result.status == "replaced" and result.chunks == 3
    assert store.deleted == [make_document_id(file)]


def test_file_without_text_is_reported_empty(tmp_path):
    assert make_pipeline(FakeStore(), chunks=0).ingest_safe(touch(tmp_path, "a.txt")).status == "empty"


def test_errors_are_reported_and_say_if_the_old_version_was_removed(tmp_path):
    file = touch(tmp_path, "a.txt")
    store = FakeStore({make_document_id(file)})

    result = make_pipeline(store, error=RuntimeError("boom")).ingest_safe(file, overwrite=True)

    assert result.status == "failed" and "boom" in result.detail
    assert result.old_version_removed is True


def test_unsupported_type_fails_cleanly(tmp_path):
    result = make_pipeline(FakeStore()).ingest_safe(touch(tmp_path, "a.exe"))

    assert result.status == "failed" and ".exe" in result.detail


def test_directory_ingests_supported_files_recursively_and_ignores_the_rest(tmp_path):
    for name in ("a.txt", "sub/b.pdf", "sub/deep/c.docx", "notes.md", "~$lock.docx", ".hidden.txt",
                 "__MACOSX/junk.txt", "image.png"):
        touch(tmp_path, name)
    pipeline = make_pipeline(FakeStore())

    results = pipeline.ingest_directory(tmp_path)

    assert sorted(r.filename for r in results) == ["a.txt", "b.pdf", "c.docx"]
    assert {r.status for r in results} == {"added"}


def test_directory_can_be_non_recursive(tmp_path):
    touch(tmp_path, "a.txt")
    touch(tmp_path, "sub/b.txt")

    results = make_pipeline(FakeStore()).ingest_directory(tmp_path, recursive=False)

    assert [r.filename for r in results] == ["a.txt"]


def test_same_file_name_in_two_folders_is_flagged_not_overwritten(tmp_path):
    touch(tmp_path, "one/book.txt")
    touch(tmp_path, "two/book.txt")
    pipeline = make_pipeline(FakeStore())

    results = pipeline.ingest_directory(tmp_path)

    assert sorted(r.status for r in results) == ["added", "duplicate_name"]
    assert pipeline.calls == ["book.txt"]


def test_one_failing_file_does_not_stop_the_folder(tmp_path):
    touch(tmp_path, "a.txt")
    touch(tmp_path, "b.txt")
    pipeline = IngestionPipeline(vector_store=FakeStore())

    def flaky(file, document_id=None):
        if file.name == "a.txt":
            raise RuntimeError("bad file")
        return document_id, 2

    pipeline.ingest = flaky

    assert [(r.filename, r.status) for r in pipeline.ingest_directory(tmp_path)] == [
        ("a.txt", "failed"),
        ("b.txt", "added"),
    ]


def test_progress_callback_reports_each_file(tmp_path):
    touch(tmp_path, "a.txt")
    touch(tmp_path, "b.txt")
    seen = []

    make_pipeline(FakeStore()).ingest_directory(tmp_path, on_progress=lambda i, n, name: seen.append((i, n, name)))

    assert seen == [(1, 2, "a.txt"), (2, 2, "b.txt")]


def test_missing_directory_raises(tmp_path):
    with pytest.raises(NotADirectoryError):
        make_pipeline(FakeStore()).ingest_directory(tmp_path / "nope")


def test_supported_extensions_are_the_documented_ones():
    assert ingestion.SUPPORTED_EXTENSIONS == {".pdf", ".docx", ".txt"}
