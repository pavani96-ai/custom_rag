"""OpenSearch access for chunk text and vectors. Uses the native OpenSearch Python SDK."""

import json

from opensearchpy import NotFoundError, OpenSearch, RequestError

INDEX_NAME = "chunks_jina_v5_512_sentences"


class IndexingError(Exception):
    """Raised when OpenSearch rejects a request or a bulk write has item errors."""


def index_definition(dimension: int) -> dict:
    """Return the index settings and mappings for chunk text, vectors, and access fields."""
    keyword = {"type": "keyword"}
    return {
        "settings": {"index": {"knn": True}},
        "mappings": {
            "properties": {
                "chunk_id": keyword,
                "workspace_id": keyword,
                "collection_id": keyword,
                "document_id": keyword,
                "filename": keyword,
                "page": {"type": "integer"},
                "text": {"type": "text"},
                "embedding": {"type": "knn_vector", "dimension": dimension},
            }
        },
    }


def ensure_index(client: OpenSearch, dimension: int) -> None:
    """Create the chunk index if it does not exist yet."""
    if client.indices.exists(index=INDEX_NAME):
        return
    try:
        client.indices.create(index=INDEX_NAME, body=index_definition(dimension))
    except RequestError as exc:
        if exc.error != "resource_already_exists_exception":
            raise


def bulk_index(client: OpenSearch, documents: list[dict]) -> None:
    """Write chunk documents in one bulk request. Re-writing a chunk ID replaces it."""
    if not documents:
        return
    lines: list[str] = []
    for document in documents:
        lines.append(json.dumps({"index": {"_index": INDEX_NAME, "_id": document["chunk_id"]}}))
        lines.append(json.dumps(document))
    body = "\n".join(lines) + "\n"
    response = client.bulk(body=body, params={"refresh": "wait_for"})
    if response.get("errors"):
        raise IndexingError("bulk write reported errors")


def count_chunks(client: OpenSearch, document_id: str) -> int | None:
    """Count a document's searchable chunks. Return None if the index is missing."""
    try:
        result = client.count(
            index=INDEX_NAME,
            body={"query": {"term": {"document_id": document_id}}},
        )
    except NotFoundError:
        return None
    if result["_shards"]["failed"]:
        raise IndexingError("chunk count reported shard failures")
    return result["count"]
