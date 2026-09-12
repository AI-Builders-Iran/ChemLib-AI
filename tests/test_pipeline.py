from datetime import date
from pathlib import Path

import pytest
from langchain_core.documents import Document

from src.loaders.document_loader import DocumentLoader
from src.pipeline import DocumentPipeline
from src.processing import DocumentProcessor, RecursiveChunker
from src.schemas.common import DocumentType
from src.schemas.invoice import Invoice
from src.utils import model_to_dict, model_to_json


class FakeExtractor:
    def __init__(self, result: Invoice) -> None:
        self.result = result
        self.calls: list[tuple[str, DocumentType]] = []

    def extract(
        self,
        document_text: str,
        document_type: DocumentType,
    ) -> Invoice:
        self.calls.append((document_text, document_type))
        return self.result


class RecordingProcessor:
    def __init__(self, result: list[Document]) -> None:
        self.result = result
        self.received: list[Document] | None = None

    def process(self, documents: list[Document]) -> list[Document]:
        self.received = documents
        return self.result


class RecordingChunker:
    def __init__(self, chunks_by_text: dict[str, list[Document]]) -> None:
        self.chunks_by_text = chunks_by_text
        self.received: list[Document] = []

    def chunk(self, document: Document) -> list[Document]:
        self.received.append(document)
        return self.chunks_by_text.get(document.page_content, [])


def make_invoice() -> Invoice:
    return Invoice(
        invoice_number="INV-1024",
        vendor="ABC Company",
        date=date(2026, 8, 20),
        total=12500000,
    )


def patch_loader(monkeypatch: pytest.MonkeyPatch, documents: list[Document]) -> None:
    def load(cls: type[DocumentLoader], file: Path | str) -> list[Document]:
        return documents

    monkeypatch.setattr(DocumentLoader, "load", classmethod(load))


def test_pipeline_happy_path_passes_text_and_document_type() -> None:
    extractor = FakeExtractor(make_invoice())
    processor = RecordingProcessor([Document(page_content="clean text")])
    chunker = RecordingChunker(
        {"clean text": [Document(page_content="clean text")]}
    )
    pipeline = DocumentPipeline(
        extractor=extractor,
        processor=processor,  # type: ignore[arg-type]
        chunker=chunker,  # type: ignore[arg-type]
    )

    original = [Document(page_content="source text")]
    with pytest.MonkeyPatch.context() as monkeypatch:
        patch_loader(monkeypatch, original)
        result = pipeline.run("sample.txt", DocumentType.INVOICE)

    assert processor.received == original
    assert chunker.received == [Document(page_content="clean text")]
    assert extractor.calls == [("clean text", DocumentType.INVOICE)]
    assert result is extractor.result
    assert isinstance(result, Invoice)


def test_multiple_documents_are_processed_and_chunked_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = FakeExtractor(make_invoice())
    documents = [Document(page_content="first"), Document(page_content="second")]
    processor = RecordingProcessor(documents)
    chunker = RecordingChunker(
        {
            "first": [Document(page_content="first-1"), Document(page_content="first-2")],
            "second": [Document(page_content="second-1")],
        }
    )
    patch_loader(monkeypatch, documents)

    DocumentPipeline(
        extractor=extractor,
        processor=processor,  # type: ignore[arg-type]
        chunker=chunker,  # type: ignore[arg-type]
    ).run("sample.txt", DocumentType.CONTRACT)

    assert [doc.page_content for doc in chunker.received] == ["first", "second"]
    assert extractor.calls == [
        ("first-1\n\nfirst-2\n\nsecond-1", DocumentType.CONTRACT)
    ]


def test_real_loader_processor_and_chunker_connect_to_fake_extractor(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.txt"
    source.write_text(
        "Invoice Number: INV-1024\x00\r\nVendor: ABC Company\r\n\r\n"
        "Date: 2026-08-20\r\nTotal: 12500000",
        encoding="utf-8",
    )
    extractor = FakeExtractor(make_invoice())

    result = DocumentPipeline(
        extractor=extractor,
        chunker=RecursiveChunker(chunk_size=30, chunk_overlap=0),
    ).run(source, DocumentType.INVOICE)

    assert result is extractor.result
    assert len(extractor.calls) == 1
    extracted_text, extracted_type = extractor.calls[0]
    assert extracted_type is DocumentType.INVOICE
    assert "\x00" not in extracted_text
    assert "\r" not in extracted_text
    assert "Invoice Number: INV-1024" in extracted_text
    assert "Vendor: ABC Company" in extracted_text


def test_unsupported_extension_error_is_preserved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.md"
    source.write_text("unsupported", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        DocumentPipeline(extractor=FakeExtractor(make_invoice())).run(
            source,
            DocumentType.GENERAL,
        )


def test_missing_file_error_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "missing.txt"

    with pytest.raises(RuntimeError, match="Error loading"):
        DocumentPipeline(extractor=FakeExtractor(make_invoice())).run(
            source,
            DocumentType.GENERAL,
        )


def test_empty_loader_result_fails_before_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = FakeExtractor(make_invoice())
    patch_loader(monkeypatch, [])

    with pytest.raises(ValueError, match="loader returned no documents"):
        DocumentPipeline(extractor=extractor).run(
            "sample.txt",
            DocumentType.GENERAL,
        )

    assert extractor.calls == []


def test_empty_chunk_result_fails_before_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = FakeExtractor(make_invoice())
    patch_loader(monkeypatch, [Document(page_content="text")])
    chunker = RecordingChunker({"text": []})

    with pytest.raises(ValueError, match="no usable document text"):
        DocumentPipeline(
            extractor=extractor,
            chunker=chunker,  # type: ignore[arg-type]
        ).run("sample.txt", DocumentType.GENERAL)

    assert extractor.calls == []


def test_unsupported_document_type_fails_before_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = FakeExtractor(make_invoice())
    patch_loader(monkeypatch, [Document(page_content="text")])

    with pytest.raises(ValueError, match="Unsupported document type"):
        DocumentPipeline(extractor=extractor).run(
            "sample.txt",
            "memo",  # type: ignore[arg-type]
        )

    assert extractor.calls == []


def test_json_utilities_serialize_pydantic_model() -> None:
    invoice = make_invoice()

    as_dict = model_to_dict(invoice)
    as_json = model_to_json(invoice)

    assert as_dict["document_type"] == "invoice"
    assert as_dict["date"] == "2026-08-20"
    assert '"invoice_number":"INV-1024"' in as_json


def test_default_processor_uses_the_real_cleaners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extractor = FakeExtractor(make_invoice())
    patch_loader(monkeypatch, [Document(page_content="\x00  text\r\n")])
    chunker = RecordingChunker({"text": [Document(page_content="text")]})

    DocumentPipeline(
        extractor=extractor,
        chunker=chunker,  # type: ignore[arg-type]
    ).run("sample.txt", DocumentType.GENERAL)

    assert [doc.page_content for doc in chunker.received] == ["text"]
