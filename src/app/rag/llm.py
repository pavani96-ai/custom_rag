"""Gemini chat model built through LlamaIndex. Used by /ask and by the chat stream."""

from fastapi import HTTPException
from google.genai import types
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.google_genai import GoogleGenAI
from pydantic import PrivateAttr

from app.config.settings import Settings
from app.rag.embedder import Embedder


def build_llm(settings: Settings) -> GoogleGenAI:
    """Return the answer model. Uses Vertex AI when a project is set, otherwise the API key."""
    options = types.HttpOptions(api_version="v1", timeout=settings.generation_timeout_ms)
    if settings.google_cloud_project:
        return GoogleGenAI(
            model=settings.gemini_model,
            vertexai_config={
                "project": settings.google_cloud_project,
                "location": settings.google_cloud_location,
            },
            http_options=options,
        )
    if key := settings.gemini_api_key.get_secret_value().strip():
        return GoogleGenAI(model=settings.gemini_model, api_key=key, http_options=options)
    raise HTTPException(
        status_code=503,
        detail="Set GEMINI_API_KEY for local development or configure Vertex AI credentials.",
    )


def make_messages(system: str, user: str) -> list[ChatMessage]:
    """Build a system message followed by one user message."""
    return [
        ChatMessage(role=MessageRole.SYSTEM, content=system),
        ChatMessage(role=MessageRole.USER, content=user),
    ]


class JinaLlamaEmbedding(BaseEmbedding):
    """Embed index writes with the passage embedder and queries with the query embedder."""

    _index_embedder: Embedder = PrivateAttr()
    _query_embedder: Embedder = PrivateAttr()

    def __init__(self, index_embedder: Embedder, query_embedder: Embedder, batch_size: int) -> None:
        """Keep both embedders. Batches are sized to match our provider calls."""
        super().__init__(embed_batch_size=batch_size, model_name="jina-embeddings-v5")
        self._index_embedder = index_embedder
        self._query_embedder = query_embedder

    def _get_query_embedding(self, query: str) -> list[float]:
        """Embed one question with the query task."""
        return self._query_embedder.embed([query])[0]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        """Async callers use the same synchronous provider call."""
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        """Embed one chunk with the passage task."""
        return self._index_embedder.embed([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunks with the passage task."""
        return self._index_embedder.embed(texts)
