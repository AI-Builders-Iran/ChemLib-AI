import os
from typing import Type

from openai import OpenAI
from pydantic import BaseModel

#------------LLM provider implementation using OpenRouter---------------
class OpenRouterProvider:

    def __init__(
        self,
        api_key: str | None = None,
        model_names: list[str] | None = None,
    ) -> None:
        """
        initialize the openRouter provider.
        Args:
            api_key: openRouter API key.
            model_names: models ordered by fallback priority.
        Raises:
            ValueError: if the API key is not available.
        """
        self._api_key = api_key or os.getenv("OPENROUTER_API_KEY")

        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        self._model_names = model_names or [
            os.getenv(
                "OPENROUTER_MODEL",
                "z-ai/glm-5.2:free",
            ),
        ]

        self._client = OpenAI(
            api_key=self._api_key,
            base_url="https://openrouter.ai/api/v1",
        )

    def extract(
        self,
        prompt: str,
        schema: Type[BaseModel],
    ) -> BaseModel:
        """
        Extract structured data using openRouter.
        Args:
            prompt: extraction prompt.
            schema: pydantic output schema.
        Returns:
            A validated Pydantic model.
        """
        response = self._client.chat.completions.parse(
            model=self._model_names[0],
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_format=schema,
            extra_body={
                "models": self._model_names,
            },
        )

        parsed = response.choices[0].message.parsed

        if parsed is None:
            raise ValueError(
                "OpenRouter returned no parsed structured output."
            )

        return parsed