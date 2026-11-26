"""Embedding model for the hosted Jina API, built on LlamaIndex's Jina integration."""

from typing import Literal, Protocol

import requests
from fastapi import Depends
from llama_index.embeddings.jinaai import JinaEmbedding

from app.config.settings import Settings, get_settings
from app.exception_handling.exceptions import EmbeddingError


class Embedder(Protocol):
    """Turns texts into fixed-size vectors."""

    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in order."""
        ...


class JinaEmbedder:
    """Embed passages or queries with one Jina retrieval task, through LlamaIndex's client."""

    def __init__(
        self, settings: Settings, task: Literal["retrieval.passage", "retrieval.query"]
    ) -> None:
        """Build the LlamaIndex client for this task from the configured model and size."""
        self._api_key = settings.jina_api_key
        self.dimension = settings.jina_embedding_dimension
        self._model = JinaEmbedding(
            api_key=self._api_key.get_secret_value().strip(),
            model=settings.jina_embedding_model,
            task=task,
            dimensions=self.dimension,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per text, in order. Raises EmbeddingError on any failure."""
        if not texts:
            return []
        self._require_key()
        try:
            return self._model.get_text_embedding_batch(texts)
        except (RuntimeError, KeyError, requests.RequestException) as error:
            raise EmbeddingError("Jina embedding request failed.") from error

    def _require_key(self) -> None:
        """Raise when the API key is missing, before any request is sent."""
        if not self._api_key.get_secret_value().strip():
            raise EmbeddingError("Set JINA_API_KEY in .env to enable embeddings.")


def get_embedder(settings: Settings = Depends(get_settings)) -> Embedder:
    """Return the query embedder for the current settings. Used as a FastAPI dependency."""
    return JinaEmbedder(settings, "retrieval.query")
