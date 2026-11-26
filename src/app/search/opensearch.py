"""Chunk index on OpenSearch: LlamaIndex's vector store wrapper on the native SDK client."""

from llama_index.vector_stores.opensearch import OpensearchVectorClient, OpensearchVectorStore
from opensearchpy import NotFoundError, OpenSearch

from app.config.settings import get_settings

INDEX_NAME = "chunks_jina_v5_512_v2"
TEXT_FIELD = "text"
EMBEDDING_FIELD = "embedding"
METHOD = {
    "name": "hnsw",
    "space_type": "cosinesimil",
    "engine": "lucene",
    "parameters": {"ef_construction": 256, "m": 48},
}


class IndexingError(Exception):
    """Raised when OpenSearch reports a shard failure while counting chunks."""


def build_vector_store(client: OpenSearch, dimension: int) -> OpensearchVectorStore:
    """Return the chunk vector store on the native client. The index is created on first use."""
    vector_client = OpensearchVectorClient(
        endpoint=get_settings().opensearch_url,
        index=INDEX_NAME,
        dim=dimension,
        embedding_field=EMBEDDING_FIELD,
        text_field=TEXT_FIELD,
        method=METHOD,
        os_client=client,
    )
    return OpensearchVectorStore(client=vector_client)


def count_chunks(client: OpenSearch, document_id: str) -> int | None:
    """Count a document's searchable chunks. Return None if the index is missing."""
    try:
        result = client.count(
            index=INDEX_NAME,
            body={"query": {"term": {"metadata.source_document_id.keyword": document_id}}},
        )
    except NotFoundError:
        return None
    if result["_shards"]["failed"]:
        raise IndexingError("chunk count reported shard failures")
    return result["count"]
