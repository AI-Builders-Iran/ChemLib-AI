from typing import Type

from pydantic import BaseModel

from src.extraction.prompts import PromptBuilder
from src.extraction.providers.base import LLMProvider
from src.schemas.common import DocumentType, GeneralDocument
from src.schemas.contract import Contract
from src.schemas.invoice import Invoice

#-------------extract structured information from documents--------------------
class DocumentExtractor:

    _SCHEMA_MAP: dict[DocumentType, Type[BaseModel]] = {
        DocumentType.CONTRACT: Contract,
        DocumentType.INVOICE: Invoice,
        DocumentType.GENERAL: GeneralDocument,
    }

    def __init__(self, providers: list[LLMProvider]) -> None:
        """
        initialize the document extractor.
        args:
            providers: Ordered list of LLM providers.
                the first provider is the primary provider.
                the following providers are used as fallbacks.
        Raises:
            valueError: if no provider is provided.
        """
        if not providers:
            raise ValueError("At least one LLM provider is required.")

        self._providers = providers
        self._prompt_builder = PromptBuilder()

    def extract(
        self,
        document_text: str,
        document_type: DocumentType,
    ) -> BaseModel:
        """
        extract structured information from document text.
        args:
            document_text: Text extracted from the document.
            document_type: Type of the document.
        returns:
            a validated Pydantic model.
        raises:
            valueerror: if the document type is unsupported.
            runtimeerror: if all providers fail.
        """
        schema = self._get_schema(document_type)

        prompt = self._prompt_builder.build(
            document_text=document_text,
            document_type=document_type.value,
        )

        errors: list[str] = []

        for provider in self._providers:
            try:
                return provider.extract(
                    prompt=prompt,
                    schema=schema,
                )
            except Exception as exc:
                errors.append(
                    f"{provider.__class__.__name__}: {exc}"
                )

        raise RuntimeError(
            "All LLM providers failed. "
            + " | ".join(errors)
        )

    def _get_schema(
        self,
        document_type: DocumentType,
    ) -> Type[BaseModel]:
        """
        return the pydantic schema associated with a document type.
        args:
            document_type: type of the document.
        returns:
            the corresponding Pydantic model class.

        raises:
            valueError: if the document type is unsupported.
        """
        try:
            return self._SCHEMA_MAP[document_type]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported document type: {document_type}"
            ) from exc