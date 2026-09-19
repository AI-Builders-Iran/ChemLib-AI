#---OpenRouter LLM wrapper for RAG generation (OpenAI-compatible API).---#

from __future__ import annotations

import logging
import os
from typing import Protocol

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen/qwen3-14b:free"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS = 45.0


class LLMError(Exception):
    """Base error for RAG LLM failures (safe to map to HTTP 500)."""


class LLMTimeoutError(LLMError):
    """The model request timed out."""


class LLMRateLimitError(LLMError):
    """The provider rejected the request because of rate limiting."""


class LLMGenerator(Protocol):
    def generate(self, prompt: str) -> str:
        """Return a model completion for ``prompt``."""


class OpenRouterLLM:
    """Generate free-text completions via OpenRouter's OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        self._model = model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
        self._base_url = (
            base_url or os.getenv("OPENROUTER_BASE_URL") or DEFAULT_BASE_URL
        )
        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    def generate(self, prompt: str) -> str:
        """Send ``prompt`` to the configured model and return the text reply."""
        logger.info(
            "Calling OpenRouter model=%s base_url=%s",
            self._model,
            self._base_url,
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
        except RateLimitError as exc:
            logger.warning("OpenRouter rate-limited the request.")
            raise LLMRateLimitError(
                "The language model is temporarily rate-limited."
            ) from exc
        except APITimeoutError as exc:
            logger.warning("OpenRouter request timed out.")
            raise LLMTimeoutError(
                "The language model request timed out."
            ) from exc
        except (APIConnectionError, APIStatusError) as exc:
            logger.warning("OpenRouter API error: %s", exc.__class__.__name__)
            raise LLMError("The language model request failed.") from exc
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unexpected OpenRouter client error: %s", type(exc).__name__)
            raise LLMError("The language model request failed.") from exc

        content = ""
        if response.choices:
            content = (response.choices[0].message.content or "").strip()
        if not content:
            raise LLMError("The language model returned an empty response.")
        return content
