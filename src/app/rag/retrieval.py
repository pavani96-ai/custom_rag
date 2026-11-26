"""Retrieval steps: scoped OpenSearch branches, rank fusion, and Jina reranking."""

from typing import Any

from llama_index.core.llms import MockLLM
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from opensearchpy import OpenSearch

from app.config.settings import Settings
from app.rag.providers.embedder import Embedder
from app.rag.providers.reranker import JinaReranker
from app.schema.models import CitedPassage, Passage
from app.search.opensearch import INDEX_NAME

SOURCE_FIELDS = ["chunk_id", "document_id", "filename", "page", "text"]
METADATA_FIELDS = ("chunk_id", "document_id", "filename", "page")
VECTOR_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4


class SearchTimeout(Exception):
    """OpenSearch did not answer in time."""


def build_search_filters(collection_id: str, document_ids: list[str]) -> list[dict[str, Any]]:
    """Scope a search to one collection and to the given ready documents."""
    return [
        {"term": {"collection_id": collection_id}},
        {"terms": {"document_id": document_ids}},
    ]


class OpenSearchRetriever(BaseRetriever):
    """Adapt one native OpenSearch search to LlamaIndex nodes."""

    def __init__(
        self,
        client: OpenSearch,
        filters: list[dict[str, Any]],
        top_k: int,
        embedder: Embedder | None = None,
    ) -> None:
        """Keep the client, scope filters, and result size. Vector search needs an embedder."""
        super().__init__()
        self.client = client
        self.filters = filters
        self.top_k = top_k
        self.embedder = embedder

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        """Run the search and return its hits as nodes with scores."""
        result = self.client.search(
            index=INDEX_NAME,
            params={"ignore_unavailable": "true", "allow_partial_search_results": "false"},
            body={
                "size": self.top_k,
                "_source": SOURCE_FIELDS,
                "query": self._query(query_bundle.query_str),
            },
        )
        if result["timed_out"]:
            raise SearchTimeout("Search timed out.")
        return [_hit_to_node(hit) for hit in result["hits"]["hits"]]

    def _query(self, query: str) -> dict[str, Any]:
        """Return the vector query when an embedder is set, otherwise the keyword query."""
        if self.embedder is not None:
            return self._vector_query(query, self.embedder)
        return {"bool": {"filter": self.filters, "must": [{"match": {"text": query}}]}}

    def _vector_query(self, query: str, embedder: Embedder) -> dict[str, Any]:
        """Score filtered chunks by cosine similarity to the embedded query."""
        (vector,) = embedder.embed([query])
        return {
            "script_score": {
                "query": {"bool": {"filter": self.filters}},
                "script": {
                    "lang": "knn",
                    "source": "knn_score",
                    "params": {
                        "field": "embedding",
                        "query_value": vector,
                        "space_type": "cosinesimil",
                    },
                },
            }
        }


def _hit_to_node(hit: dict[str, Any]) -> NodeWithScore:
    """Convert one OpenSearch hit into a node that keeps its citation metadata."""
    source = hit["_source"]
    node = TextNode(
        id_=source["chunk_id"],
        text=source["text"],
        metadata={key: source[key] for key in METADATA_FIELDS},
    )
    return NodeWithScore(node=node, score=hit["_score"])


def fused_search(
    client: OpenSearch,
    filters: list[dict[str, Any]],
    top_k: int,
    embedder: Embedder,
    query: str,
) -> list[NodeWithScore]:
    """Run vector and keyword branches, fuse their scores, and return the top matches."""
    retriever = _fusion_retriever(client, filters, top_k, embedder)
    return retriever.retrieve(query)


def _fusion_retriever(
    client: OpenSearch, filters: list[dict[str, Any]], top_k: int, embedder: Embedder
) -> QueryFusionRetriever:
    """Build the fusion retriever over the two OpenSearch branches."""
    vector_search = OpenSearchRetriever(client, filters, top_k, embedder)
    keyword_search = OpenSearchRetriever(client, filters, top_k)
    return QueryFusionRetriever(
        [vector_search, keyword_search],
        mode="relative_score",
        retriever_weights=[VECTOR_WEIGHT, KEYWORD_WEIGHT],
        similarity_top_k=top_k,
        num_queries=1,
        # The constructor expects an LLM. A single query skips generation.
        llm=MockLLM(),
        use_async=False,
    )


def to_passage(match: NodeWithScore) -> Passage:
    """Convert a retrieved node into the public passage model."""
    return Passage(
        text=match.node.get_content(),
        score=match.get_score(),
        **match.node.metadata,
    )


def rerank_passages(
    passages: list[Passage], query: str, top_n: int, settings: Settings
) -> list[CitedPassage]:
    """Keep the first copy of each passage, then assign citation IDs in reranked order."""
    by_id = _unique_by_chunk(passages)
    nodes = [
        NodeWithScore(node=TextNode(id_=chunk_id, text=passage.text), score=passage.score)
        for chunk_id, passage in by_id.items()
    ]
    reranker = JinaReranker(api_key=settings.jina_api_key, top_n=top_n)
    ranked = reranker.postprocess_nodes(nodes, query_str=query)
    return [
        CitedPassage(
            source_id=index,
            passage=by_id[match.node.node_id],
            rerank_score=match.get_score(),
        )
        for index, match in enumerate(ranked, start=1)
    ]


def _unique_by_chunk(passages: list[Passage]) -> dict[str, Passage]:
    """Map each chunk ID to its passage, dropping repeats with the same normalized text."""
    seen_text: dict[str, Passage] = {}
    for passage in passages:
        seen_text.setdefault(" ".join(passage.text.split()), passage)
    return {str(passage.chunk_id): passage for passage in seen_text.values()}
