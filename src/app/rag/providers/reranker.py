"""LlamaIndex postprocessor backed by Jina's hosted reranking API."""

import httpx
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle
from pydantic import Field, SecretStr, ValidationError

from app.schema.models import RerankResponse

JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"
JINA_RERANK_MODEL = "jina-reranker-v3.5"


class RerankError(Exception):
    """Jina did not return a usable reranking result."""


class JinaReranker(BaseNodePostprocessor):
    """Rank candidate nodes by relevance to the user's question."""

    api_key: SecretStr = Field(exclude=True)
    top_n: int

    def _postprocess_nodes(
        self, nodes: list[NodeWithScore], query_bundle: QueryBundle | None = None
    ) -> list[NodeWithScore]:
        if query_bundle is None:
            raise ValueError("Reranking requires a query.")
        if not nodes:
            return []

        key = self.api_key.get_secret_value().strip()
        if not key:
            raise RerankError("Set JINA_API_KEY in .env to enable reranking.")
        limit = min(self.top_n, len(nodes))
        try:
            response = httpx.post(
                JINA_RERANK_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": JINA_RERANK_MODEL,
                    "query": query_bundle.query_str,
                    "documents": [node.node.get_content() for node in nodes],
                    "top_n": limit,
                    "return_documents": False,
                },
                timeout=30,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RerankError(f"Jina reranking returned HTTP {exc.response.status_code}.") from None
        except httpx.RequestError:
            raise RerankError("Could not connect to the Jina reranking API.") from None

        try:
            results = RerankResponse.model_validate_json(response.content).results
        except ValidationError:
            raise RerankError("Jina returned an invalid reranking response.") from None
        indices = {result.index for result in results}
        if len(indices) != limit or len(results) != limit or not indices <= set(range(len(nodes))):
            raise RerankError("Jina returned unexpected passage indices.")

        return [
            NodeWithScore(node=nodes[result.index].node, score=result.relevance_score)
            for result in results
        ]
