# 📚 ChemLib AI

## AI assistant for a university chemistry library: grounded RAG chat + structured extraction

> **Formerly DocumentAI.** The project was renamed to **ChemLib AI** (repo:
> [`AI-Builders-Iran/ChemLib-AI`](https://github.com/AI-Builders-Iran/ChemLib-AI))
> when it became a demo for a university chemistry faculty. The original
> document-extraction feature is still here as a separate demo.

A student asks a scientific question in Persian or English; the answer comes
from the library's own books, with the book and page it was taken from, and
never from the model's guesswork.

**Highlights**

- Answers with citations (book + page); says "not enough information" instead of guessing
- Persian and English, mixed text and scanned PDFs (OCR)
- **My documents** mode: a user's own file/folder, kept in memory for one session only
- Library admin panel: add, replace and remove books without touching code
- Automatic fallback from Gemini to OpenRouter, with a visible notice to the user
- Compare a concept across two sources, and a REST API for other systems

ChemLib AI covers two related products built on the same document
loading/processing foundation:

1. **Chemistry Library RAG** — the library's PDFs/DOCX/TXT (including scanned
   PDFs) are indexed into a vector database, and users ask grounded questions
   with citations. It ships as a ready-to-present web app with two roles:
   - **Users** get a chat over the library. They can also load their own
     file or folder for the current session only: it stays in memory, is never
     saved to the vector database and disappears with the page.
   - **Library admins** get a protected panel to add, replace and remove
     documents in the vector database, one file, many files, a ZIP or a whole
     folder at a time.
2. **Structured Extraction** — turn an invoice/contract/general document into
   validated JSON. The pipeline (`src/extraction/`, `src/pipeline/`) is still
   there and still reachable via `POST /api/v1/extract`; it currently has no
   dedicated UI (the old Streamlit demo for it was removed — see
   "Project history" below).

### UI

**NiceGUI app** (`app/nicegui_app/`) — run with `python -m app.nicegui_app.main`.
Dashboard, AI Chat (library + private docs, Compare Sources, citations),
Documents, Settings. Admin actions are gated by `ADMIN_PASSWORD`. It calls
the backend directly (`rag/`, `src/`) — no HTTP hop through
`app/api/api_app.py`, which is a separate FastAPI surface for external API
consumers and doesn't even cover document management.

> **Project history:** this app originally shipped with a Streamlit UI
> (`app/streamlit_app/`). It has been replaced by the NiceGUI app above and
> removed from the repository; its structured-extraction demo page went with
> it (the underlying extraction feature itself did not — see point 2 above).

---

## 🔄 End-to-End Pipelines

### RAG pipeline

```text
Ingest (library admin):
  Document → Loader (text layer first; OCR only for pages without one, see below)
           → Cleaning (Unicode, control chars, Persian normalisation) → Chunking
           → Embedding (BGE-M3, local) → ChromaDB (persisted on disk)

Chat (user):
  Question → Persian-normalise → Embed question → Chroma similarity search
           → similarity below threshold? → "not enough information" (no LLM call)
           → else → RAG prompt → LLM (OpenRouter)
           → grounded answer + sources (book + page)

Compare (same chat, or API):
  "Compare X and Y" detected in the chat, or two document_ids via the API
           → retrieve each source independently
           → compare prompt (contexts kept strictly separate)
           → LLM → structured comparison (definition/explanation per source + comparison)
```

### Extraction pipeline

```text
Document (PDF/DOCX/TXT)
   → Loader → Cleaning → Chunking → Rejoin
   → LLM Extraction (OpenRouter)
   → Validated Pydantic model (Invoice / Contract / GeneralDocument)
```

---

## 🏗 Architecture

```text
                         PDF / DOCX / TXT
                                |
                                ↓
                      ┌─────────────────┐
                      │ Document Loader │  (text layer first, multi-engine
                      └────────┬────────┘   OCR only for scanned pages)
                               |
                               ↓
                 ┌────────────────────────┐
                 │ Text Processing Layer  │
                 │ Unicode / Text / WS    │
                 │ Recursive Chunking     │
                 └───────────┬────────────┘
                               |
                 ┌─────────────┴─────────────┐
                 ↓                           ↓
     ┌────────────────────┐      ┌───────────────────────┐
     │ Extraction Engine   │      │ RAG Ingestion          │
     │ OpenRouter          │      │ BGE-M3 Embedding        │
     │ → Pydantic schemas  │      │ → ChromaDB               │
     └──────────┬───────────┘     └───────────┬───────────┘
                 |                             |
                 |                             ↓
                 |                  ┌───────────────────────┐
                 |                  │ RAGService             │
                 |                  │ retrieve → prompt →    │
                 |                  │ OpenRouter →           │
                 |                  │ grounded answer/compare│
                 |                  └───────────┬───────────┘
                 └─────────────┬─────────────────┘
                               ↓
          ┌─────────────────────────────────────────┐
          │ FastAPI          NiceGUI                  │
          │                  ├─ Chat (users)          │
          │                  └─ Library admin panel   │
          └─────────────────────────────────────────┘
```

---

## 🛠 Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| Document loading | LangChain loaders (PDF/DOCX/TXT) |
| PDF text / rendering | PyMuPDF (fallback: pypdf + pdf2image/Poppler) |
| OCR (scanned pages only) | Engine chain with quality gate: online (Azure Document Intelligence, OpenRouter vision model), local fallback (RapidOCR, English) |
| LLM providers | OpenRouter (only) |
| Embeddings | BAAI/bge-m3, local via `sentence-transformers` (free, no API cost) |
| Vector store | ChromaDB (persisted locally) |
| Data validation | Pydantic v2 (structured LLM output for both features) |
| API | FastAPI |
| UI | NiceGUI (right-to-left, Persian) |
| Testing | Pytest |
| Deployment | Docker |

---

## 📂 Project Structure

```text
ChemLib-AI/
├── app/
│   ├── api/api_app.py              # /extract, /ingest (admin), /chat, /compare
│   └── streamlit_app/
│       ├── app.py                  # library app: user chat + hidden admin panel
│       ├── extraction_demo.py      # original structured-extraction demo UI
│       └── docai_ui/               # UI building blocks
│           ├── chat_view.py        #   user chat
│           ├── admin_view.py       #   admin sign-in, upload (files/ZIP/folder), document list
│           ├── outcomes.py         #   shows per-file ingestion results
│           ├── archive.py          #   safe ZIP extraction for folder uploads
│           ├── services.py         #   cached vector store / RAG service, ingestion
│           ├── auth.py             #   ADMIN_PASSWORD check
│           ├── components.py       #   HTML fragments (source tiles, hero, stats)
│           ├── helpers.py          #   labels, digits, colours
│           └── theme.py            #   stylesheet
├── .streamlit/config.toml          # theme, upload limit
├── rag/
│   ├── schemas.py                  # ChunkResult, RAGAnswer, CompareAnswer, API schemas
│   ├── prompts.py                  # RAGPromptBuilder, ComparePromptBuilder
│   ├── ingestion.py                # load → clean → chunk → embed → store (file, batch, folder)
│   └── rag_service.py              # retrieval + grounding threshold + LLM fallback
├── src/
│   ├── loaders/                    # PDF (page routing, pdf_pages.py) / DOCX / TXT
│   ├── ocr/                        # OCR engines, quality checks, fallback pipeline
│   ├── processing/
│   │   ├── cleaners/               # unicode, text, whitespace, persian (Persian rules)
│   │   └── chunking/
│   ├── embedding/embedding.py      # BGE-M3 embedder (LangChain HuggingFaceEmbeddings)
│   ├── retrieval/vector_store.py   # ChromaDB store: add / query / list / delete
│   ├── retrieval/session_store.py  # in-memory store for a user's private documents
│   ├── extraction/
│   │   ├── prompts.py
│   │   ├── providers/              # OpenRouterProvider (shared by both features: extraction, RAG chat, OCR, figure captions)
│   │   └── extractor.py
│   ├── schemas/                    # Extraction-only schemas (Invoice, Contract, GeneralDocument)
│   └── pipeline/                   # Extraction orchestration
├── tests/                          # pytest, mocks only
├── vector_database/                # created on first ingestion (git-ignored)
├── requirements.txt
├── Dockerfile
└── README.md
```

**Note on `OpenRouterProvider` sharing:** the Extraction feature, the RAG
feature (chat + compare), and OCR/figure-captioning all use the same
`src/extraction/providers/OpenRouterProvider` — that folder name is a
holdover from when the project only did extraction; the provider itself is
general-purpose (`extract(prompt, schema)` for text, `extract_image(image,
prompt, schema)` for vision) and is not extraction-specific.

---

## ⚡ Quick Start

```bash
git clone https://github.com/AI-Builders-Iran/ChemLib-AI.git
cd ChemLib-AI

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Configuration

Copy `.env` to `.env` and fill in:

```bash
OPENROUTER_API_KEY=your-key   # required — used by extraction, RAG chat/compare, and online OCR/figure captions
OPENROUTER_MODEL=             # optional — model slug routed through OpenRouter; must support image input for OCR/figure captions (see .env)
ADMIN_PASSWORD=choose-one     # required for the library admin panel
<<<<<<< HEAD
POPPLER_PATH=                 # Windows only, and only without PyMuPDF — see .env
```

OCR settings are optional; see [Scanned PDFs and OCR](#-scanned-pdfs-and-ocr).
For scanned English PDFs without internet, `pip install rapidocr-onnxruntime`
(already in `requirements.txt`) and pick **فقط محلی** in the upload form.
=======
POPPLER_PATH=                 # Windows only — see .env.example

# Optional model overrides
GEMINI_MODEL=                 # default: gemini-3.6-flash
OPENROUTER_MODEL=             # default: openrouter/auto (use openrouter/free for free models only)
```

**LLM fallback.** Gemini is tried first. If it does not answer (quota, outage,
network), the request is retried automatically on OpenRouter and the chat shows
which model answered. If neither answers, the user is told so. The fallback
needs `OPENROUTER_API_KEY` **and** the `langchain-openrouter` package (both are
in `requirements.txt`). Free-tier Gemini quotas are small and per model, and
OCR of scanned pages uses the same quota. Restart the app after changing `.env`:
providers are created once per process.
>>>>>>> 623a52fcabb13bb6235dcffd784b29f43f8deafd

The app and the API load `.env` automatically. Never commit it (it is already
in `.gitignore` and `.dockerignore`).

**Windows extra setup, only if PyMuPDF is not installed** (PyMuPDF renders
scanned pages itself; without it, `pdf2image` needs Poppler, which is not
installable via pip):
1. Download Poppler for Windows: https://github.com/oschwartz10612/poppler-windows/releases
2. Extract it, find the folder containing `pdftoppm.exe` / `pdfinfo.exe`
3. Set `POPPLER_PATH` in `.env` to that folder

On Linux/Mac, install poppler via your package manager
(`apt-get install poppler-utils` / `brew install poppler`) and leave
`POPPLER_PATH` empty — it will already be on `PATH`.

---

## 🚀 Usage

### 1. Run the library app

Always start from the project root (the vector database path and
`.streamlit/config.toml` are resolved from there):

```bash
streamlit run app/streamlit_app/app.py
```

Open http://localhost:8501.

> The first start downloads the BGE-M3 embedding model (roughly 2 GB) and
> loads it, so it takes a few minutes. Later starts are fast.

#### For users: ask questions

1. Open http://localhost:8501. You land directly on the chat.
2. Type a question in Persian or English and press Enter. Write the concept's
   name in the question itself: every question is searched independently, so
   follow-ups like "explain more" do not carry over.
3. Read the answer. Under it, each **source tile** shows the book (colour and
   letters) and the page (number in the corner) the answer came from.
4. With more than one book in the library, use **جست‌وجو در** (Search in) to search all
   books or a single one. **گفتگوی جدید** (New chat) clears the conversation.
5. If nothing relevant exists in the library, the app says so instead of
   guessing.
6. **Compare two sources — in the same chat, no separate screen.** Ask
   something like "Compare Organic Chemistry and Inorganic Chemistry" (or
   "کتاب X و کتاب Y را مقایسه کن") right in the chat box. The app detects the
   two source names, retrieves each independently, and answers with an
   overall comparison plus each source's own definition/explanation and
   citations. This reuses the same backend as `POST /api/v1/compare` — see
   [REST API](#2-rest-api) — it's just wired into the chat input as well now.

**Using your own documents (no library needed).** Switch the selector at the
top of the chat from **کتابخانه** (Library) to **سند من** (My documents):

1. Under **بارگذاری فایل یا پوشه** (Upload file or folder), pick one file, several files, or a folder
   compressed as a ZIP (browsers cannot upload a raw folder to Streamlit).
   PDF, DOCX and TXT are read; sub-folders inside the ZIP are included.
2. Press **بارگذاری موقت** (Temporary upload) and wait until the files are processed.
3. Ask questions as usual. Answers and source tiles come only from your files.
4. **پاک‌کردن سندهای من** (Clear my documents) removes them immediately; closing or refreshing the
   page removes them too.

Your files are kept in memory for your session only: they never reach the
shared vector database and nobody else can search them. To write an answer,
the passages relevant to your question are still sent to the language-model
service (OpenRouter), like any library question. A
private session is limited to about 5,000 text chunks (a few large books).
This mode also works when the library is empty.

#### For the library admin: add documents

1. Open http://localhost:8501/?mode=admin (users are never shown this address
   or any link to it).
2. Sign in with `ADMIN_PASSWORD`.
3. Choose **مدیریت منابع** (Manage sources) in the top bar.
4. Under **افزودن منبع جدید** (Add new source) choose how to add documents:
   - **فایل یا ZIP** (File or ZIP): select one file, several files, or a ZIP of a folder
     (every PDF/DOCX/TXT inside, sub-folders included) and press
     **افزودن به کتابخانه** (Add to library).
   - **پوشه روی این رایانه** (Folder on this computer): type the path of a folder on the machine running
     the app (for example `D:\Books\Chemistry`), choose whether sub-folders
     are read, and press **افزودن پوشه** (Add folder). Best for a big collection already on
     the server.

   Each file is read, cleaned, chunked, embedded and stored in the vector
   database; scanned PDF pages go through the OCR engine chain (slower, and cloud
   engines use API quota). One failing file does not stop the rest: every file gets its own
   result. Hidden files, Word lock files (`~$...`) and unsupported types are
   ignored, and two files with the same name in different sub-folders are
   reported as duplicates (only the first is indexed, because a document id
   comes from the file name).
5. A file whose name is already indexed is skipped. Tick
   **اگر منبعی با همین نام وجود دارد، جایگزین شود** (Replace if a source with the same name exists) to replace it: the old
   version is deleted first, then the new file is indexed.
6. **منابع ایندکس‌شده** (Indexed sources) lists every book with its number of chunks; **حذف** (Delete)
   removes a book (with a confirmation step).
<<<<<<< HEAD
7. **وضعیت تنظیمات** shows whether the OpenRouter key and
   Poppler are configured. Switch back to **گفتگو** to try the chat as a user
   would, and use **خروج** to sign out.
=======
7. **وضعیت تنظیمات** (Configuration status) shows whether the Gemini key, the OpenRouter key,
   Poppler and the OpenRouter package are configured. Switch back to **گفتگو** (Chat) to try the chat as a user
   would, and use **خروج** (Sign out) to sign out.
>>>>>>> 623a52fcabb13bb6235dcffd784b29f43f8deafd

Who sees what:

| | User | Library admin |
|---|---|---|
| Chat with citations | yes | yes |
| Book list and search scope | yes | yes |
| Load own file/folder for this session only (memory, never saved) | yes | yes |
| Add / replace / delete library documents (file, ZIP, folder) | no | yes |
| Configuration status, technical error details | no | yes |

**Security notes.** The `?mode=admin` address only keeps the sign-in out of
sight; the protection is the password, checked on the server for each browser
session. There is one shared password (no per-user accounts), so for a public
deployment put the app behind HTTPS (for example a reverse proxy). If
`ADMIN_PASSWORD` is not set, the admin panel stays locked.

### 2. REST API

```bash
uvicorn app.api.api_app:app --reload
```

Swagger UI: http://localhost:8000/docs

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/extract` | Structured invoice/contract/general extraction |
| `POST /api/v1/ingest` | Index a PDF/DOCX/TXT into the RAG vector store (**admin only**) |
| `POST /api/v1/ingest/batch` | Index several files in one request, a folder's worth (**admin only**) |
| `POST /api/v1/chat` | Ask a grounded question (`document_id` optional, to scope to one source) |
| `POST /api/v1/compare` | Compare a concept across two ingested `document_id`s |

When `ADMIN_PASSWORD` is set, `/api/v1/ingest` and `/api/v1/ingest/batch` require it in the
`X-Admin-Password` header (when it is not set, the endpoint stays open, which
is convenient for local development only):

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "X-Admin-Password: $ADMIN_PASSWORD" \
  -F "file=@book.pdf"
```

`/api/v1/ingest/batch` takes several `files` (and optional `overwrite=true`) and
returns one result per file (`added`, `replaced`, `skipped`, `empty`,
`duplicate_name` or `failed`):

```bash
curl -X POST http://localhost:8000/api/v1/ingest/batch \
  -H "X-Admin-Password: $ADMIN_PASSWORD" \
  -F "files=@book1.pdf" -F "files=@book2.docx" -F "overwrite=false"
```

In Python code, the same is available as
`IngestionPipeline(...).ingest_directory("path/to/folder")`.

`sources[].page` in chat/compare responses is the 0-based PDF page index as
stored by the loader (the Streamlit app shows it as page + 1).

**Running the API and the Streamlit app together:** both open the same
on-disk database (`vector_database/chroma_db`). Ingest through one of them
only: the other process may not see newly added vectors until it is restarted.

### 3. Structured-extraction demo

```bash
streamlit run app/streamlit_app/extraction_demo.py
```

The original demo UI: upload an invoice or contract and get validated JSON.

### 4. Docker

```bash
docker build -t chemlib-ai .

# Library app (leave POPPLER_PATH empty in .env: poppler is installed in the image)
docker run --rm -p 8501:8501 --env-file .env \
  -v "$(pwd)/vector_database:/app/vector_database" \
  chemlib-ai streamlit run app/streamlit_app/app.py --server.address 0.0.0.0

# REST API (image default)
docker run --rm -p 8000:8000 --env-file .env \
  -v "$(pwd)/vector_database:/app/vector_database" chemlib-ai
```

The volume keeps the vector database across container restarts.

### 5. Tests

```bash
pytest -v
```

All tests use mocks (no real API calls, no Poppler/Tesseract/model downloads)
— safe to run in CI.

---

## 🖨 Scanned PDFs and OCR

Reading a PDF page by page, the loader (`src/loaders/pdf_loader.py`) decides
per page how to get its text:

```text
page → has a usable text layer? ──yes──→ read it directly (PyMuPDF / pypdf), no OCR
              │
              no (scan, empty, or garbage such as reversed Persian)
              ↓
        render the page → blank? ──yes──→ skip (no OCR call is paid for)
              │
              no
              ↓
   classify the page (src/ocr/page_type.py, cheap heuristic — no ML model)
              │
      ┌───────┼──────────────┐
      ↓       ↓               ↓
    TEXT    TABLE           FIGURE
   (prose)  (has a grid,   (diagram / chemical structure / chart / photo,
             even mixed     no table grid — NEVER reaches this branch if
             with text)     the page also has a table)
      │       │                │
      └───┬───┘                ↓
          ↓             skip: no OCR call, page kept with empty text,
          ↓             recorded as `extraction=skipped:figure` in its
          ↓             metadata and in PDFLoadReport.skipped_figure_pages
          ↓
   OCR mode "online_first" (default)         OCR mode "local_only"
   ─────────────────────────────────         ─────────────────────
   1. Azure Document Intelligence            RapidOCR (local, English)
   2. OpenRouter (vision-capable model)      (PaddleOCR if you enabled it)
   3. RapidOCR (local, English)              nothing leaves this machine
        each result must pass the quality gate (text sanity + engine confidence);
        a rejected result or an error moves on to the next engine
              │ nothing passed
              ↓
   keep the best result, flagged low quality (never silently dropped)
```

**Figure/diagram pages are skipped, tables never are.** For this MVP, a
scanned page classified as mostly a figure/diagram/chemical structure (and
with no table grid) is not sent to any OCR engine at all — this avoids
burning OCR calls (and, for the cloud engines, API cost) on content that
plain-text OCR was never going to read usefully anyway. `classify_page()` is
a deliberately simple pixel-density heuristic (no layout model): it looks for
long, unbroken dark runs (ruling lines) to detect a table grid, and checks
how much of the page the ink covers to tell running text from a smaller,
more centered figure. **A page with a table is always OCR'd**, even if it
also contains figures, and even if the table has no visible ruling lines
(that specific case is a known limitation — see below). A skipped page keeps
its place in the document (empty text, not removed), with
`extraction=skipped:figure` in its metadata, `PDFLoadReport.skipped_figure_pages`
listing every skipped page number, and a line in the loader's log — so it is
always possible to tell afterwards which pages were *intentionally* left
unread rather than lost by mistake. `PP-StructureV3` (`LAYOUT_ENGINE=ppstructure`,
see below) is a separate, heavier, opt-in mechanism that extracts real table/figure
*blocks* with a proper layout model; this heuristic is only the page-level
decision of whether to bother with full-page OCR at all.

**Choosing online or local.** Every upload form (the admin's file/ZIP/folder
forms and the user's "سند من" form) has **روش OCR برای صفحه‌های اسکن‌شده**:

| Choice | What happens | Use it for |
|---|---|---|
| آنلاین، و اگر نشد محلی (default) | Page images go to Azure or OpenRouter; if they fail or return junk, local RapidOCR reads the page | Best quality, any language (Persian needs an online engine) |
| فقط محلی | Only local engines; page images never leave the computer | English documents, confidential files, no internet/API key |

The default for new sessions is `OCR_MODE` (`online_first` unless you change it).
After indexing, the result line tells which engine read how many pages, for
example: `OCR: OpenRouter (آنلاین) ۳ صفحه، RapidOCR (محلی) ۱ صفحه`, and warns when
scanned pages could not be read at all; a separate note reports how many
pages were skipped as figures/diagrams. Answering questions still uses the
language model (OpenRouter) in both modes; "local only" concerns the OCR step.

**Missing spaces.** RapidOCR's default model often prints English without spaces
between words (`Ithasbeenknownforalongtime`), which makes the text useless for
search. `src/ocr/spacing.py` repairs such lines with `wordninja` (in
`requirements.txt`), and the quality gate treats text with implausibly long
letter runs as junk (`missing_spaces`), so a glued page is never accepted as
good. Without `wordninja` the panel shows it as not ready and local OCR pages are
flagged low quality. Documents indexed before this fix must be deleted and added again.

**Local OCR is English-only.** RapidOCR ships English/Chinese models, so it is
the fallback for English documents. Its result is accepted only if it passes the
quality gate and is mostly Latin text: a Persian page it cannot read is reported
as unread instead of being indexed as gibberish. For Persian scans use an online
engine (or opt in to the heavy PaddleOCR Persian model with
`OCR_ENGINES=azure,openrouter,rapidocr,paddle`).

* **Text layer check** (`src/ocr/quality.py`): enough letters, no private-use or
  replacement characters, not letter-by-letter, and, for Persian/English, a
  normal share of common words. Reversed Persian (a legacy-font symptom) is
  detected because reversed words like `تسا` replace `است`.
* **OCR quality gate**: the same text checks, a bit stricter
  (`OCR_MIN_QUALITY`, default 0.7), plus the engine's own confidence
  (`OCR_MIN_CONFIDENCE`). A confident but garbled result is still rejected.
* **Observability**: every page records how it was read (`extraction` =
  `text_layer`, `ocr:<engine>`, `blank`, ...). The loader logs a summary such as
  `120 pages: text layer=84, OCR=openrouter=30, rapidocr=6, blank=0, low quality=2,
  skipped figures=3,
  failed=0`, and `PDFLoader.last_report` holds the same numbers.

Setup:

| Engine | Install / configure |
|---|---|
| PyMuPDF (recommended) | `pip install pymupdf`. Faster text extraction and Poppler-free rendering. **License: AGPL-3.0** (commercial licence available from Artifex): check it suits your delivery. Without it, pypdf + Poppler are used. |
| RapidOCR (local, light) | `pip install rapidocr-onnxruntime` (in `requirements.txt`; CPU only, about 15 MB of models) |
| Azure Document Intelligence | `AZURE_DI_ENDPOINT` and `AZURE_DI_KEY` (REST, no extra package) |
| OpenRouter (vision) | `OPENROUTER_API_KEY`; the model chosen via `OPENROUTER_MODEL` must support image input |
| PaddleOCR (optional, heavy) | `pip install paddleocr paddlepaddle`, add `paddle` to `OCR_ENGINES`, `PADDLE_OCR_LANG=fa` |
| PP-StructureV3 layout (table/formula/figure) | same install as above; `LAYOUT_ENGINE=ppstructure` (default). If you hit `NotImplementedError: ConvertPirAttribute2RuntimeAttribute ... oneDNN` on CPU (common on Windows), it's already disabled by default — set `PADDLE_ENABLE_MKLDNN=true` only if your install doesn't hit that bug. `PADDLE_DEVICE=gpu` to use a GPU. |
| PaddleOCR / PP-StructureV3 on GPU (faster) | Needs an NVIDIA GPU with a matching CUDA + cuDNN install. Uninstall the CPU build first (`pip uninstall paddlepaddle`), then install the GPU build for your CUDA version from PaddlePaddle's own index, e.g. for CUDA 12.x: `pip install paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu126/` (check https://www.paddlepaddle.org.cn/en/install/quick for the index matching your CUDA version — `nvidia-smi` shows it). `paddleocr` itself stays the same package. Then set `PADDLE_DEVICE=gpu` in `.env` — this applies to both the OCR engine (`paddle` in `OCR_ENGINES`) and the `ppstructure` layout engine. `PADDLE_ENABLE_MKLDNN` is CPU-only and ignored on GPU. |

The admin panel's **وضعیت تنظیمات** shows which of these are ready. The REST API
takes the same choice: `ocr_mode=online_first|local_only` on `/api/v1/ingest` and
`/api/v1/ingest/batch`.

**Measure before trusting.** How well RapidOCR reads your scanned English pages
is not known in advance; run a real scanned book in both modes and compare the
logged summary and a few answers. Azure and OpenRouter are cloud services: check
that your network can reach them (a `403 Forbidden` from Google means the request
was blocked before reaching your key), and that Persian is supported for your
Azure resource and region.

---

## 🔤 Persian Text Preprocessing

RAG ingestion cleans every page with these steps, in order
(`src/processing/cleaners/`):

| Step | What it does |
|---|---|
| `UnicodeCleaner` | NFKC: turns presentation forms (ﻻ, ﻓ …) into normal letters, `H₂O` into `H2O` |
| `TextCleaner` | Removes control characters, normalises line endings |
| `PersianCharacterCleaner` | `ي ك ى ة ۀ` → `ی ک ی ه ه`; removes harakat, kashida and invisible bidi marks; digits `۱۲۳` / `١٢٣` → `123` (formulas like `C6H12O6` stay intact); `٫ ٬ ٪` → `. , %`; keeps a half-space only between two Persian letters |
| `PersianSpacingCleaner` | Restores half-spaces (`می شود` → `می‌شود`, `کتاب ها` → `کتاب‌ها`, `بزرگ تر` → `بزرگ‌تر`) and fixes spacing around `، ؛ ؟` |
| `LineWrapCleaner` | Joins lines a PDF broke in the middle of a sentence; keeps headings, list items, sentence ends and blank lines |
| `WhitespaceCleaner` | Collapses spaces and blank lines |

The user's question is normalised with the same character rules
(`normalize_query`, applied inside both vector stores), so a question typed with
Arabic `ي`/`ك` or Persian digits still matches the indexed text. The text sent
to the LLM as the question is left as typed.

Options: `IngestionPipeline(persian=False)` turns the Persian steps off;
`PersianCharacterCleaner(digits="persian" | "keep", remove_diacritics=False,
unify_alef=True)` changes digit style, keeps harakat, or maps `أ إ ٱ` to `ا`
(off by default). **Documents indexed before this change keep their old
spelling: delete and re-add them so they match the normalised questions.**

Not covered: PDFs whose text comes out reversed or letter by letter (a font or
extraction problem, not a spelling one), hyphenated Latin words split across
lines, and repeated page headers/footers.

---

## 🎯 Design Notes

<<<<<<< HEAD
- **OCR** is a chain, not a single engine. Fully-local options evaluated
  earlier for Persian scanned text (Tesseract, RapidOCR, PaddleOCR-VL) did not
  reach acceptable quality or speed on real scanned academic pages, so a cloud
  engine (OpenRouter, optionally Azure) stays at the end of the chain as the
  quality backstop, while cheap local extraction and the quality gate keep
  most pages away from it. OCR only runs for pages where the text layer is
  missing or unusable.
=======
- **OCR** uses Gemini Vision, not a traditional OCR engine. Several
  fully-local/free OCR options were evaluated for Persian scanned text
  (Tesseract, RapidOCR, PaddleOCR-VL) and none reached acceptable quality
  or speed for real scanned academic pages — this is a documented,
  deliberate trade-off, not an oversight. OCR is only invoked for pages
  where digital text extraction fails, so the API cost stays limited to a
  minority of pages.
- **Provider fallback**: `RAGService` tries providers in order (Gemini, then
  OpenRouter). The response reports which backup answered
  (`fallback_provider`, `fallback_model`, `failed_providers`), and the UI turns
  that into a notice; if all providers fail, `AllProvidersFailedError` lists them.
- **Private documents**: the "My documents" store (`SessionVectorStore`) is
  in-memory and never touches the shared database. Pipelines must test it with
  `is not None`, not truthiness, because an empty store is still a store.
>>>>>>> 623a52fcabb13bb6235dcffd784b29f43f8deafd
- **Embeddings** stay fully local (BGE-M3) — no per-query API cost for
  retrieval, only for LLM generation.
- **Grounding**: retrieval runs a cheap similarity-threshold check
  (`SIMILARITY_THRESHOLD` in `rag/rag_service.py`) before calling the LLM
  at all. If nothing relevant is found, the service returns a fixed
  "not enough information" response without spending an LLM call. The model
  may also declare the retrieved context insufficient; then no sources are shown.
- **Sources**: the model lists the chunk ids it used; only those chunks are
  shown as sources (all retrieved chunks if it cited none).
- **Structured output**: both extraction and RAG answers come back as
  validated Pydantic models directly from the LLM provider
  (`response_schema`), not parsed from free-text — this avoids fragile
  regex-based parsing of LLM output.
- **Interface**: the library app is right-to-left and uses the Vazirmatn font,
  loaded from a CDN (offline machines fall back to a system font). Each book is drawn
  as a periodic-table style tile, so a source is recognisable at a glance.

---

## ⚠️ Known Limitations

- "My documents" are private to one browser session but are not encrypted, and
  the relevant passages are sent to the language-model service to write answers.
- A folder can only be uploaded through the browser as a ZIP; the server-path
  option is for the admin, on the machine that runs the app.
- Chat is single-turn: earlier messages are not used to interpret a new question.
- One shared admin password; no per-user accounts or audit log.
- A document's id is derived from its file name, so two different books with
  the same file name count as the same document.
- If every OCR engine fails for a scanned page, that page is left out of the
  index; the upload result warns how many pages were unread.
- Local OCR (RapidOCR) reads English only; scanned Persian pages need an online engine.
- Tables/formulas/figures are pulled out separately only when PP-StructureV3
  is available (`LAYOUT_ENGINE=ppstructure`, on by default — requires
  `paddleocr`/`paddlepaddle` to be installed); otherwise they fall back to
  being read as plain OCR text lines.
- `src/rag/` is an older, unused RAG draft (it imports a module that no longer
  exists). The active implementation is the top-level `rag/` package.

---

## 🚀 Roadmap

- Chat memory: rewrite follow-up questions using the conversation
- Per-user accounts for admins
- Tune `SIMILARITY_THRESHOLD` and chunk size against a real, larger corpus
- Reranking, if retrieval precision needs improvement post-MVP

---

## 🇮🇷 Interface Language and Quick Guide

The app's interface is Persian (right-to-left) because its users are Persian-speaking
students; questions can be written in Persian or English. UI labels are shown in this
README as they appear on screen, followed by an English translation.

| On screen | Meaning |
|---|---|
| **کتابخانه** | Library (chat over the shared books) |
| **سند من** | My documents (private, session-only files) |
| **جست‌وجو در** / **همهٔ منابع** | Search in / All sources |
| **گفتگوی جدید** | New chat |
| **بارگذاری فایل یا پوشه** / **بارگذاری موقت** | Upload file or folder / Temporary upload |
| **پاک‌کردن سندهای من** | Clear my documents |
| **مدیریت منابع** / **گفتگو** | Manage sources / Chat (admin top bar) |
| **افزودن به کتابخانه** / **افزودن پوشه** | Add to library / Add folder |
| **منابع ایندکس‌شده** / **حذف** | Indexed sources / Delete |
| **وضعیت تنظیمات** / **خروج** | Configuration status / Sign out |

**Install and run**

```bash
pip install -r requirements.txt
<<<<<<< HEAD
cp .env .env        # سپس OPENROUTER_API_KEY و ADMIN_PASSWORD را پر کنید
=======
cp .env.example .env        # then fill in GEMINI_API_KEY and ADMIN_PASSWORD
>>>>>>> 623a52fcabb13bb6235dcffd784b29f43f8deafd
streamlit run app/streamlit_app/app.py
```

Always run from the project root. The first start downloads the BGE-M3 model and takes a few minutes.

**Users (students / professors)** open `http://localhost:8501` and land directly on the
chat. They ask in Persian or English and get the answer with the source book and page
number. Each question is searched independently, so write the concept's name in the
question itself. Users never see any option for adding files to the library.

**Library admin**

1. Open `http://localhost:8501/?mode=admin` and sign in with `ADMIN_PASSWORD`.
2. Choose **مدیریت منابع** (Manage sources) in the top bar.
3. Select one or more PDF, DOCX or TXT files and press **افزودن به کتابخانه** (Add to library). Scanned files are read with OCR and take longer.
4. To replace a file that was already added, tick the replace option. To remove one, press **حذف** (Delete) next to it.
5. To see the chat as a user would, choose **گفتگو** (Chat) in the top bar.

<<<<<<< HEAD
**روش OCR (برای صفحه‌های اسکن‌شده):** کنار هر فرم بارگذاری، دو انتخاب هست. «آنلاین، و اگر نشد محلی» (پیش‌فرض): تصویر صفحه به Azure یا OpenRouter می‌رود و اگر خطا داد یا نتیجهٔ بی‌کیفیت آمد، OCR محلی (RapidOCR) جایگزین می‌شود. «فقط محلی»: هیچ تصویری از رایانه بیرون نمی‌رود. OCR محلی سبک است و فقط برای متن **انگلیسی** مناسب است؛ برای PDF فارسی اسکن‌شده حالت آنلاین لازم است. صفحه‌هایی که خودشان متن دارند اصلاً OCR نمی‌شوند؛ صفحه‌هایی که عمدتاً شکل یا نمودار پیچیده‌اند و جدول ندارند هم اصلاً OCR نمی‌شوند (جدول‌ها همیشه OCR می‌شوند). بعد از بارگذاری، نتیجه نشان می‌دهد هر موتور چند صفحه را خوانده است. برای نصب OCR محلی: `pip install rapidocr-onnxruntime`.

**سند من (بدون کتابخانه):** بالای صفحهٔ گفتگو از «کتابخانه» به «سند من» بروید، یک فایل، چند فایل یا یک پوشهٔ ZIP‌شده را بارگذاری کنید و سؤال بپرسید. این فایل‌ها فقط در حافظهٔ همین صفحه می‌مانند، در پایگاه برداری کتابخانه ذخیره نمی‌شوند و با «پاک‌کردن سندهای من» یا بستن و تازه‌کردن صفحه از بین می‌روند. توجه: برای نوشتن پاسخ، بخش‌های مرتبط با سؤال به سرویس مدل زبانی (OpenRouter) فرستاده می‌شود. برای مقایسهٔ دو منبع هم می‌توانید همین‌جا بنویسید، مثلاً «فلان و بهمان را مقایسه کن».
=======
**Adding a folder:** under Manage sources there are two ways: the **فایل یا ZIP** (File or ZIP) tab for several files or a zipped folder, and the **پوشه روی این رایانه** (Folder on this computer) tab for a path on the machine running the app. Every PDF, DOCX and TXT inside (sub-folders included) is added, with a separate result per file.
>>>>>>> 623a52fcabb13bb6235dcffd784b29f43f8deafd

**My documents (no library needed):** at the top of the chat switch from **کتابخانه** (Library) to **سند من** (My documents), upload a file, several files, or a zipped folder, and ask questions. These files stay in the memory of that page only: they are not stored in the library's vector database and disappear with **پاک‌کردن سندهای من** (Clear my documents) or when the page is closed or refreshed. Note: to write an answer, the passages relevant to the question are sent to the language-model service (Gemini, or OpenRouter as fallback).

**Fallback model:** if Gemini does not respond (for example the free quota is used up), the app automatically uses OpenRouter and shows in the chat which model answered. This needs `OPENROUTER_API_KEY` in `.env`; restart the app after changing `.env`.

**Note:** if `ADMIN_PASSWORD` is not set, admin sign-in is disabled.

---

## 👥 Developers

Created by the **AI Builders Iran** team

> We Don't Compete. We Replace.

---

## 📄 License

MIT License
