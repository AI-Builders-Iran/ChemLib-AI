from textwrap import dedent

from .schemas import ChunkResult


class RAGPromptBuilder:

    def build(self,
              question: str, chunks: list[ChunkResult]
              ) -> str:
        context = "\n\n".join(
            f"[{c.chunk_id}] {c.text}" for c in chunks
        )
        return dedent(f"""
                    You are answering questions for chemistry faculty library users.
                    Answer ONLY using the context below. Do not use outside knowledge.
                    If the context is insufficient to answer, set grounded=false and
                    say so briefly, in the same language as the question (Persian or English).
                    Always list the chunk_ids you actually used in the citations field.

                    Question: {question}

                    Context:
                    {context}
                """).strip()
