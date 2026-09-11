# DocumentAI

DocumentAI extracts structured information from PDF, DOCX, and TXT documents using local document processing and LLM-backed Pydantic schemas.

The current pipeline is:

```text
File
  |
  v
DocumentLoader
  |
  v
DocumentProcessor
  |
  v
RecursiveChunker
  |
  v
ordered document text
  |
  v
DocumentExtractor
  |
  v
validated Pydantic model
  |
  v
JSON / dict
```

## Current status

The `feature/pipeline` branch contains the Person 3 integration implementation.

- `DocumentPipeline.run(file_path, document_type)` connects all processing and extraction stages.
- `DocumentType` currently supports `INVOICE`, `CONTRACT`, and `GENERAL`.
- The pipeline returns the validated Pydantic model produced by `DocumentExtractor`.
- Tests use fake extractors, so normal automated tests do not call Gemini, OpenRouter, or any other external LLM.
- The current test suite passes with 18 tests.

For a complete Persian explanation of the implementation, contracts, design decisions, tests, and limitations, see [README_PERSON3_PIPELINE.md](README_PERSON3_PIPELINE.md).

## Project structure

```text
DocumentAI/
|-- src/
|   |-- loaders/
|   |   |-- document_loader.py       # Extension-based loader routing
|   |   |-- pdf_loader.py            # PDFLoader
|   |   |-- docx_loader.py           # DOCXLoader
|   |   +-- txt_loader.py            # TXTLoader
|   |-- processing/
|   |   |-- cleaners/                # Text, Unicode, and whitespace cleaners
|   |   |-- chunking/                # RecursiveChunker
|   |   +-- pipeline.py              # DocumentProcessor
|   |-- extraction/
|   |   |-- extractor.py             # Schema selection and provider fallback
|   |   |-- prompts.py               # PromptBuilder
|   |   +-- providers/               # LLMProvider, Gemini, and OpenRouter
|   |-- schemas/                     # Invoice, Contract, and GeneralDocument
|   |-- pipeline/
|   |   |-- pipeline.py              # DocumentPipeline
|   |   +-- __init__.py              # Public pipeline export
|   +-- utils/
|       |-- json_utils.py            # Pydantic dict/JSON serialization
|       +-- __init__.py              # Public utility exports
|-- tests/
|   |-- test_pipeline.py
|   |-- test_extractor.py
|   +-- test_schemas.py
|-- README.md
|-- README_PERSON3_PIPELINE.md
|-- requirements.txt
+-- Dockerfile
```

There is currently no `config.py`. Provider settings are read from environment variables by the existing providers, and chunking settings can be supplied by injecting a configured `RecursiveChunker`.

## Team responsibilities

### Person 1: document processing

Person 1 owns `src/loaders/` and `src/processing/`.

```text
File -> Document -> clean Document -> chunks
```

The main contracts are:

```python
DocumentLoader.load(file: Path | str) -> list[Document]
DocumentProcessor.process(documents: list[Document]) -> list[Document]
RecursiveChunker.chunk(document: Document) -> list[Document]
```

`DocumentLoader` routes `.pdf`, `.docx`, and `.txt` files to the corresponding loader. `DocumentProcessor` applies cleaners sequentially while preserving metadata. `RecursiveChunker` accepts one `Document` at a time.

### Person 2: LLM extraction

Person 2 owns `src/extraction/` and `src/schemas/`.

```text
text -> prompt -> provider -> schema -> validated Pydantic model
```

The main contract is:

```python
DocumentExtractor.extract(
    document_text: str,
    document_type: DocumentType,
) -> BaseModel
```

`DocumentExtractor` selects the schema using `DocumentType`, builds a prompt with `PromptBuilder`, and tries providers in order. If one provider fails, the next provider is used as a fallback.

### Person 3: integration

Person 3 owns `src/pipeline/`, `src/utils/`, and `tests/test_pipeline.py`.

The current integration contract is:

```text
Path | str
  -> list[Document]
  -> list[Document]
  -> list[Document]
  -> str
  -> BaseModel
```

The pipeline loops over processed documents because `RecursiveChunker.chunk()` accepts a single `Document`. It flattens the resulting chunk lists, reads each `chunk.page_content`, preserves order, joins the text, and calls the extractor once.

## Usage

### Environment variables

Never place API keys in source code. The existing providers read these variables:

```powershell
$env:GEMINI_API_KEY = "your-gemini-key"
$env:OPENROUTER_API_KEY = "your-openrouter-key"
$env:OPENROUTER_MODEL = "your-model-name"
```

### Invoice extraction with Gemini

```python
from src.extraction.extractor import DocumentExtractor
from src.extraction.providers.gemini_provider import GeminiProvider
from src.pipeline import DocumentPipeline
from src.schemas.common import DocumentType
from src.utils import model_to_dict, model_to_json

provider = GeminiProvider()
extractor = DocumentExtractor(providers=[provider])
pipeline = DocumentPipeline(extractor=extractor)

result = pipeline.run(
    "sample.pdf",
    DocumentType.INVOICE,
)

print(result)
print(model_to_dict(result))
print(model_to_json(result))
```

### Contract extraction with provider fallback

```python
from src.extraction.extractor import DocumentExtractor
from src.extraction.providers.gemini_provider import GeminiProvider
from src.extraction.providers.openrouter_provider import OpenRouterProvider
from src.pipeline import DocumentPipeline
from src.schemas.common import DocumentType
from src.utils import model_to_json

providers = [
    GeminiProvider(),
    OpenRouterProvider(),
]
extractor = DocumentExtractor(providers=providers)
pipeline = DocumentPipeline(extractor=extractor)

result = pipeline.run(
    "contract.docx",
    DocumentType.CONTRACT,
)

print(result)
print(model_to_json(result))
```

To customize chunking, inject a configured chunker:

```python
from src.processing import RecursiveChunker

chunker = RecursiveChunker(chunk_size=2000, chunk_overlap=300)
pipeline = DocumentPipeline(
    extractor=extractor,
    chunker=chunker,
)
```

## Multi-chunk strategy

The current MVP does not perform a complete `Invoice` or `Contract` extraction independently for every chunk. Required fields may be distributed across different chunks, so independent full-schema extraction could produce incomplete Pydantic models.

Instead, the pipeline joins all non-empty chunk text in its original order and calls `DocumentExtractor.extract()` once. This keeps complete-schema validation in one place.

For very large documents, the joined text may exceed the LLM context window. Future improvements could use partial schemas, per-chunk extraction with aggregation, batching, or map-reduce extraction.

## Serialization

The pipeline returns a Pydantic model. Use the public utilities for JSON-compatible output:

```python
from src.utils import model_to_dict, model_to_json

as_dict = model_to_dict(result)
as_json = model_to_json(result)
```

These helpers use native Pydantic v2 APIs: `model_dump(mode="json")` and `model_dump_json()`.

## Installation and tests

The repository currently has an empty `requirements.txt`, although the source uses Pydantic, LangChain, provider SDKs, and pytest. In an environment where dependencies are already available, run:

```bash
python -m pytest
```

On the development machine, the default pytest temp directory had a permission restriction. The complete suite was verified with:

```bash
python -m pytest --basetemp .pytest-temp
```

Result:

```text
18 passed
```

Additional validation:

```bash
python -m compileall -q src tests
git diff --check
```

No automated test calls a real LLM provider.

## Known limitations

- `OpenRouterProvider` implements the expected `extract(prompt, schema)` method but does not inherit `LLMProvider`.
- `src/processing/__init__.py` has a pre-existing `__all__` comma issue.
- `TXTLoader` wraps missing-file errors in a `RuntimeError` from the underlying LangChain loader.
- The main pipeline currently joins all chunks, which is not suitable for documents larger than the model context window.

These issues were documented but left unchanged because they are outside the minimal Person 3 integration scope.

## Git workflow

Work on the assigned feature branch and review changes before committing:

```bash
git status
git branch --show-current
git diff
git diff --check
git diff --stat
```

Do not push, merge, rebase, or open a Pull Request until the implementation has been reviewed.

## Commit message rules

Commit messages must follow:

```text
<type>: <description>
```

Examples:

```text
feat: add PDF document loader
feat: integrate document processing pipeline
test: add pipeline integration tests
docs: update project documentation
fix: normalize repeated line breaks
```

Common types are `feat`, `fix`, `test`, `refactor`, `docs`, and `chore`.
