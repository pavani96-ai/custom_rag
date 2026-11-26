"""Tests for the chunk index: the LlamaIndex vector store on the native client, and chunk counts."""

from unittest.mock import Mock

import pytest
from opensearchpy import NotFoundError

from app.config.settings import get_settings
from app.exception_handling.exceptions import IndexingError
from app.rag.vectorstore import build_vector_store, count_chunks


def test_vector_store_uses_chunk_index_dimension_and_cosine_method() -> None:
    """The wrapper writes to the chunk index with 512-dim vectors and cosine similarity."""
    client = Mock()
    store = build_vector_store(client, 512, get_settings())
    wrapper = store._client
    assert wrapper._index == get_settings().opensearch_index_name
    assert wrapper._dim == 512
    assert wrapper._method["space_type"] == "cosinesimil"
    assert wrapper._method["engine"] == "lucene"


def test_vector_store_uses_the_injected_native_client() -> None:
    """Our configured client is the one the wrapper talks to, so no second client is built."""
    client = Mock()
    store = build_vector_store(client, 512, get_settings())
    assert store._client._os_client is client


def test_count_chunks_filters_by_document_id() -> None:
    """Counts use the keyword form of metadata.document_id, so the match is exact."""
    client = Mock()
    client.count.return_value = {"count": 3, "_shards": {"failed": 0}}

    assert count_chunks(client, "doc-1", get_settings()) == 3
    body = client.count.call_args.kwargs["body"]
    assert body == {"query": {"term": {"metadata.source_document_id.keyword": "doc-1"}}}


def test_count_chunks_returns_none_when_index_is_missing() -> None:
    """A missing index means no chunks have been written yet."""
    client = Mock()
    client.count.side_effect = NotFoundError(404, "index_not_found_exception", {})
    assert count_chunks(client, "doc-1", get_settings()) is None


def test_count_chunks_raises_on_shard_failures() -> None:
    """Partial counts are reported as errors, not as a smaller number."""
    client = Mock()
    client.count.return_value = {"count": 1, "_shards": {"failed": 1}}
    with pytest.raises(IndexingError):
        count_chunks(client, "doc-1", get_settings())
