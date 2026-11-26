"""Embedding model adapter for the hosted Jina API."""

from typing import Literal, Protocol

import httpx
from pydantic import SecretStr, ValidationError

from app.schema.models import EmbeddingResponse

JINA_EMBEDDINGS_URL = "https://api.jina.ai/v1/embeddings"


class EmbeddingError(Exception):
    """The embedding service could not return usable vectors."""


class Embedder(Protocol):
    """Turns texts into fixed-size vectors."""

    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in order."""
        ...


class JinaEmbedder:
    """Embed passages and queries using Jina's paired retrieval tasks."""

    dimension = 512

    def __init__(
        self, api_key: SecretStr, task: Literal["retrieval.passage", "retrieval.query"]
    ) -> None:
        self._api_key = api_key
        self._task = task

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        key = self._api_key.get_secret_value().strip()
        if not key:
            raise EmbeddingError("Set JINA_API_KEY in .env to enable embeddings.")
        try:
            response = httpx.post(
                JINA_EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": "jina-embeddings-v5-text-small",
                    "task": self._task,
                    "dimensions": self.dimension,
                    "embedding_type": "float",
                    "input": texts,
                },
                timeout=60,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(f"Jina returned HTTP {exc.response.status_code}.") from None
        except httpx.RequestError:
            raise EmbeddingError("Could not connect to the Jina embedding API.") from None

        try:
            items = sorted(
                EmbeddingResponse.model_validate_json(response.content).data,
                key=lambda item: item.index,
            )
        except ValidationError:
            raise EmbeddingError("Jina returned an invalid embedding response.") from None
        if [item.index for item in items] != list(range(len(texts))) or any(
            len(item.embedding) != self.dimension for item in items
        ):
            raise EmbeddingError("Jina returned an unexpected number or size of embeddings.")
        return [item.embedding for item in items]
