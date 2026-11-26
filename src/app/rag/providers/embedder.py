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
        """Store the API key and the retrieval task used for every call."""
        self._api_key = api_key
        self._task = task

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per text, in order. Raises EmbeddingError on any failure."""
        if not texts:
            return []
        key = self._require_key()
        response = self._post_embeddings(key, texts)
        return self._parse_vectors(response.content, len(texts))

    def _require_key(self) -> str:
        """Return the stripped API key, or raise when it is missing."""
        key = self._api_key.get_secret_value().strip()
        if not key:
            raise EmbeddingError("Set JINA_API_KEY in .env to enable embeddings.")
        return key

    def _post_embeddings(self, key: str, texts: list[str]) -> httpx.Response:
        """Call the Jina embeddings API and return a successful response."""
        try:
            response = httpx.post(
                JINA_EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {key}"},
                json=self._request_body(texts),
                timeout=60,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(f"Jina returned HTTP {exc.response.status_code}.") from None
        except httpx.RequestError:
            raise EmbeddingError("Could not connect to the Jina embedding API.") from None
        return response

    def _request_body(self, texts: list[str]) -> dict[str, object]:
        """Return the JSON body for one embeddings request."""
        return {
            "model": "jina-embeddings-v5-text-small",
            "task": self._task,
            "dimensions": self.dimension,
            "embedding_type": "float",
            "input": texts,
        }

    def _parse_vectors(self, content: bytes, count: int) -> list[list[float]]:
        """Validate the response body and return vectors ordered by input index."""
        try:
            items = sorted(
                EmbeddingResponse.model_validate_json(content).data,
                key=lambda item: item.index,
            )
        except ValidationError:
            raise EmbeddingError("Jina returned an invalid embedding response.") from None
        if [item.index for item in items] != list(range(count)) or any(
            len(item.embedding) != self.dimension for item in items
        ):
            raise EmbeddingError("Jina returned an unexpected number or size of embeddings.")
        return [item.embedding for item in items]
