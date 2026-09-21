import os
from typing import Type

from google import genai
from pydantic import BaseModel

from src.extraction.providers.base import LLMProvider


# ----------LLM provider implementation using Google gemini--------------
class GeminiProvider(LLMProvider):

    def __init__(
            self,
            api_key: str | None = None,
            model_name: str | None = None,
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
        # Free-tier quotas are per model: set GEMINI_MODEL in .env to switch models
        # without touching the code.
        self._model_name = model_name or os.getenv("GEMINI_MODEL") or "gemini-3.6-flash"

    @property
    def model_name(self) -> str:
        return self._model_name

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

    def extract_image(
            self,
            image,
            schema: Type[BaseModel],
            prompt: str,
    ) -> BaseModel:
        """
        Extract structured data from an image using Gemini's vision capability.
        Args:
            image: a PIL Image object.
            schema: Pydantic output schema.
            prompt: instruction for what to extract from the image.
        Returns:
            A validated Pydantic model.
        """
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[prompt, image],
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )
        return schema.model_validate_json(response.text)