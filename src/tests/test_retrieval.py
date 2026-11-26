"""Exercise search routing and the OpenSearch request without loading an embedding model."""

from unittest.mock import Mock
from uuid import UUID, uuid4

from app.api import routes as retrieval
from app.api.main import app
from app.search.opensearch import INDEX_NAME


def test_search_returns_ranked_passages(monkeypatch) -> None:
    collection_id, document_id, chunk_id = (str(uuid4()) for _ in range(3))
    passage = {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "filename": "report.pdf",
        "page": 2,
        "text": "A passage from page two.",
    }
    keyword_passage = {**passage, "chunk_id": str(uuid4()), "text": "Keyword match."}
    embedder = Mock()
    embedder.embed.return_value = [[0.5, 0.5]]
    monkeypatch.setattr(retrieval, "collection_exists", lambda conn, cid: True)
    monkeypatch.setattr(retrieval, "ready_document_ids", lambda conn, cid: [document_id])

    client = Mock()
    filters = [
        {"term": {"collection_id": collection_id}},
        {"terms": {"document_id": [document_id]}},
    ]

    def search(*, index, body, params):
        assert index == INDEX_NAME
        assert body["size"] == 3
        assert params["allow_partial_search_results"] == "false"
        if "script_score" in body["query"]:
            scoring = body["query"]["script_score"]
            assert scoring["query"]["bool"]["filter"] == filters
            assert scoring["script"]["params"]["query_value"] == [0.5, 0.5]
            hit = passage
        else:
            assert body["query"] == {
                "bool": {"filter": filters, "must": [{"match": {"text": "A question?"}}]}
            }
            hit = keyword_passage
        return {"timed_out": False, "hits": {"hits": [{"_source": hit, "_score": 1.5}]}}

    client.search.side_effect = search
    monkeypatch.setattr(retrieval, "OpenSearch", lambda *args, **kwargs: client)
    assert "post" in app.openapi()["paths"]["/collections/{collection_id}/search"]
    conn = Mock()
    response = retrieval.search_collection(
        UUID(collection_id), retrieval.SearchIn(query=" A question? ", top_k=3), conn, embedder
    )
    assert [hit.model_dump(mode="json") for hit in response] == [
        {**passage, "score": 0.6},
        {**keyword_passage, "score": 0.4},
    ]
    assert client.search.call_count == 2
    client.close.assert_called_once()
    embedder.embed.assert_called_once_with(["A question?"])


def test_empty_collection_skips_embedding(monkeypatch) -> None:
    embedder = Mock()
    monkeypatch.setattr(retrieval, "collection_exists", lambda conn, cid: True)
    monkeypatch.setattr(retrieval, "ready_document_ids", lambda conn, cid: [])
    response = retrieval.search_collection(
        uuid4(), retrieval.SearchIn(query="question"), Mock(), embedder
    )
    assert response == []
    embedder.embed.assert_not_called()
