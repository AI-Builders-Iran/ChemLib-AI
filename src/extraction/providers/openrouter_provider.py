import base64
import io
import logging
import os
import re
from typing import Type

from langchain.chat_models import init_chat_model
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output-token limits.
#
# ``ChatOpenRouter`` sends no ``max_tokens`` unless told to, and OpenRouter then
# reserves the model's *maximum* output (131072 for some models) against the
# account's credit balance, so a small balance fails with
# "402: You requested up to 131072 tokens, but can only afford N".
# Every request therefore carries an explicit, task-sized limit. All are
# overridable from .env.
# ---------------------------------------------------------------------------
DEFAULT_MAX_TOKENS = 4096        # RAG answers / structured extraction (OPENROUTER_MAX_TOKENS)
OCR_MAX_TOKENS = 4096            # one page transcribed by a vision model (OCR_LLM_MAX_TOKENS)
FIGURE_CAPTION_MAX_TOKENS = 2048  # figure captions (FIGURE_CAPTION_MAX_TOKENS)

_HTTP_REASONS = {
    400: "Bad Request",
    401: "Unauthorized (check OPENROUTER_API_KEY)",
    402: "Payment Required (out of credits, or max_tokens too high for the balance)",
    403: "Forbidden (key not allowed to use this model, or content moderated)",
    404: "Not Found (check OPENROUTER_MODEL)",
    408: "Request Timeout",
    429: "Too Many Requests (rate limited)",
}

_KEY_LIKE = re.compile(r"sk-or-[A-Za-z0-9_\-]{6,}")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{8,}")
_KEY_ASSIGNMENT = re.compile(r"(?i)(api[_-]?key|authorization)(['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]+")


def redact_secrets(text: str) -> str:
    """Remove anything that looks like an API key / auth header from ``text``."""
    text = _KEY_LIKE.sub("[REDACTED]", text)
    text = _BEARER.sub("[REDACTED]", text)
    return _KEY_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)


def env_int(name: str, default: int) -> int:
    """Positive int from an environment variable; bad/empty values use ``default``."""
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class OpenRouterProviderError(RuntimeError):
    """An OpenRouter call failed in a way the caller can reason about.

    It subclasses ``RuntimeError`` so existing ``except Exception`` fallbacks
    (RAG provider fallback, OCR engine fallback) keep working, while new code can
    look at ``status_code`` / ``kind`` / ``retryable``.

    ``kind``: "http" (the API answered with an error status), "malformed" (it
    answered, but not with a usable completion), "network" (no/failed
    connection, timeout) or "unexpected".
    """

    def __init__(self, message: str, *, kind: str, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retryable = retryable


def _provider_message(exc: Exception) -> str:
    """Best human-readable message the API gave (never the whole raw body)."""
    value = getattr(exc, "message", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    value = getattr(getattr(getattr(exc, "data", None), "error", None), "message", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return str(exc).strip()


def classify_openrouter_error(exc: Exception) -> OpenRouterProviderError:
    """Turn whatever the SDK/HTTP stack raised into one safe, readable error.

    Handles: the OpenRouter SDK's typed HTTP errors and openai-style
    ``APIStatusError`` (both expose ``status_code``), connection/timeout errors,
    and pydantic ``ValidationError``s - the latter is what appears when a
    non-completion body (e.g. a 402 error JSON) is parsed as a chat completion
    ("body.choices Field required").
    """
    if isinstance(exc, OpenRouterProviderError):
        return exc

    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status >= 400:
        reason = _HTTP_REASONS.get(status) or ("Server Error" if status >= 500 else "HTTP error")
        detail = redact_secrets(_provider_message(exc))[:300]
        message = f"OpenRouter returned HTTP {status} {reason}."
        if detail:
            message += f" Provider message: {detail}"
        retryable = status in (408, 429) or status >= 500
        return OpenRouterProviderError(message, kind="http", status_code=status, retryable=retryable)

    name = type(exc).__name__
    if name in ("ValidationError", "ResponseValidationError") or "validation error" in str(exc).lower():
        return OpenRouterProviderError(
            "OpenRouter returned a response that is not a valid chat completion "
            "(likely an upstream error body or an unexpected format).",
            kind="malformed",
        )
    if isinstance(exc, (TimeoutError, ConnectionError)) or any(
        token in name for token in ("Timeout", "Connect", "Network", "NoResponse", "ReadError")
    ):
        return OpenRouterProviderError(
            f"OpenRouter could not be reached ({name}).", kind="network", retryable=True
        )
    return OpenRouterProviderError(
        f"OpenRouter request failed ({name}): {redact_secrets(str(exc))[:300]}", kind="unexpected"
    )


# ------------LLM provider implementation using OpenRouter (via LangChain)---------------
class OpenRouterProvider:

    def __init__(
        self,
        api_key: str | None = None,
        model_names: list[str] | str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        """
        Initialize the OpenRouter provider via LangChain's init_chat_model.

        Args:
            api_key: OpenRouter API key.
            model_names: models ordered by fallback priority.
            max_tokens: output-token limit sent with every request (OpenRouter's
                ``max_tokens`` chat-completions parameter). Default:
                ``OPENROUTER_MAX_TOKENS`` or 4096.

        Raises:
            ValueError: if the API key is not available.
        """
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        # OpenRouter needs these env vars set for LangChain to pick them up
        os.environ["OPENROUTER_API_KEY"] = self._api_key

        # OpenRouter needs a full model slug: the bare word "auto" is not one, the Auto
        # Router is "openrouter/auto". Override with OPENROUTER_MODEL in .env
        # (e.g. "openrouter/free" to stay on free models only).
        if isinstance(model_names, (list, tuple)):
            model_names = model_names[0] if model_names else None
        self._model_names = model_names or os.getenv("OPENROUTER_MODEL") or "openrouter/auto"
        self._max_tokens = max_tokens or env_int("OPENROUTER_MAX_TOKENS", DEFAULT_MAX_TOKENS)

        # "auto" lets init_chat_model use the provider's default model,
        # but OpenRouter needs a concrete model slug, so pass the first one.
        self._llm = init_chat_model(
            self._model_names,
            model_provider="openrouter",
            max_tokens=self._max_tokens,
        )

    @property
    def model_name(self) -> str:
        return self._model_names

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def _invoke_structured(self, payload, schema: Type[BaseModel], what: str) -> BaseModel:
        """One structured-output call. Every failure becomes an
        ``OpenRouterProviderError``: the SDK checks the HTTP status before it
        parses a completion, so an error body is never treated as a successful
        response, and a missing parse result is an explicit error too."""
        try:
            parsed = self._llm.with_structured_output(schema).invoke(payload)
        except Exception as exc:  # noqa: BLE001 - classified and re-raised as a typed error
            raise classify_openrouter_error(exc) from exc

        if parsed is None:
            raise OpenRouterProviderError(
                f"OpenRouter returned no parsed structured output for {what}.", kind="malformed"
            )
        return parsed

    def extract(
        self,
        prompt: str,
        schema: Type[BaseModel],
    ) -> BaseModel:
        """
        Extract structured data using OpenRouter.

        Args:
            prompt: extraction prompt.
            schema: pydantic output schema.

        Returns:
            A validated Pydantic model.

        Raises:
            OpenRouterProviderError: on any HTTP/network/format failure.
        """
        return self._invoke_structured(prompt, schema, "the prompt")

    def extract_image(
        self,
        image,
        schema: Type[BaseModel],
        prompt: str,
    ) -> BaseModel:
        """
        Extract structured data from an image using a vision-capable model
        routed through OpenRouter.

        Args:
            image: a PIL Image object.
            schema: Pydantic output schema.
            prompt: instruction for what to extract from the image.

        Returns:
            A validated Pydantic model.

        Raises:
            OpenRouterProviderError: on any HTTP/network/format failure.

        Note: the model selected via ``OPENROUTER_MODEL`` (or the default
        "openrouter/auto") must support image input. If it does not, the
        underlying call will raise - pick a vision-capable model (e.g. a
        "-vl" / multimodal model slug) for OCR / figure-captioning use.
        """
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
        return self._invoke_structured([message], schema, "the image")
