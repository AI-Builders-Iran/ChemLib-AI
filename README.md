# DocumentAI

A Document AI pipeline for extracting, understanding, and transforming unstructured documents (PDF, DOCX, TXT) into structured data using LLMs.

The project is built as a complete, production-ready pipeline:

```
File
  ↓
Document
  ↓
Clean Document
  ↓
Chunks
  ↓
LLM Extraction
  ↓
Structured Data (Pydantic)
```

---

## 📁 Project Structure

```
DocumentAI/
├── loaders/          # Person 1
├── processing/        # Person 1
├── extraction/        # Person 2
├── schemas/            # Person 2
├── pipeline/           # Person 3
├── config.py           # Person 3
├── utils/               # Person 3
└── tests/
    ├── test_loaders.py
    ├── test_cleaner.py
    ├── test_chunker.py
    ├── test_extractor.py
    ├── test_schemas.py
    └── test_pipeline.py
```

---

## 👥 Team Task Breakdown

### 👨‍💻 Person 1 — Document Processing Engineer

**Owns:** `loaders/` and `processing/`

Final output of this stage:

```
File → Document → Clean Document → Chunks
```

| # | Task | File |
|---|------|------|
| 1 | PDF Loader | `loaders/pdf_loader.py` |
| 2 | DOCX Loader | `loaders/docx_loader.py` |
| 3 | TXT Loader | `loaders/txt_loader.py` |
| 4 | Cleaner | `processing/cleaner.py` |
| 5 | Chunker | `processing/chunker.py` |
| 6 | Unit Tests | `tests/test_loaders.py`, `tests/test_cleaner.py`, `tests/test_chunker.py` |

**Branches:** `feature/loaders`, `feature/cleaner`

---

### 👨‍💻 Person 2 — LLM / Extraction Engineer

**Owns:** `extraction/` and `schemas/`

Final output of this stage:

```
Text → LLM → Structured Data → Pydantic
```

| # | Task | File |
|---|------|------|
| 1 | Prompt Design | `extraction/prompts.py` |
| 2 | LLM Integration | `extraction/extractor.py` |
| 3 | Contract Schema | `schemas/contract.py` |
| 4 | Invoice Schema | `schemas/invoice.py` |
| 5 | Structured Output (LLM → Pydantic) | `extraction/extractor.py` |
| 6 | Tests | `tests/test_extractor.py`, `tests/test_schemas.py` |

> Example prompt in `prompts.py`:
> ```python
> EXTRACTION_PROMPT = """
> Extract the following information...
> """
> ```

**Branches:** `feature/extractor`, `feature/schemas`

---

### 👨‍💻 Person 3 — Pipeline / Integration Engineer

**Owns:** `pipeline/`, `config.py`, `utils/`

⚠️ This is the most critical role — it wires everything together. The output of all three people ultimately connects here.

| # | Task | Details |
|---|------|---------|
| 1 | Core Pipeline | `pipeline/pipeline.py` — `DocumentPipeline` class with a `run(self, file_path)` method |
| 2 | Connect Loader | `Pipeline → Loader` |
| 3 | Connect Cleaner | `Loader → Cleaner` |
| 4 | Connect Chunker | `Cleaner → Chunker` |
| 5 | Connect LLM | `Chunker → Extractor` |
| 6 | Validation | `Extractor → Pydantic` |
| 7 | End-to-End Tests | `tests/test_pipeline.py` |

Skeleton class:

```python
class DocumentPipeline:
    def run(self, file_path):
        document = self.loader.load(file_path)
        clean_doc = self.cleaner.clean(document)
        chunks = self.chunker.split(clean_doc)
        extracted = self.extractor.extract(chunks)
        return self.validate(extracted)
```

**Branch:** `feature/pipeline`

---

## 🌳 Git Workflow

```
main
 │
 └── develop
       │
       ├── feature/loaders
       ├── feature/cleaner
       ├── feature/extractor
       ├── feature/schemas
       └── feature/pipeline
```

- Each person works **only on their own branch**.
- No direct commits to `main` or `develop`.
- A Pull Request is required before merging into `develop`.

---

## ✅ Commit Message Rules

Commit messages must be **clear, specific, and follow Conventional Commits**.

### ❌ Bad
```
update
fix
final
test
changes
```

### ✅ Good
```
feat: add PDF document loader
feat: add DOCX document loader
feat: implement text cleaning
feat: add contract schema
feat: add structured extraction
test: add loader unit tests
fix: normalize repeated line breaks
```

General pattern:

```
<type>: <description>
```

Common types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`

---

## 🚀 Getting Started

```bash
git clone https://github.com/AI-Builders-Iran/DocumentAI.git
cd DocumentAI
git checkout develop
git checkout -b feature/<your-feature>
```

After finishing each task, make sure to:
1. Write the corresponding unit test.
2. Commit using the correct format.
3. Open a Pull Request targeting `develop`.

---

## 📌 Project Status

The project is currently in the early development phase. This README will be updated as each section (installation, usage, examples, benchmarks) is completed.
