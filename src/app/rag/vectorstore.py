"""Chunk index on OpenSearch: LlamaIndex's vector store wrapper on the native SDK client."""

from llama_index.vector_stores.opensearch import OpensearchVectorClient, OpensearchVectorStore
from opensearchpy import NotFoundError, OpenSearch

from app.config.settings import Settings
from app.exception_handling.exceptions import IndexingError


def build_vector_store(
    client: OpenSearch, dimension: int, settings: Settings
) -> OpensearchVectorStore:
    """Return the chunk vector store on the native client. The index is created on first use."""
    vector_client = OpensearchVectorClient(
        endpoint=settings.opensearch_url,
        index=settings.opensearch_index_name,
        dim=dimension,
        embedding_field=settings.opensearch_embedding_field,
        text_field=settings.opensearch_text_field,
        method=_hnsw_method(settings),
        os_client=client,
    )
    return OpensearchVectorStore(client=vector_client)


def _hnsw_method(settings: Settings) -> dict:
    """Return the approximate k-NN method settings for the chunk index."""
    return {
        "name": "hnsw",
        "space_type": settings.opensearch_space_type,
        "engine": settings.opensearch_engine,
        "parameters": {
            "ef_construction": settings.opensearch_hnsw_ef_construction,
            "m": settings.opensearch_hnsw_m,
        },
    }


def count_chunks(client: OpenSearch, document_id: str, settings: Settings) -> int | None:
    """Count a document's searchable chunks. Return None if the index is missing."""
    try:
        result = client.count(
            index=settings.opensearch_index_name,
            body={"query": {"term": {"metadata.source_document_id.keyword": document_id}}},
        )
    except NotFoundError:
        return None
    if result["_shards"]["failed"]:
        raise IndexingError("chunk count reported shard failures")
    return result["count"]
