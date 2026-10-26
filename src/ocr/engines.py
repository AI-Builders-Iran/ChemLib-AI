"""OCR engines behind one interface, tried in priority order by ``OCRPipeline``.

Online (the page image is sent to a cloud service):

* ``azure``: Azure AI Document Intelligence "prebuilt-read" over REST (needs an
  Azure resource: ``AZURE_DI_ENDPOINT`` and ``AZURE_DI_KEY``).
* ``openrouter``: a vision-capable model routed through OpenRouter (needs
  ``OPENROUTER_API_KEY``; the model chosen via ``OPENROUTER_MODEL`` must
  support image input).

Local (nothing leaves the machine):

* ``rapidocr``: RapidOCR on ONNX Runtime. Light (pip only, CPU, small models)
  but English/Chinese only, so use it for English documents.
* ``paddle``: PaddleOCR with a Persian model. Heavy; opt-in via ``OCR_ENGINES``.

An engine that is not installed or configured is simply skipped.
Selection and order: ``OCR_ENGINES`` (default ``azure,openrouter,rapidocr``); which
group goes first is decided by the OCR mode (see ``pipeline.build_default_pipeline``).
"""

from __future__ import annotations

import base64
import importlib.util
import io
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from statistics import median

from .spacing import restore_english_spaces

logger = logging.getLogger(__name__)

DEFAULT_ENGINE_ORDER = "azure,openrouter,rapidocr"

OCR_PROMPT = (
    "Transcribe all text visible in this image exactly as written. "
    "The text may be in Persian (Farsi) and/or English, or a mix of both. "
    "Preserve line breaks where meaningful. Do not translate, summarize, "
    "or add any commentary — output only the transcribed text."
)


@dataclass
class EngineOutput:
    text: str
    confidence: float | None = None  # 0..1 when the engine reports one


class OCREngine(ABC):
    name: str
    online: bool = True  # True: the page image is sent to a cloud service
    english_only: bool = False  # True: reads English (Latin) text only


    @abstractmethod
    def unavailable_reason(self) -> str | None:
        """None when ready to use; otherwise why not (not installed / not configured)."""

    @abstractmethod
    def recognize(self, image) -> EngineOutput:
        """OCR one PIL image. May raise; the pipeline moves on to the next engine."""

    def available(self) -> bool:
        return self.unavailable_reason() is None


# ---------------------------------------------------------------------------
# OpenRouter (vision-capable model)
# ---------------------------------------------------------------------------

class OpenRouterOCREngine(OCREngine):
    name = "openrouter"

    def __init__(self, provider_factory=None, attempts: int = 3, retry_delay: float = 5.0, sleep=time.sleep):
        self._provider_factory = provider_factory
        self._provider = None
        self._attempts = attempts
        self._retry_delay = retry_delay
        self._sleep = sleep

    def unavailable_reason(self) -> str | None:
        if self._provider_factory is None and not os.getenv("OPENROUTER_API_KEY"):
            return "OPENROUTER_API_KEY is not set"
        return None

    def recognize(self, image) -> EngineOutput:
        from rag.schemas import OCRResult

        if self._provider is None:
            if self._provider_factory is not None:
                self._provider = self._provider_factory()
            else:
                from src.extraction.providers.openrouter_provider import (
                    OCR_MAX_TOKENS,
                    OpenRouterProvider,
                    env_int,
                )

                self._provider = OpenRouterProvider(max_tokens=env_int("OCR_LLM_MAX_TOKENS", OCR_MAX_TOKENS))

        for attempt in range(1, self._attempts + 1):
            try:
                result = self._provider.extract_image(image=image, schema=OCRResult, prompt=OCR_PROMPT)
                return EngineOutput(text=(result.text or "").strip())
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenRouter OCR attempt %d/%d failed: %s", attempt, self._attempts, exc)
                if attempt == self._attempts or not getattr(exc, "retryable", True):
                    raise  # out of attempts, or a retry cannot help (402/401/403/400)
                self._sleep(self._retry_delay * attempt)  # backoff
        raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# Azure AI Document Intelligence (REST, no SDK)
# ---------------------------------------------------------------------------

class AzureDocumentIntelligenceEngine(OCREngine):
    name = "azure"

    def __init__(
        self,
        endpoint: str | None = None,
        key: str | None = None,
        api_version: str | None = None,
        session=None,
        sleep=time.sleep,
        poll_interval: float = 1.0,
        timeout: float = 120.0,
    ):
        self._endpoint = (endpoint or os.getenv("AZURE_DI_ENDPOINT") or "").rstrip("/")
        self._key = key or os.getenv("AZURE_DI_KEY") or ""
        self._api_version = api_version or os.getenv("AZURE_DI_API_VERSION") or "2024-11-30"
        self._session = session
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._timeout = timeout

    def unavailable_reason(self) -> str | None:
        if not self._endpoint or not self._key:
            return "AZURE_DI_ENDPOINT / AZURE_DI_KEY are not set"
        return None

    def recognize(self, image) -> EngineOutput:
        session = self._session
        if session is None:
            import requests

            session = self._session = requests.Session()

        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        headers = {"Ocp-Apim-Subscription-Key": self._key}

        response = session.post(
            f"{self._endpoint}/documentintelligence/documentModels/prebuilt-read:analyze",
            params={"api-version": self._api_version},
            headers=headers,
            json={"base64Source": base64.b64encode(buffer.getvalue()).decode("ascii")},
            timeout=60,
        )
        if response.status_code != 202:
            raise RuntimeError(f"Azure Document Intelligence returned HTTP {response.status_code}")
        operation_url = response.headers["Operation-Location"]

        waited = 0.0
        while True:
            poll = session.get(operation_url, headers=headers, timeout=60)
            poll.raise_for_status()
            body = poll.json()
            status = body.get("status")
            if status == "succeeded":
                return self._parse(body.get("analyzeResult", {}))
            if status == "failed":
                raise RuntimeError(f"Azure Document Intelligence analysis failed: {body.get('error')}")
            if waited >= self._timeout:
                raise TimeoutError("Azure Document Intelligence did not finish in time")
            self._sleep(self._poll_interval)
            waited += self._poll_interval

    @staticmethod
    def _parse(result: dict) -> EngineOutput:
        lines: list[str] = []
        confidences: list[float] = []
        for page in result.get("pages", []):
            lines.extend(line.get("content", "") for line in page.get("lines", []))
            confidences.extend(w["confidence"] for w in page.get("words", []) if "confidence" in w)

        text = "\n".join(lines) if lines else result.get("content", "")
        confidence = sum(confidences) / len(confidences) if confidences else None
        return EngineOutput(text=text.strip(), confidence=confidence)


# ---------------------------------------------------------------------------
# PaddleOCR (local)
# ---------------------------------------------------------------------------

def _is_rtl(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    arabic = sum(1 for c in letters if "\u0600" <= c <= "\u06ff")
    return bool(letters) and arabic >= len(letters) / 2


def _item(box, text, score) -> tuple[float, float, float, str, float] | None:
    """(x centre, y centre, height, text, score) for one recognised text box."""
    if not text or not str(text).strip():
        return None
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return (sum(xs) / len(xs), sum(ys) / len(ys), max(ys) - min(ys), str(text).strip(), float(score))


def _parse_paddle(raw) -> list[tuple[float, float, float, str, float]]:
    """Normalise PaddleOCR output (2.x and 3.x layouts) to (x, y, height, text, score)."""
    items = []

    for page in raw or []:
        if page is None:
            continue
        if hasattr(page, "get") and page.get("rec_texts") is not None:  # 3.x: dict-like per image
            boxes = page.get("rec_polys")
            if boxes is None:
                boxes = page.get("dt_polys")
            entries = zip(boxes, page["rec_texts"], page["rec_scores"])
        else:  # 2.x: [[box, (text, score)], ...]
            entries = ((entry[0], entry[1][0], entry[1][1]) for entry in page)
        items.extend(item for item in (_item(*entry) for entry in entries) if item)
    return items


def _parse_rapid(raw) -> list[tuple[float, float, float, str, float]]:
    """Normalise RapidOCR output: ``(result, elapse)`` with ``[box, text, score]`` rows
    (rapidocr_onnxruntime), or an object with boxes/txts/scores (rapidocr 2+)."""
    if raw is None:
        return []
    if hasattr(raw, "txts"):
        if raw.txts is None:
            return []
        entries = zip(raw.boxes, raw.txts, raw.scores)
    else:
        rows = raw[0] if isinstance(raw, tuple) else raw
        entries = rows or []
    return [item for item in (_item(*entry) for entry in entries) if item]


def order_text_items(items) -> tuple[str, float | None]:
    """Reading order: rows top to bottom; inside a row right-to-left for Persian."""
    if not items:
        return "", None

    typical_height = median(item[2] for item in items) or 1.0
    rows: list[list[tuple]] = []
    for item in sorted(items, key=lambda i: i[1]):
        if rows and abs(item[1] - sum(r[1] for r in rows[-1]) / len(rows[-1])) < 0.5 * typical_height:
            rows[-1].append(item)
        else:
            rows.append([item])

    lines = []
    for row in rows:
        rtl = _is_rtl(" ".join(i[3] for i in row))
        row.sort(key=lambda i: i[0], reverse=rtl)
        lines.append(" ".join(i[3] for i in row))

    total = sum(len(i[3]) for i in items)
    confidence = sum(i[4] * len(i[3]) for i in items) / total if total else None
    return "\n".join(lines), confidence


class PaddleOCREngine(OCREngine):
    name = "paddle"
    online = False

    def __init__(self, lang: str | None = None, engine=None):
        self._lang = lang or os.getenv("PADDLE_OCR_LANG") or "fa"
        self._engine = engine  # injectable for tests

    def unavailable_reason(self) -> str | None:
        if self._engine is not None:
            return None
        if importlib.util.find_spec("paddleocr") is None or importlib.util.find_spec("paddle") is None:
            return "paddleocr / paddlepaddle are not installed"
        return None

    def recognize(self, image) -> EngineOutput:
        import numpy as np

        if self._engine is None:
            from src.utils.paddle_env import set_paddle_env_flags

            set_paddle_env_flags()
            from paddleocr import PaddleOCR

            kwargs = {"lang": self._lang}
            device = os.getenv("PADDLE_DEVICE")
            if device:
                kwargs["device"] = device
            logger.info("OCR: Initializing PaddleOCR model...")
            started = time.monotonic()
            try:
                self._engine = PaddleOCR(**kwargs)
            except TypeError:
                # Older/newer paddleocr releases may not accept the device kwarg at all.
                logger.info("PaddleOCR doesn't accept a device kwarg on this install; using defaults")
                self._engine = PaddleOCR(lang=self._lang)
            logger.info("OCR: PaddleOCR model initialized in %.2fs", time.monotonic() - started)
        else:
            logger.debug("OCR: Reusing initialized PaddleOCR engine")

        array = np.array(image.convert("RGB"))
        raw = self._engine.predict(array) if hasattr(self._engine, "predict") else self._engine.ocr(array, cls=True)

        text, confidence = order_text_items(_parse_paddle(raw))
        return EngineOutput(text=text, confidence=confidence)


class RapidOCREngine(OCREngine):
    """Light local OCR (ONNX Runtime, CPU). English/Chinese models: for English documents."""

    name = "rapidocr"
    online = False
    english_only = True

    def __init__(self, engine=None, segmenter=None):
        self._engine = engine  # injectable for tests
        self._segmenter = segmenter

    def unavailable_reason(self) -> str | None:
        if self._engine is not None:
            return None
        if importlib.util.find_spec("rapidocr_onnxruntime") is None and importlib.util.find_spec("rapidocr") is None:
            return "rapidocr-onnxruntime is not installed (pip install rapidocr-onnxruntime)"
        return None

    def recognize(self, image) -> EngineOutput:
        import numpy as np

        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError:
                from rapidocr import RapidOCR

            logger.info("OCR: Initializing RapidOCR model...")
            started = time.monotonic()
            self._engine = RapidOCR()
            logger.info("OCR: RapidOCR model initialized in %.2fs", time.monotonic() - started)
        else:
            logger.debug("OCR: Reusing initialized RapidOCR engine")

        text, confidence = order_text_items(_parse_rapid(self._engine(np.array(image.convert("RGB")))))
        # This model often drops the spaces between English words; put them back.
        return EngineOutput(text=restore_english_spaces(text, self._segmenter), confidence=confidence)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

_ENGINE_CLASSES: dict[str, type[OCREngine]] = {
    "azure": AzureDocumentIntelligenceEngine,
    "openrouter": OpenRouterOCREngine,
    "rapidocr": RapidOCREngine,
    "paddle": PaddleOCREngine,
}


def _configured_names() -> list[str]:
    raw = os.getenv("OCR_ENGINES") or DEFAULT_ENGINE_ORDER
    names = [n.strip().lower() for n in raw.split(",") if n.strip()]
    unknown = [n for n in names if n not in _ENGINE_CLASSES]
    if unknown:
        logger.warning("Ignoring unknown OCR engines in OCR_ENGINES: %s", ", ".join(unknown))
    return [n for n in names if n in _ENGINE_CLASSES]


# One engine instance per name for the whole process. Engines hold the loaded
# model (RapidOCR/Paddle weights, an HTTP session), and ``build_default_engines``
# is called for every uploaded document: without this cache every document
# re-created the engines and re-loaded the OCR model. Access to an instance's
# ``recognize`` is serialised by the OCR pipeline (see ``pipeline._run_lock``).
_ENGINE_CACHE: dict[str, OCREngine] = {}
_ENGINE_CACHE_LOCK = threading.Lock()


def get_engine(name: str) -> OCREngine:
    """The shared engine instance for ``name`` (created on first use)."""
    with _ENGINE_CACHE_LOCK:
        engine = _ENGINE_CACHE.get(name)
        if engine is None:
            engine = _ENGINE_CACHE[name] = _ENGINE_CLASSES[name]()
        return engine


def build_default_engines() -> list[OCREngine]:
    """Usable engines in configured priority order (unavailable ones are skipped)."""
    engines: list[OCREngine] = []
    for name in _configured_names():
        engine = get_engine(name)
        reason = engine.unavailable_reason()
        if reason:
            logger.info("OCR engine '%s' skipped: %s", name, reason)
        else:
            engines.append(engine)
    return engines


def engine_status() -> list[tuple[str, bool, str]]:
    """(name, ready, reason) for every known engine, for the admin status panel."""
    status = []
    for name, cls in _ENGINE_CLASSES.items():
        reason = cls().unavailable_reason()
        status.append((name, reason is None, reason or ""))
    return status
