import os
from typing import Type

from google import genai
from pydantic import BaseModel
from src.extraction.providers.base import LLMProvider

#----------LLM provider implementation using Google gemini--------------
class GeminiProvider(LLMProvider):

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        """
        Initialize the Gemini provider.
        Args:
            api_key: Gemini API key.
            model_name: Gemini model name.
        """
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not self._api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        self._client = genai.Client(api_key=self._api_key)
        self._model_name = model_name

    def extract(
        self,
        prompt: str,
        schema: Type[BaseModel],
    ) -> BaseModel:
        """
        extract structured data using gemini.
        Args:
            prompt: Extraction prompt.
            schema: Pydantic output schema.
        Returns:
            A validated Pydantic model.
        """
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )

        return schema.model_validate_json(response.text)