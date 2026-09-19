from rag.schemas import ChunkResult, RAGAnswer
from rag.prompts import RAGPromptBuilder
from src.extraction.providers.openrouter_provider import OpenRouterProvider
import os

api_key = os.getenv("OPENROUTER_API_KEY")

chunks = [
    ChunkResult(
        text="آب در دمای ۱۰۰ درجه سانتی‌گراد در فشار یک اتمسفر می‌جوشد.",
        source_file="chem_intro.pdf",
        page=12,
        chunk_id="chem_intro_p12_c1",
        score=0.91,
    )
]

prompt = RAGPromptBuilder().build("فرمول شیمیایی گلوکز چیست؟", chunks)

provider = OpenRouterProvider(
    api_key=api_key
)

result = provider.extract(prompt=prompt, schema=RAGAnswer)

print(result)