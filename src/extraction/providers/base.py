from abc import ABC, abstractmethod
from typing import Type

from pydantic import BaseModel

#-------------abstract interface for LLM providers.--------------------
class LLMProvider(ABC):

    @abstractmethod
    def extract(
        self,
        prompt: str,
        schema: Type[BaseModel],
    ) -> BaseModel:
        """
        extract structured data using the provider.
        Args:
            prompt: Extraction prompt.
            schema: Pydantic model defining the expected output.

        Returns:
            A validated Pydantic model.
        Raises:
            Exception: If the provider cannot complete the request.
        """
        raise NotImplementedError