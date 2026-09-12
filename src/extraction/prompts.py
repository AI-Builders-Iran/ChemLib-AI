from textwrap import dedent

from src.schemas.common import DocumentType

#------build prompts for document information extraction------
class PromptBuilder:

    def build(
        self,
        document_text: str,
        document_type: str,
    ) -> str:
        """
        build an extraction prompt.
        args:
            document_text: Text extracted from the document.
            document_type: Document type.
        returns:
            A prompt for the language model.
        """
        return dedent(
            f"""
            You are a document information extraction system.

            Document type: {document_type}

            Extract the required information from the document below.

            Rules:
            - Extract information only from the provided document.
            - Do not invent missing information.
            - Preserve extracted values accurately.
            - The document may be written in Persian or English.
            - Do not translate extracted values unless required.
            - Follow the provided structured output schema.
            - Return only the requested structured information.

            Document:
            {document_text}
            """
        )