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


def test_persian_cleaners_are_part_of_the_default_pipeline_and_can_be_disabled():
    from src.processing.cleaners.persian import LineWrapCleaner, PersianCharacterCleaner, PersianSpacingCleaner

    with_persian = [type(c) for c in IngestionPipeline(vector_store=FakeStore())._processor.cleaners]
    without = [type(c) for c in IngestionPipeline(vector_store=FakeStore(), persian=False)._processor.cleaners]

    for cleaner in (PersianCharacterCleaner, PersianSpacingCleaner, LineWrapCleaner):
        assert cleaner in with_persian and cleaner not in without
    assert with_persian[-1].__name__ == "WhitespaceCleaner"


def test_default_pipeline_cleans_a_messy_persian_page():
    from langchain_core.documents import Document

    messy = Document(
        page_content="  خانۀ  ما در سال ٢٠٢٤ ساخته می شود و كتاب ها\nبسیار مفید هستند و این خط بلند است ،\nبنابراین ادامه دارد.  ",
        metadata={"page": 0},
    )

    cleaned = IngestionPipeline(vector_store=FakeStore())._processor.process([messy])[0]

    assert cleaned.page_content == (
        "خانه ما در سال 2024 ساخته می\u200cشود و کتاب\u200cها بسیار مفید هستند و این خط بلند است، بنابراین ادامه دارد."
    )
    assert cleaned.metadata == {"page": 0}


def test_result_reports_which_ocr_engines_read_pages_and_how_many_were_unreadable(tmp_path):
    from collections import Counter

    file = touch(tmp_path, "scan.pdf")
    pipeline = IngestionPipeline(vector_store=FakeStore())

    def fake_ingest(path, document_id=None):
        pipeline.last_extraction = Counter({"text_layer": 2, "ocr:gemini": 3, "ocr:rapidocr": 1, "none": 1})
        return document_id, 6

    pipeline.ingest = fake_ingest

    result = pipeline.ingest_safe(file)

    assert result.status == "added"
    assert result.ocr_pages == {"gemini": 3, "rapidocr": 1}
    assert result.unread_pages == 1


def test_ocr_mode_reaches_the_document_loader_and_extraction_counts_are_kept(tmp_path, monkeypatch):
    from langchain_core.documents import Document

    received = {}

    def fake_load(file, ocr_mode=None):
        received["mode"] = ocr_mode
        return [
            Document(page_content="a", metadata={"page": 0, "extraction": "text_layer"}),
            Document(page_content="b", metadata={"page": 1, "extraction": "ocr:rapidocr"}),
        ]

    monkeypatch.setattr(ingestion.DocumentLoader, "load", staticmethod(fake_load))
    store = FakeStore()
    store.add = lambda chunks: None
    pipeline = IngestionPipeline(vector_store=store, ocr_mode="local_only")
    pipeline._processor = type("P", (), {"process": lambda self, docs: docs})()
    pipeline._chunker = type("C", (), {"chunk": lambda self, doc: [doc]})()

    _, count = pipeline.ingest(touch(tmp_path, "scan.pdf"))

    assert received["mode"] == "local_only" and count == 2
    assert pipeline.last_extraction == {"text_layer": 1, "ocr:rapidocr": 1}
