# راهنمای Person 3: Pipeline / Integration Engineer

این فایل توضیح می‌دهد که در شاخه `feature/pipeline` چه چیزی بررسی و پیاده‌سازی شده است. هدف این است که یک توسعه‌دهنده‌ی تازه‌کار بتواند مسیر حرکت داده را دنبال کند، از تصمیم‌های طراحی دفاع کند و کد را آزمایش کند.

## A. مسئولیت من چه بود؟

تقسیم مسئولیت پروژه به شکل زیر است:

```text
Person 1:
File -> Document -> Clean -> Chunks

Person 3:
Integration / orchestration

Person 2:
Text -> Prompt -> LLM -> Schema -> Pydantic

Person 3:
final connection + output
```

`Person 1` اجزای خواندن و آماده‌سازی سند را ساخته است: `DocumentLoader` فایل را به `Document` تبدیل می‌کند، `DocumentProcessor` متن را تمیز می‌کند و `RecursiveChunker` هر `Document` را به چند chunk تقسیم می‌کند.

`Person 2` اجزای استخراج را ساخته است: `DocumentExtractor` متن و `DocumentType` را می‌گیرد، schema مناسب را انتخاب می‌کند، prompt می‌سازد و آن را به provider می‌دهد تا خروجی ساختاریافته و معتبر Pydantic تولید شود.

وظیفه‌ی `Person 3` بازنویسی این اجزا نیست. وظیفه‌ی آن اتصال درستشان است: خروجی هر مرحله باید با نوع ورودی مرحله‌ی بعد سازگار شود و نتیجه‌ی نهایی به مصرف‌کننده برگردد. بنابراین کد `DocumentPipeline` فقط orchestration انجام می‌دهد و منطق loader، cleaner، chunker، prompt، provider و schema را دوباره پیاده‌سازی نمی‌کند.

## B. پروژه را چگونه فهمیدیم؟

اول وضعیت Git و شاخه بررسی شد:

```bash
git status
git branch --show-current
```

نتیجه این بود که worktree در ابتدا clean بود و شاخه‌ی فعلی `feature/pipeline` بود. سپس تاریخچه‌ی کلی و تاریخچه‌ی مسیرهای مرتبط بررسی شد:

```bash
git log --all --oneline --decorate --graph
git log --all --reverse -- src/loaders src/processing
git log --all --reverse -- src/extraction src/schemas
git show <important-commit>
git diff
git grep -n "DocumentPipeline"
git grep -n "DocumentExtractor"
git grep -n "DocumentProcessor"
git grep -n "RecursiveChunker"
```

این بررسی نشان داد که commitهای مربوط به loaders و processing از یک بخش جدا و commitهای مربوط به extraction و schemas از بخش دیگری آمده‌اند. همچنین معلوم شد که `pipeline.py` هنوز خالی است و مثال قدیمی `README.md` با API فعلی هماهنگ نیست.

چرا فقط به `README.md` اعتماد نکردیم؟ چون README هنوز skeleton قدیمی زیر را نشان می‌دهد:

```python
run(self, file_path)
```

اما کد واقعی `DocumentExtractor.extract()` علاوه بر متن، `document_type` را هم لازم دارد. همین تفاوت کوچک، قرارداد عمومی pipeline را تعیین می‌کند. برای فهمیدن ساختار یک پروژه، باید به ترتیب زیر عمل کرد:

1. با `git status` مطمئن شویم تغییرات قبلی را خراب نمی‌کنیم.
2. با `git branch --show-current` شاخه و محدوده‌ی کار را کنترل کنیم.
3. با `git log -- <path>` بفهمیم هر subsystem چگونه و در چه commitهایی ساخته شده است.
4. با `git show` بدنه‌ی commitهای مهم را ببینیم؛ مثلاً بفهمیم آیا `chunk()` یک سند می‌گیرد یا فهرست سندها.
5. خود source را بخوانیم و signature، نوع خروجی و رفتار خطا را ثبت کنیم.
6. تست‌ها را بخوانیم، چون تست‌ها نمونه‌ی قابل‌اعتماد‌تری از استفاده‌ی واقعی API هستند.
7. پس از تغییر، با `git diff` و `git diff --check` مطمئن شویم فقط تغییرات لازم انجام شده‌اند.

به زبان ساده، boundaryهای integration از روی نام فایل‌ها حدس زده نشدند؛ از روی signatureها مشخص شدند. دیدن `DocumentLoader.load(...) -> list[Document]`، `DocumentProcessor.process(...) -> list[Document]`، `RecursiveChunker.chunk(Document) -> list[Document]` و `DocumentExtractor.extract(str, DocumentType) -> BaseModel` دقیقاً نشان داد بین کدام دو مرحله adapter لازم است.

## C. چه چیزی به چه چیزی وصل می‌شود؟

### 1. `DocumentLoader`

```python
DocumentLoader.load(file: Path | str) -> list[Document]
```

ورودی یک مسیر فایل است. `DocumentLoader` پسوند را بررسی می‌کند و به یکی از `PDFLoader`، `DOCXLoader` یا `TXTLoader` می‌فرستد. خروجی همیشه از نظر قرارداد، فهرستی از `langchain_core.documents.Document` است. هر `Document` دو بخش مهم دارد:

```text
document.page_content: str
document.metadata: dict
```

### 2. `DocumentProcessor`

```python
DocumentProcessor.process(documents: list[Document]) -> list[Document]
```

این مرحله فهرست سندها را می‌گیرد. برای هر سند، cleanerها به ترتیب اجرا می‌شوند و یک `Document` جدید با متن تمیز و metadata قبلی ساخته می‌شود. pipeline به‌صورت پیش‌فرض این زنجیره را می‌سازد:

```text
TextCleaner -> UnicodeCleaner -> WhitespaceCleaner
```

### 3. `RecursiveChunker`

```python
RecursiveChunker(
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
)

RecursiveChunker.chunk(document: Document) -> list[Document]
```

نکته‌ی مهم این است که `chunk()` یک `Document` می‌گیرد، نه `list[Document]`. بنابراین pipeline باید روی خروجی processor loop بزند:

```python
for document in processed_documents:
    chunks.extend(chunker.chunk(document))
```

اگر این loop وجود نداشته باشد، فهرست خروجی processor مستقیماً به متدی داده می‌شود که انتظار یک سند را دارد و قرارداد شکسته می‌شود. نتیجه‌ی chunk کردن هر سند دوباره `list[Document]` است؛ pipeline این فهرست‌های کوچک را به یک فهرست مسطح تبدیل می‌کند و ترتیب سندها و chunkها را نگه می‌دارد.

### 4. adapter بین Chunker و Extractor

`DocumentExtractor` یک `str` می‌خواهد، نه یک `Document`:

```python
DocumentExtractor.extract(
    document_text: str,
    document_type: DocumentType,
) -> BaseModel
```

پس adapter این است:

```text
Document
   |
   v
document.page_content
   |
   v
str
```

pipeline از `page_content` تمام chunkهای قابل‌استفاده، به همان ترتیب، متن واحد می‌سازد:

```python
document_text = "\n\n".join(
    chunk.page_content for chunk in usable_chunks
)
```

در نتیجه جریان نوع‌ها چنین است:

```text
Path | str
    |
    v
DocumentLoader.load
    |
    v
list[Document]
    |
    v
DocumentProcessor.process
    |
    v
list[Document]
    |
    v
RecursiveChunker.chunk(document)
    |
    v
list[Document]
    |
    v
chunk.page_content
    |
    v
str + DocumentType
    |
    v
DocumentExtractor.extract
    |
    v
BaseModel
```

## D. نمودار کامل معماری

```text
file path
   |
   v
DocumentLoader
   |
   v
list[Document]
   |
   v
DocumentProcessor
   |
   v
list[Document]
   |
   v
RecursiveChunker (one Document at a time)
   |
   v
list[Document] (flattened, original order)
   |
   v
join chunk.page_content
   |
   v
document_text: str
   |
   v
DocumentExtractor
   |
   v
PromptBuilder
   |
   v
LLMProvider-compatible providers
   |-- GeminiProvider
   `-- OpenRouterProvider
   |
   v
Pydantic schema selected by DocumentType
   |-- Invoice
   |-- Contract
   `-- GeneralDocument
   |
   v
validated BaseModel
   |
   v
JSON / dict
```

## E. اتصال دقیق LLM

اتصال LLM داخل `DocumentPipeline` پیاده‌سازی نشده است؛ pipeline فقط متن را آماده و آن را به interface موجود Person 2 تحویل می‌دهد. مسیر کامل این است:

1. pipeline با `DocumentLoader` فایل را به `Document`ها تبدیل می‌کند.
2. `DocumentProcessor` متن هر سند را با cleanerهای موجود تمیز می‌کند.
3. pipeline هر سند پردازش‌شده را جداگانه به `RecursiveChunker.chunk()` می‌دهد.
4. chunkها flatten می‌شوند و ترتیب آن‌ها حفظ می‌شود.
5. برای MVP فعلی، `chunk.page_content`ها دوباره به یک `document_text: str` واحد join می‌شوند.
6. `DocumentPipeline` این دو مقدار را صدا می‌زند:

   ```python
   extractor.extract(
       document_text=document_text,
       document_type=document_type,
   )
   ```

7. `DocumentExtractor` با `DocumentType` schema مناسب را انتخاب می‌کند: `Invoice`، `Contract` یا `GeneralDocument`.
8. `PromptBuilder` prompt را از نوع سند و متن می‌سازد.
9. `DocumentExtractor` prompt و schema را به provider می‌دهد:

   ```python
   provider.extract(prompt=prompt, schema=schema)
   ```

10. `GeminiProvider` یا `OpenRouterProvider` پاسخ structured را از LLM می‌گیرد.
11. پاسخ با Pydantic به مدل معتبر تبدیل می‌شود و همان `BaseModel` به pipeline برمی‌گردد.
12. مصرف‌کننده می‌تواند مدل را به dict یا JSON تبدیل کند.

`DocumentExtractor` فهرستی از providerها می‌گیرد. provider اول primary است و اگر `extract()` آن exception بدهد، provider بعدی امتحان می‌شود. اگر همه fail شوند، extractor یک `RuntimeError` شامل خطاهای providerها می‌دهد. این fallback در Person 2 از قبل وجود داشت و pipeline آن را پنهان یا تکرار نمی‌کند.

providerها کلید را از environment می‌خوانند؛ نمونه‌ها:

```text
GEMINI_API_KEY
OPENROUTER_API_KEY
OPENROUTER_MODEL
```

هیچ API keyای در source یا این مستندات hard-code نشده است.

## F. تصمیم مربوط به چند chunk

### پیاده‌سازی فعلی (CURRENT)

pipeline برای هر chunk یک `Invoice` یا `Contract` کامل استخراج نمی‌کند. همه‌ی chunkهای non-empty را به ترتیب اصلی join می‌کند و فقط یک بار `DocumentExtractor.extract()` را صدا می‌زند.

این تصمیم مهم است، چون مثلاً `invoice_number` ممکن است در chunk اول و `total` در chunk سوم باشد. اگر روی هر chunk جداگانه schema کامل را اجرا کنیم، بیشتر chunkها مدل ناقص می‌سازند، Pydantic validation fail می‌شود یا اطلاعات جدا از هم باقی می‌ماند و قابل ترکیب مطمئن نیست.

### محدودیت

برای سندهای بسیار بزرگ، join کردن کل متن ممکن است از context window مدل LLM بزرگ‌تر شود. این محدودیت عمداً در MVP با یک subsystem پیچیده پوشانده نشده است.

### گزینه‌های آینده (FUTURE)

در نسخه‌های بعد می‌توان از این روش‌ها استفاده کرد:

- partial schemas برای استخراج فقط بخشی از فیلدها در هر chunk؛
- per-chunk extraction همراه با aggregation معتبر؛
- batching برای کنترل اندازه‌ی درخواست‌ها؛
- map-reduce extraction برای استخراج توزیع‌شده و سپس یکی‌کردن نتیجه؛
- لایه‌ی aggregation با قواعد مشخص برای conflict و missing fields.

این‌ها جزو implementation فعلی نیستند.

## G. فایل‌های ایجادشده و تکمیل‌شده در scope Person 3

فایل‌هایی که واقعاً در این task جدید ایجاد شدند، `tests/test_pipeline.py` و `README_PERSON3_PIPELINE.md` هستند. چهار فایل موجود و خالی (`src/pipeline/pipeline.py`، `src/pipeline/__init__.py`، `src/utils/json_utils.py` و `src/utils/__init__.py`) تکمیل شدند و در بخش H به‌عنوان modified آمده‌اند.

### `src/pipeline/pipeline.py`

**Purpose:** orchestration بین loader، processor، chunker و extractor.

**Responsibility:** دریافت `file_path` و `DocumentType`، اجرای مراحل محلی، ساختن `str` از chunkها و برگرداندن مدل Pydantic.

**Who uses it:** مصرف‌کننده‌ی application یا `src.pipeline`.

**Returns:** یک `BaseModel` که extractor برگردانده است.

### `src/pipeline/__init__.py`

**Purpose:** public export برای import تمیز.

**Responsibility:** export کردن `DocumentPipeline`.

**Who uses it:** مصرف‌کننده‌ای که می‌نویسد `from src.pipeline import DocumentPipeline`.

**Returns:** مقدار جدیدی تولید نمی‌کند؛ فقط symbol را export می‌کند.

### `src/utils/json_utils.py`

**Purpose:** serialization استاندارد مدل‌های Pydantic v2.

**Responsibility:** ارائه‌ی `model_to_dict()` و `model_to_json()` با API native Pydantic.

**Who uses it:** application یا caller pipeline پس از دریافت result.

**Returns:** به‌ترتیب `dict[str, Any]` سازگار با JSON و `str` JSON.

### `src/utils/__init__.py`

**Purpose:** public export ابزارهای JSON.

**Responsibility:** export کردن دو helper.

**Who uses it:** مصرف‌کننده‌ای که از `src.utils` import می‌کند.

**Returns:** مقدار جدیدی تولید نمی‌کند؛ فقط helperها را export می‌کند.

### `tests/test_pipeline.py`

**Purpose:** آزمون integration مربوط به Person 3 بدون API واقعی.

**Responsibility:** اتصال stageها، ترتیب chunkها، انتقال `DocumentType`، propagation خطا، مسیر end-to-end محلی و serialization را بررسی می‌کند.

**Who uses it:** توسعه‌دهنده و CI با اجرای `pytest`.

**Returns:** نتیجه‌ی pass/fail آزمون‌ها.

### `README_PERSON3_PIPELINE.md`

**Purpose:** راهنمای فارسی beginner-friendly برای دفاع و نگهداری implementation.

**Responsibility:** توضیح investigation، قراردادها، معماری، تصمیم چند chunk، کد نهایی، تست‌ها و limitationها.

**Who uses it:** توسعه‌دهنده، reviewer و اعضای تیم.

**Returns:** artifact اجرایی نیست؛ مستندات پروژه است.

فایل `config.py` ایجاد نشد، چون repository هیچ configuration module موجودی نداشت و برای integration فعلی نیازی به abstraction جدید نبود. `chunk_size` و `chunk_overlap` از طریق inject کردن `RecursiveChunker` قابل تنظیم‌اند و provider/model/key behavior از قبل داخل providerها و environment variables مدیریت می‌شود.

## H. همه‌ی فایل‌های تغییرکرده

در این کار فقط فایل‌های owned by Person 3 ایجاد یا تکمیل شدند:

### `src/pipeline/pipeline.py`

**Before:** فایل خالی بود.

**After:** `DocumentPipeline` با `run(file_path, document_type)`، dependency injection برای `extractor`، default processing components، loop روی اسناد و chunkها، adapter متنی و خطاهای empty stage اضافه شد.

**Why:** این فایل محل اتصال خروجی Person 1 به ورودی Person 2 است.

**Dependencies:** `DocumentLoader`، `DocumentProcessor`، `RecursiveChunker`، cleaners و `DocumentExtractor`.

### `src/pipeline/__init__.py`

**Before:** خالی بود.

**After:** `DocumentPipeline` را export می‌کند.

**Why:** import عمومی کوتاه و پایدار فراهم می‌کند.

### `src/utils/json_utils.py`

**Before:** خالی بود.

**After:** `model_to_dict()` و `model_to_json()` اضافه شد.

**Why:** خروجی Pydantic pipeline باید بدون serialize دستی به dict/JSON تبدیل شود.

### `src/utils/__init__.py`

**Before:** خالی بود.

**After:** helperهای JSON را export می‌کند.

**Why:** public utility API فراهم می‌کند.

### `tests/test_pipeline.py`

**Before:** وجود نداشت.

**After:** 10 آزمون integration و utility اضافه شد.

**Why:** قراردادهای واقعی Person 1 و Person 2 باید بدون network call تست شوند.

هیچ فایل Person 1 یا Person 2 تغییر نکرده است. بنابراین اصلاحات مربوط به inconsistencyهای pre-existing در این فهرست وجود ندارد.

## I. کد نهایی فایل‌های Person 3

کد زیر عین محتوای نهایی فایل‌های اجرایی Person 3 است.

### `src/pipeline/pipeline.py`

```python
from pathlib import Path

from langchain_core.documents import Document
from pydantic import BaseModel

from src.extraction.extractor import DocumentExtractor
from src.loaders.document_loader import DocumentLoader
from src.processing.chunking.recursive import RecursiveChunker
from src.processing.pipeline import DocumentProcessor
from src.processing.cleaners import (
    TextCleaner,
    UnicodeCleaner,
    WhitespaceCleaner,
)
from src.schemas.common import DocumentType


class DocumentPipeline:
    """Coordinate local document processing and structured extraction.

    The extractor is required because constructing a real extractor also
    requires at least one configured LLM provider. Processing components have
    useful local defaults and can be replaced in tests or applications.
    """

    def __init__(
        self,
        extractor: DocumentExtractor,
        processor: DocumentProcessor | None = None,
        chunker: RecursiveChunker | None = None,
    ) -> None:
        self.loader = DocumentLoader
        self.processor = processor or DocumentProcessor(
            cleaners=[
                TextCleaner(),
                UnicodeCleaner(),
                WhitespaceCleaner(),
            ]
        )
        self.chunker = chunker or RecursiveChunker()
        self.extractor = extractor

    def run(
        self,
        file_path: str | Path,
        document_type: DocumentType,
    ) -> BaseModel:
        """Load, process, chunk, and extract one logical document.

        All usable chunks are joined in their original order and sent to the
        extractor once. This is the safe MVP behavior for complete schemas
        such as ``Invoice`` and ``Contract``.
        """
        if not isinstance(document_type, DocumentType):
            raise ValueError(f"Unsupported document type: {document_type}")

        documents = self.loader.load(file_path)
        if not documents:
            raise ValueError("Document loader returned no documents.")

        processed_documents = self.processor.process(documents)
        if not processed_documents:
            raise ValueError("Document processor returned no documents.")

        chunks: list[Document] = []
        for document in processed_documents:
            document_chunks = self.chunker.chunk(document)
            if document_chunks:
                chunks.extend(document_chunks)

        usable_chunks = [
            chunk
            for chunk in chunks
            if isinstance(chunk.page_content, str)
            and chunk.page_content.strip()
        ]
        if not usable_chunks:
            raise ValueError("Chunker produced no usable document text.")

        document_text = "\n\n".join(
            chunk.page_content for chunk in usable_chunks
        )
        if not document_text.strip():
            raise ValueError("Document text is empty after processing.")

        return self.extractor.extract(
            document_text=document_text,
            document_type=document_type,
        )
```

### توضیح از بالا به پایین

- `Path` اجازه می‌دهد API هم `str` و هم `Path` را بپذیرد.
- `Document` برای type annotation فهرست chunkها و `BaseModel` برای نوع خروجی extractor است.
- importهای Person 1 و Person 2 فقط برای اتصال استفاده می‌شوند؛ منطق آن‌ها کپی نشده است.
- constructor، `extractor` را اجباری می‌گیرد چون provider واقعی به credential نیاز دارد و نباید pipeline خودش API client بسازد.
- `processor` و `chunker` اختیاری‌اند تا اجرای معمول default ساده داشته باشد و تست بتواند fake یا recorder inject کند.
- `self.loader = DocumentLoader` به‌صورت class نگه داشته شده، چون `DocumentLoader.load` از قبل `classmethod` و بدون state است؛ wrapper یا object اضافی لازم نیست.
- default cleanerها به ترتیب `TextCleaner`، `UnicodeCleaner` و `WhitespaceCleaner` هستند.
- `run()` ابتدا loader را صدا می‌زند و خطای loader، مانند unsupported extension یا خطای خواندن فایل، را پنهان نمی‌کند.
- `run()` قبل از I/O بررسی می‌کند که `document_type` واقعاً یکی از مقدارهای `DocumentType` باشد.
- فهرست خالی loader و processor با پیام واضح متوقف می‌شود.
- loop روی `processed_documents` لازم است چون chunker فقط یک `Document` می‌گیرد.
- `chunks.extend(...)` فهرست خروجی هر document را flatten می‌کند و ترتیب طبیعی را نگه می‌دارد.
- `usable_chunks` chunkهای خالی یا دارای `page_content` غیررشته‌ای را وارد prompt نمی‌کند.
- join، adapter بین `Document` و `str` است و separator دو newline مرز chunkها را حفظ می‌کند.
- extractor فقط یک بار صدا زده می‌شود تا schema کامل بین chunkها ناقص نشود.
- مقدار برگشتی بدون تغییر return می‌شود؛ بنابراین همان validated Pydantic model در اختیار caller است.
- exceptionهای extractor و providerها catch نمی‌شوند، چون fallback و error reporting متعلق به `DocumentExtractor` است.

### `src/pipeline/__init__.py`

```python
from .pipeline import DocumentPipeline

__all__ = ["DocumentPipeline"]
```

این فایل symbol اصلی package را public می‌کند تا caller به مسیر داخلی `pipeline.py` وابسته نباشد.

### `src/utils/json_utils.py`

```python
from typing import Any

from pydantic import BaseModel


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic v2 model to JSON-compatible Python values."""
    if not isinstance(model, BaseModel):
        raise TypeError("model must be a Pydantic BaseModel instance.")
    return model.model_dump(mode="json")


def model_to_json(model: BaseModel, **kwargs: Any) -> str:
    """Serialize a Pydantic v2 model to JSON."""
    if not isinstance(model, BaseModel):
        raise TypeError("model must be a Pydantic BaseModel instance.")
    return model.model_dump_json(**kwargs)
```

`model_to_dict` از `model_dump(mode="json")` استفاده می‌کند تا چیزهایی مانند `date` و `Enum` به مقدار JSON-compatible تبدیل شوند. `model_to_json` مستقیماً `model_dump_json` را استفاده می‌کند. هیچ provider setting یا secretای در این helperها serialize نمی‌شود؛ فقط خود model داده می‌شود.

### `src/utils/__init__.py`

```python
from .json_utils import model_to_dict, model_to_json

__all__ = ["model_to_dict", "model_to_json"]
```

این export باعث می‌شود استفاده‌ی caller ساده باشد:

```python
from src.utils import model_to_dict, model_to_json
```

### `tests/test_pipeline.py`

```python
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
```

این listing شامل تمام importها، helperها، fakeها، assertions و testهای فایل است؛ snippet حذف‌شده‌ای وجود ندارد.

### `README_PERSON3_PIPELINE.md`

این فایل خودش همان مستندی است که اکنون می‌خوانید؛ بنابراین درج دوباره‌ی محتوای کامل آن داخل خودش self-reference بی‌نهایت ایجاد می‌کند. مسیر کامل و محتوای نهایی آن همین فایل است و بخش‌های A تا O کل محتوای آن را تشکیل می‌دهند.

## J. walkthrough خط‌به‌خط

### `DocumentPipeline`

- imports وابستگی‌های واقعی stageها را وارد می‌کنند.
- class definition یک orchestration object می‌سازد.
- constructor dependencyهای قابل‌تعویض را ذخیره می‌کند.
- `extractor` اجباری است تا testها API واقعی `extract(document_text, document_type)` را نشان دهند.
- default processor سه cleaner واقعی دارد.
- default chunker همان implementation واقعی Person 1 است.
- `run()` ابتدا loading، سپس processing، سپس chunking را اجرا می‌کند.
- loop chunker برای هر `Document` جداگانه لازم است.
- adapter با خواندن `page_content` متن را برای extractor می‌سازد.
- extraction یک بار انجام می‌شود.
- return همان result مدل Pydantic است.
- خطاهای lower layer پنهان نمی‌شوند؛ فقط empty resultهایی که pipeline نمی‌تواند به مرحله بعد بدهد، پیام واضح می‌گیرند.

### `json_utils`

- `BaseModel` ورودی را محدود می‌کند.
- `isinstance` خطای استفاده‌ی اشتباه را زود و روشن نشان می‌دهد.
- `model_dump(mode="json")` dict مناسب JSON می‌سازد.
- `model_dump_json` JSON native Pydantic تولید می‌کند.

### `test_pipeline.py`

- imports ابزارهای test و مدل‌های واقعی را فراهم می‌کنند.
- `FakeExtractor` نتیجه و آرگومان‌ها را ثبت می‌کند.
- `RecordingProcessor` ثابت می‌کند loader خروجی خود را به processor داده است.
- `RecordingChunker` ثابت می‌کند processor output به‌صورت document-by-document و ordered به chunker داده شده است.
- `test_pipeline_happy_path...` مسیر موفق، adapter و `DocumentType.INVOICE` را بررسی می‌کند.
- `test_multiple_documents...` flatten شدن چند سند و چند chunk و حفظ ترتیب را بررسی می‌کند و با `DocumentType.CONTRACT` نشان می‌دهد نوع سند تغییرپذیر است.
- `test_real_loader...` اتصال واقعی local processing را بدون network ثابت می‌کند.
- دو test خطای پسوند پشتیبانی‌نشده و فایل مفقود را بررسی می‌کنند.
- testهای empty loader و empty chunk تضمین می‌کنند extractor بی‌دلیل صدا زده نمی‌شود.
- test JSON serialization خروجی dict و JSON و تبدیل date/enum را بررسی می‌کند.
- test آخر ترتیب default cleanerها و حذف control character و whitespace را به‌صورت integration بررسی می‌کند.

## K. مثال استفاده

providerها credential را از environment می‌گیرند. کلید واقعی را در کد قرار ندهید:

```powershell
$env:GEMINI_API_KEY = "your-gemini-key"
$env:OPENROUTER_API_KEY = "your-openrouter-key"
$env:OPENROUTER_MODEL = "your-model-name"
```

### Invoice با Gemini

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

### Contract با fallback Gemini و OpenRouter

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

اگر Gemini fail کند، `DocumentExtractor` provider دوم را امتحان می‌کند. برای این مثال environment هر دو provider باید آماده باشد. برای تغییر اندازه‌ی chunk، `RecursiveChunker(chunk_size=..., chunk_overlap=...)` را به constructor `DocumentPipeline` inject کنید.

## L. توضیح تست‌ها

تست‌ها عمدتاً fake هستند، چون unit test نباید API پولی یا شبکه‌ی خارجی را صدا بزند. fake فقط قرارداد را اجرا می‌کند: `extract(document_text: str, document_type: DocumentType) -> Invoice`.

پوشش اضافه‌شده:

- happy path و return شدن همان Pydantic result؛
- انتقال loader به processor؛
- انتقال processor به chunker؛
- چند document و چند chunk؛
- flatten و حفظ ترتیب؛
- تبدیل `Document.page_content` به `str`؛
- انتقال دقیق `DocumentType`؛
- خطای extension پشتیبانی‌نشده؛
- خطای فایل مفقود بر اساس رفتار واقعی `TXTLoader`؛
- document type نامعتبر؛
- loader یا chunker خالی؛
- default cleaners؛
- dict و JSON serialization.

تست end-to-end-style از مسیر واقعی زیر استفاده می‌کند:

```text
temporary/sample.txt
    -> real DocumentLoader
    -> real TextCleaner / UnicodeCleaner / WhitespaceCleaner
    -> real DocumentProcessor
    -> real RecursiveChunker
    -> FakeExtractor
    -> valid Invoice
```

دستورهای validation اجراشده:

```bash
python -m compileall src
python -m pytest
python -m pytest --basetemp .pytest-temp
git diff --check
```

اولین اجرای `python -m pytest` روی این ماشین با `WinError 5` در ساخت `tmp_path` داخل global temp folder متوقف شد؛ 14 test pass شد و 3 test در setup خطا گرفتند. این مشکل permission محیط بود، نه assertion یا exception جدید pipeline. با `--basetemp .pytest-temp` که temp را داخل repository قرار داد، نتیجه‌ی نهایی:

```text
============================= 18 passed in 4.32s =============================
```

هیچ testی API واقعی Gemini یا OpenRouter را فراخوانی نکرد.

## M. خلاصه‌ی فایل‌های تغییرکرده

| File | Created/Modified | Purpose |
|---|---|---|
| `src/pipeline/pipeline.py` | Modified (خالی بود) | orchestration اصلی |
| `src/pipeline/__init__.py` | Modified (خالی بود) | export `DocumentPipeline` |
| `src/utils/json_utils.py` | Modified (خالی بود) | Pydantic dict/JSON serialization |
| `src/utils/__init__.py` | Modified (خالی بود) | export utilityها |
| `tests/test_pipeline.py` | Created | integration و utility tests |
| `README_PERSON3_PIPELINE.md` | Created | مستندات کامل Person 3 |

خلاصه‌ی سبک `git diff --stat` برای تغییرات Person 3:

```text
4 existing empty source files completed
1 new test module added
1 new Persian documentation file added
0 Person 1/Person 2 files changed
```

## N. مشکلات و محدودیت‌های شناخته‌شده

### Pre-existing

- `README.md` مثال قدیمی `run(file_path)` را نشان می‌دهد، در حالی که API واقعی extractor به `document_type` نیاز دارد.
- `src/extraction/providers/openrouter_provider.py` از نظر runtime همان متد `extract(prompt, schema)` را دارد، اما از `LLMProvider` ارث‌بری نمی‌کند؛ به همین دلیل از نظر type contract ناسازگار است، هرچند `DocumentExtractor` در runtime فقط متد را صدا می‌زند. برای scope Person 3 تغییرش ندادیم.
- `src/processing/__init__.py` در `__all__` یک comma کم دارد و دو رشته به هم چسبیده‌اند؛ این موضوع export wildcard را خراب می‌کند، اما importهای مستقیم فعلی pipeline را متوقف نمی‌کند. برای جلوگیری از تغییر غیرمرتبط دست‌نخورده ماند.
- `requirements.txt` خالی است، در حالی که source به Pydantic، LangChain، provider SDKها و pytest نیاز دارد. در محیط فعلی dependencyهای runtime موجود بودند؛ فقط `pytest` برای validation نصب شد.
- `TXTLoader` خطای پایین‌دستی missing file را در `RuntimeError("Error loading ...")` wrap می‌کند؛ pipeline آن را پنهان نمی‌کند.

### محدودیت implementation جدید

- join کردن تمام chunkها برای سند خیلی بزرگ ممکن است از context window عبور کند.
- partial-schema aggregation یا map-reduce هنوز پیاده‌سازی نشده است.
- configuration module جدید ایجاد نشده؛ تنظیمات موجود providerها از environment می‌آیند و chunking با dependency injection قابل تنظیم است.
- pipeline برای ساخت `DocumentLoader` wrapper ندارد، چون `DocumentLoader.load` از قبل `classmethod` بدون state است.

## O. قدم بعدی چیست؟

پس از review این implementation، ترتیب منطقی کارهای بعدی چنین است:

1. یک PDF واقعی و یک DOCX واقعی را به‌صورت manual test اجرا کنید.
2. با credential معتبر، یک test دستی Gemini یا OpenRouter انجام دهید؛ این کار نباید وارد normal automated tests شود.
3. `git diff` و `git diff --check` را review کنید.
4. تغییرات Person 3 را با commit message مناسب commit کنید.
5. شاخه‌ی `feature/pipeline` را push کنید.
6. Pull Request باز کنید.

در این task هیچ push، merge، rebase یا Pull Requestی انجام نشده است.
