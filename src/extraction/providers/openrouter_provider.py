import os
from typing import Type

from langchain.chat_models import init_chat_model
from pydantic import BaseModel


# ------------LLM provider implementation using OpenRouter (via LangChain)---------------
class OpenRouterProvider:

    def __init__(
        self,
        api_key: str | None = None,
        model_names: list[str] | None = None,
    ) -> None:
        """
        Initialize the OpenRouter provider via LangChain's init_chat_model.

        Args:
            api_key: OpenRouter API key.
            model_names: models ordered by fallback priority.

        Raises:
            ValueError: if the API key is not available.
        """
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        # OpenRouter needs these env vars set for LangChain to pick them up
        os.environ["OPENROUTER_API_KEY"] = self._api_key

        self._model_names = model_names or "auto"

        # "auto" lets init_chat_model use the provider's default model,
        # but OpenRouter needs a concrete model slug, so pass the first one.
        self._llm = init_chat_model(
            self._model_names,
            model_provider="openrouter",
        )

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
        """
        # LangChain's structured output uses the schema directly.
        structured_llm = self._llm.with_structured_output(schema)

        parsed = structured_llm.invoke(prompt)

        if parsed is None:
            raise ValueError(
                "OpenRouter returned no parsed structured output."
            )

        return parsed