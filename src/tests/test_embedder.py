"""Verify the hosted Jina request and response without a live key."""

import httpx
import pytest
from pydantic import SecretStr

from app.rag.providers.embedder import EmbeddingError, JinaEmbedder


@pytest.mark.parametrize("task", ["retrieval.passage", "retrieval.query"])
def test_jina_embedder_preserves_input_order(monkeypatch, task) -> None:
    def post(url, *, headers, json, timeout):
        assert url == "https://api.jina.ai/v1/embeddings"
        assert headers["Authorization"] == "Bearer test-key"
        assert json == {
            "model": "jina-embeddings-v5-text-small",
            "task": task,
            "dimensions": 512,
            "embedding_type": "float",
            "input": ["first", "second"],
        }
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"data": [
                {"index": 1, "embedding": [0.2] * 512},
                {"index": 0, "embedding": [0.1] * 512},
            ]},
        )

    monkeypatch.setattr(httpx, "post", post)
    assert JinaEmbedder(SecretStr("test-key"), task).embed(["first", "second"]) == [
        [0.1] * 512,
        [0.2] * 512,
    ]


def test_missing_key_only_errors_when_embedding_is_needed() -> None:
    embedder = JinaEmbedder(SecretStr(""), "retrieval.passage")
    assert embedder.embed([]) == []
    with pytest.raises(EmbeddingError, match="JINA_API_KEY"):
        embedder.embed(["some text"])
