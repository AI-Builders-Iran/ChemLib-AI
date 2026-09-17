import json

from src.extraction.extractor import DocumentExtractor
from src.extraction.providers.gemini_provider import GeminiProvider
from src.extraction.providers.openrouter_provider import OpenRouterProvider
from src.schemas.common import DocumentType
from dotenv import load_dotenv

load_dotenv()


def load_chunks(file_path: str) -> str:
    """
    Load chunks from a JSON file and combine their text.

    Args:
        file_path: Path to the chunked JSON file.

    Returns:
        Combined document text.
    """
    with open(file_path, "r", encoding="utf-8") as file:
        chunks = json.load(file)

    return "\n\n".join(
        chunk["text"]
        for chunk in chunks
    )


def main() -> None:
    """Run structured extraction on the chunked contract."""

    document_text = load_chunks(
        "src/processing/chunks.json"
    )

    extractor = DocumentExtractor(
        providers=[
            GeminiProvider(),
            OpenRouterProvider(),
        ]
    )

    result = extractor.extract(
        document_text=document_text,
        document_type=DocumentType.CONTRACT,
    )

    print("\nFinal result:")
    print(result)

    print("\nJSON:")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()