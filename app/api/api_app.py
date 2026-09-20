from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


app = FastAPI(
    title="Chemistry AI API",
    version="0.1.0",
    description="API for the Chemistry AI Streamlit UI.",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    answer: str
    grounded: bool = False
    sources: list[dict[str, Any]] = []


class UploadResponse(BaseModel):
    message: str
    files: list[str]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """
    Temporary UI/demo endpoint.

    Replace this implementation with the real RAGService later.
    """
    return ChatResponse(
        answer=(
            "This is a temporary demo response. "
            "The Streamlit UI is connected to FastAPI, "
            "and the real Chemistry RAG service can be integrated here."
        ),
        grounded=False,
        sources=[],
    )


@app.post("/upload", response_model=UploadResponse)
def upload(files: list[str]) -> UploadResponse:
    """
    Temporary upload endpoint placeholder.

    The real document ingestion pipeline will be connected later.
    """
    return UploadResponse(
        message="Files received by the demo API.",
        files=files,
    )
