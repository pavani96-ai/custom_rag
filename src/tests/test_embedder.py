"""Verify the Jina embedding request and response without a live key."""

import pytest
import requests
from pydantic import SecretStr

from app.config.settings import Settings
from app.exception_handling.exceptions import EmbeddingError
from app.rag.embedder import JinaEmbedder


class FakeResponse:
    """Stands in for a requests response with a JSON body."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        """Return the canned JSON payload."""
        return self._payload


@pytest.mark.parametrize("task", ["retrieval.passage", "retrieval.query"])
def test_jina_embedder_sends_task_and_keeps_input_order(monkeypatch, task) -> None:
    """Each request names its retrieval task and vectors come back in input order."""
    seen: dict = {}

    def post(session, url, *, json, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(url=url, body=json, auth=session.headers["Authorization"])
        return FakeResponse({"data": [
            {"index": 1, "embedding": [0.2] * 512},
            {"index": 0, "embedding": [0.1] * 512},
        ]})

    monkeypatch.setattr(requests.Session, "post", post)
    embedder = JinaEmbedder(Settings(jina_api_key=SecretStr("test-key")), task)
    vectors = embedder.embed(["first", "second"])
    assert vectors == [[0.1] * 512, [0.2] * 512]
    assert seen["url"].endswith("/embeddings")
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["task"] == task
    assert seen["body"]["dimensions"] == 512
    assert seen["body"]["input"] == ["first", "second"]


def test_missing_key_only_errors_when_embedding_is_needed() -> None:
    """Empty input needs no key, but any text fails fast without a key."""
    embedder = JinaEmbedder(Settings(jina_api_key=SecretStr("")), "retrieval.passage")
    assert embedder.embed([]) == []
    with pytest.raises(EmbeddingError, match="JINA_API_KEY"):
        embedder.embed(["some text"])
