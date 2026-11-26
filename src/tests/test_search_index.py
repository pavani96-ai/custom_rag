"""Tests for the native OpenSearch SDK calls for indexing."""

import json
from unittest.mock import Mock

import pytest

from app.search.opensearch import (
    INDEX_NAME,
    IndexingError,
    bulk_index,
    ensure_index,
    index_definition,
)


def test_index_definition_sets_vector_dimension() -> None:
    mapping = index_definition(512)["mappings"]["properties"]["embedding"]
    assert mapping == {"type": "knn_vector", "dimension": 512}


def test_ensure_index_creates_missing_index() -> None:
    client = Mock()
    client.indices.exists.return_value = False

    ensure_index(client, 512)

    client.indices.exists.assert_called_once_with(index=INDEX_NAME)
    client.indices.create.assert_called_once_with(index=INDEX_NAME, body=index_definition(512))


def test_ensure_index_skips_existing_index() -> None:
    client = Mock()
    client.indices.exists.return_value = True

    ensure_index(client, 512)

    client.indices.create.assert_not_called()


def test_bulk_index_sends_ndjson_with_chunk_ids() -> None:
    client = Mock()
    client.bulk.return_value = {"errors": False}

    bulk_index(client, [{"chunk_id": "c1", "text": "hi"}])

    kwargs = client.bulk.call_args.kwargs
    assert kwargs["params"] == {"refresh": "wait_for"}
    assert [json.loads(line) for line in kwargs["body"].splitlines()] == [
        {"index": {"_index": INDEX_NAME, "_id": "c1"}},
        {"chunk_id": "c1", "text": "hi"},
    ]


def test_bulk_index_raises_on_item_errors() -> None:
    client = Mock()
    client.bulk.return_value = {"errors": True}
    with pytest.raises(IndexingError):
        bulk_index(client, [{"chunk_id": "c1"}])
