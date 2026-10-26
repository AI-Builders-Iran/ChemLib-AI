"""Figure handling: MVP = skip, with a clean extension point for a production VLM.

MVP (``ENABLE_FIGURE_PROCESSING`` unset/false, the default): a figure region
found by the layout engine is *skipped* - no crop saved, no OpenRouter/VLM
call, no caption. The pipeline is text + OCR + layout + tables + RAG.

Production (``ENABLE_FIGURE_PROCESSING=true``): :func:`describe_figure` turns a
cropped figure into a short searchable caption through whichever provider
implements ``extract_image`` (OpenRouter today). This is the single place to
swap in a specialised VLM / chemical-structure pipeline later.

Captioning is an enhancement, never a dependency: :func:`describe_figure`
returns ``""`` on *any* failure (payment required, rate limit, malformed
response, network) unless ``FIGURE_CAPTION_REQUIRED=true``, and after a hard
failure it stops calling the API for a cool-down so a 402 on one figure does
not turn into a 402 per figure.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from pydantic import BaseModel

logger = logging.getLogger(__name__)

FIGURE_PROMPT = (
    "This image is a figure cropped from a chemistry textbook or paper: a "
    "diagram, chemical structure, reaction scheme, apparatus drawing, or "
    "chart. In 1-3 sentences, describe what it shows so a student could find "
    "it by searching for its topic (e.g. the reaction/compound/concept "
    "involved). If it contains a chemical structure, name the compound or "
    "functional groups if you can identify them. Answer in the same "
    "language as any text visible in the image, defaulting to English."
)

# Cool-down (seconds) after a failure that will keep failing for a while.
_COOLDOWN_BY_STATUS = {401: 3600, 402: 600, 403: 3600, 429: 60}
_DEFAULT_COOLDOWN = 0  # other failures (one bad image, a blip) do not pause captioning

_breaker_lock = threading.Lock()
_paused_until = 0.0
_paused_reason = ""


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def figure_processing_enabled() -> bool:
    """``ENABLE_FIGURE_PROCESSING`` - default False (MVP: figures are skipped)."""
    return _env_flag("ENABLE_FIGURE_PROCESSING", False)


def figure_caption_required() -> bool:
    """``FIGURE_CAPTION_REQUIRED`` - default False (a caption failure never fails ingestion)."""
    return _env_flag("FIGURE_CAPTION_REQUIRED", False)


def figure_caption_max_tokens() -> int:
    """``FIGURE_CAPTION_MAX_TOKENS`` - output-token limit for a caption (default 2048)."""
    from src.extraction.providers.openrouter_provider import FIGURE_CAPTION_MAX_TOKENS, env_int

    return env_int("FIGURE_CAPTION_MAX_TOKENS", FIGURE_CAPTION_MAX_TOKENS)


class FigureCaption(BaseModel):
    caption: str


def reset_circuit_breaker() -> None:
    """Forget any cool-down (tests, or after the user fixed their credits)."""
    global _paused_until, _paused_reason
    with _breaker_lock:
        _paused_until, _paused_reason = 0.0, ""


def _paused() -> str | None:
    with _breaker_lock:
        if _paused_until and time.monotonic() < _paused_until:
            return _paused_reason
    return None


def _trip(status_code: int | None, reason: str) -> None:
    global _paused_until, _paused_reason
    cooldown = _COOLDOWN_BY_STATUS.get(status_code or 0, _DEFAULT_COOLDOWN)
    if cooldown:
        with _breaker_lock:
            _paused_until = time.monotonic() + cooldown
            _paused_reason = reason


def describe_figure(image, provider=None) -> str:
    """Best-effort caption for a cropped figure. Returns "" when unavailable.

    ``provider``: an object with ``extract_image(image, schema, prompt)``
    (injectable for tests). Defaults to ``OpenRouterProvider`` limited to
    ``FIGURE_CAPTION_MAX_TOKENS`` output tokens. Never raises, unless
    ``FIGURE_CAPTION_REQUIRED=true``.
    """
    required = figure_caption_required()

    paused_reason = _paused()
    if paused_reason and not required:
        logger.debug("Figure captioning paused (%s); skipping caption for this figure", paused_reason)
        return ""

    try:
        if provider is None:
            from src.extraction.providers.openrouter_provider import OpenRouterProvider

            provider = OpenRouterProvider(max_tokens=figure_caption_max_tokens())

        result = provider.extract_image(image=image, schema=FigureCaption, prompt=FIGURE_PROMPT)
        caption = getattr(result, "caption", None)
        if not isinstance(caption, str):
            raise ValueError("caption provider returned no caption text")
        return caption.strip()
    except Exception as exc:  # noqa: BLE001 - captioning is an enhancement, never fatal
        if required:
            raise
        status = getattr(exc, "status_code", None)
        try:
            from src.extraction.providers.openrouter_provider import redact_secrets

            detail = redact_secrets(str(exc))
        except Exception:  # noqa: BLE001 - never let log formatting hide the real failure
            detail = type(exc).__name__
        logger.warning(
            "Figure captioning unavailable: %s Skipping caption generation for this figure.", detail
        )
        _trip(status, detail)
        return ""
