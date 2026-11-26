"""Tests for search routing through the LlamaIndex chunk index. No real OpenSearch is called."""

import json
from unittest.mock import Mock
from uuid import UUID, uuid4

from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.utils import node_to_metadata_dict

from app.api import answer_pipeline
from app.api import routes as retrieval
from app.api.main import app
from app.search.opensearch import INDEX_NAME


def wrapper_hit(chunk_id: str, text: str, document_id: str, score: float) -> dict:
    """Build one hit in the shape the LlamaIndex OpenSearch wrapper parses."""
    node = TextNode(
        id_=chunk_id,
        text=text,
        metadata={
            "chunk_id": chunk_id,
            "source_document_id": document_id,
            "filename": "report.pdf",
            "page": 2,
        },
    )
    return {
        "_id": chunk_id,
        "_score": score,
        "_source": {"text": text, "metadata": node_to_metadata_dict(node, remove_text=True)},
    }


def test_search_returns_ranked_passages(monkeypatch) -> None:
    """Vector and keyword branches are fused, and each passage keeps its citation metadata."""
    collection_id, document_id = str(uuid4()), str(uuid4())
    vector_id, keyword_id = str(uuid4()), str(uuid4())
    embedder = Mock()
    embedder.dimension = 512
    embedder.embed.return_value = [[0.5, 0.5]]
    monkeypatch.setattr(retrieval, "collection_exists", lambda conn, cid: True)
    monkeypatch.setattr(answer_pipeline, "ready_document_ids", lambda conn, cid: [document_id])

    client = Mock()
    client.info.return_value = {"version": {"number": "2.18.0"}}
    seen: list[str] = []

    def search(*, index, body, **kwargs):  # type: ignore[no-untyped-def]
        assert index == INDEX_NAME
        query = json.dumps(body["query"])
        assert "metadata.collection_id" in query and collection_id in query
        if "knn" in query:
            seen.append("vector")
            hit = wrapper_hit(vector_id, "A passage from page two.", document_id, 1.5)
        else:
            seen.append("keyword")
            hit = wrapper_hit(keyword_id, "Keyword match.", document_id, 1.5)
        return {"timed_out": False, "hits": {"hits": [hit]}}

    client.search.side_effect = search
    monkeypatch.setattr(answer_pipeline, "OpenSearch", lambda *args, **kwargs: client)
    assert "post" in app.openapi()["paths"]["/collections/{collection_id}/search"]

    response = retrieval.search_collection(
        UUID(collection_id), retrieval.SearchIn(query=" A question? ", top_k=3), Mock(), embedder
    )

    assert sorted(seen) == ["keyword", "vector"]
    scores = {passage.chunk_id: passage.score for passage in response}
    assert scores == {UUID(vector_id): 0.6, UUID(keyword_id): 0.4}
    assert all(passage.filename == "report.pdf" and passage.page == 2 for passage in response)
    client.close.assert_called_once()
    embedder.embed.assert_called_with(["A question?"])


def test_empty_collection_skips_embedding(monkeypatch) -> None:
    """A collection with no ready documents returns nothing and never calls the embedder."""
    embedder = Mock()
    monkeypatch.setattr(retrieval, "collection_exists", lambda conn, cid: True)
    monkeypatch.setattr(answer_pipeline, "ready_document_ids", lambda conn, cid: [])
    response = retrieval.search_collection(
        uuid4(), retrieval.SearchIn(query="question"), Mock(), embedder
    )
    assert response == []
    embedder.embed.assert_not_called()
