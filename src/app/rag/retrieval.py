"""Retrieval steps: scoped vector and keyword branches on the chunk index, fusion, reranking."""

import requests
from llama_index.core import VectorStoreIndex
from llama_index.core.llms import MockLLM
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.vector_stores import FilterOperator, MetadataFilter, MetadataFilters
from llama_index.core.vector_stores.types import VectorStoreQueryMode
from llama_index.postprocessor.jinaai_rerank import JinaRerank

from app.config.settings import Settings
from app.exception_handling.exceptions import RerankError
from app.schema.models import CitedPassage, Passage


def build_search_filters(collection_id: str, document_ids: list[str]) -> MetadataFilters:
    """Scope a search to one collection and to the given ready documents."""
    return MetadataFilters(
        filters=[
            MetadataFilter(key="collection_id", value=collection_id),
            MetadataFilter(
                key="source_document_id", value=document_ids, operator=FilterOperator.IN
            ),
        ]
    )


def fused_search(
    index: VectorStoreIndex,
    filters: MetadataFilters,
    top_k: int,
    query: str,
    settings: Settings,
) -> list[NodeWithScore]:
    """Run the vector and keyword branches, fuse their scores, and return the top matches."""
    vector_branch = index.as_retriever(similarity_top_k=top_k, filters=filters)
    keyword_branch = index.as_retriever(
        similarity_top_k=top_k,
        filters=filters,
        vector_store_query_mode=VectorStoreQueryMode.TEXT_SEARCH,)
    fusion = QueryFusionRetriever(
        [vector_branch, keyword_branch],mode="relative_score",
        retriever_weights=_fusion_weights(settings),
        similarity_top_k=top_k,
        num_queries=1,
        # Passing None would make LlamaIndex use its global default LLM (OpenAI, needs a key).
        # MockLLM is never called: with num_queries=1 the retriever skips query generation.
        llm=MockLLM(),
        use_async=False,
    )
    return fusion.retrieve(query)


def _fusion_weights(settings: Settings) -> list[float]:
    """Return the vector and keyword weights, in the order the fusion retriever expects."""
    return [settings.retrieval_vector_weight, settings.retrieval_keyword_weight]


def to_passage(match: NodeWithScore) -> Passage:
    """Convert a retrieved node into the public passage model."""
    meta = match.node.metadata
    return Passage(
        chunk_id=meta["chunk_id"],
        document_id=meta["source_document_id"],
        filename=meta["filename"],
        page=meta["page"],
        text=match.node.get_content(),
        score=match.get_score(),
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
    ranked = _run_rerank(nodes, query, top_n, settings)
    return [
        CitedPassage(
            source_id=index,
            passage=by_id[match.node.node_id],
            rerank_score=match.get_score(),
        )
        for index, match in enumerate(ranked, start=1)
    ]


def _run_rerank(
    nodes: list[NodeWithScore], query: str, top_n: int, settings: Settings
) -> list[NodeWithScore]:
    """Rank nodes with Jina's reranker. Raises RerankError on a missing key or failed call."""
    key = settings.jina_api_key.get_secret_value().strip()
    if not key:
        raise RerankError("Set JINA_API_KEY in .env to enable reranking.")
    reranker = JinaRerank(api_key=key, top_n=top_n, model=settings.jina_rerank_model)
    try:
        return reranker.postprocess_nodes(nodes, query_str=query)
    except (RuntimeError, KeyError, requests.RequestException) as error:
        raise RerankError("Jina reranking request failed.") from error


def _unique_by_chunk(passages: list[Passage]) -> dict[str, Passage]:
    """Map each chunk ID to its passage, dropping repeats with the same normalized text."""
    seen_text: dict[str, Passage] = {}
    for passage in passages:
        seen_text.setdefault(" ".join(passage.text.split()), passage)
    return {str(passage.chunk_id): passage for passage in seen_text.values()}
