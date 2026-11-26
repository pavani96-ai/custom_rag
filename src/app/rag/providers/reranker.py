"""LlamaIndex postprocessor backed by Jina's hosted reranking API."""

import httpx
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle
from pydantic import Field, SecretStr, ValidationError

from app.schema.models import RerankedResult, RerankResponse

JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"
JINA_RERANK_MODEL = "jina-reranker-v3.5"


def _rerank_body(query: str, nodes: list[NodeWithScore], limit: int) -> dict[str, object]:
    """Return the JSON body for one reranking request."""
    return {
        "model": JINA_RERANK_MODEL,
        "query": query,
        "documents": [node.node.get_content() for node in nodes],
        "top_n": limit,
        "return_documents": False,
    }


class RerankError(Exception):
    """Jina did not return a usable reranking result."""


class JinaReranker(BaseNodePostprocessor):
    """Rank candidate nodes by relevance to the user's question."""

    api_key: SecretStr = Field(exclude=True)
    top_n: int

    def _postprocess_nodes(
        self, nodes: list[NodeWithScore], query_bundle: QueryBundle | None = None
    ) -> list[NodeWithScore]:
        """Return up to top_n nodes ordered by Jina's relevance score. Raises RerankError."""
        if query_bundle is None:
            raise ValueError("Reranking requires a query.")
        if not nodes:
            return []
        key = self._require_key()
        limit = min(self.top_n, len(nodes))
        response = self._post_rerank(key, query_bundle.query_str, nodes, limit)
        results = self._parse_results(response.content, limit, len(nodes))
        return [
            NodeWithScore(node=nodes[result.index].node, score=result.relevance_score)
            for result in results
        ]

    def _require_key(self) -> str:
        """Return the stripped API key, or raise when it is missing."""
        key = self.api_key.get_secret_value().strip()
        if not key:
            raise RerankError("Set JINA_API_KEY in .env to enable reranking.")
        return key

    def _post_rerank(
        self, key: str, query: str, nodes: list[NodeWithScore], limit: int
    ) -> httpx.Response:
        """Call the Jina reranking API and return a successful response."""
        try:
            response = httpx.post(
                JINA_RERANK_URL,
                headers={"Authorization": f"Bearer {key}"},
                json=_rerank_body(query, nodes, limit),
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RerankError(f"Jina reranking returned HTTP {exc.response.status_code}.") from None
        except httpx.RequestError:
            raise RerankError("Could not connect to the Jina reranking API.") from None
        return response

    def _parse_results(self, content: bytes, limit: int, count: int) -> list[RerankedResult]:
        """Validate the response and check that it names each expected passage once."""
        try:
            results = RerankResponse.model_validate_json(content).results
        except ValidationError:
            raise RerankError("Jina returned an invalid reranking response.") from None
        indices = {result.index for result in results}
        if len(indices) != limit or len(results) != limit or not indices <= set(range(count)):
            raise RerankError("Jina returned unexpected passage indices.")
        return results
