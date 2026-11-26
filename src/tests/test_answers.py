"""Check that answers cite passages from the existing retrieval pipeline."""

import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import requests

from app.api import answer_pipeline
from app.api import routes as answers
from app.api.routes import Passage, SearchIn
from app.config.settings import Settings
from app.schema.models import GeneratedAnswer


class FakeResponse:
    """Stands in for a requests response with a JSON body."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        """Return the canned JSON payload."""
        return self._payload


def test_answer_resolves_citation_to_passage(monkeypatch) -> None:
    passage = Passage(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="guide.pdf",
        page=2,
        text="Internal company memos are generally sensitive.",
        score=0.9,
    )
    duplicate = passage.model_copy(update={"chunk_id": uuid4(), "document_id": uuid4()})
    other = passage.model_copy(
        update={"chunk_id": uuid4(), "text": "An unrelated passage.", "score": 1.0}
    )

    def search(_collection, body, _conn, _embedder, _settings):
        assert body.top_k == 20
        return [other, passage, duplicate]

    def rerank(session, url, *, json, **kwargs):  # type: ignore[no-untyped-def]
        assert url.endswith("/rerank")
        assert session.headers["Authorization"] == "Bearer test"
        assert json["documents"] == [other.text, passage.text]
        assert json["model"] == "jina-reranker-v3.5"
        assert json["top_n"] == 5
        return FakeResponse({"results": [
            {"index": 1, "relevance_score": 0.98},
            {"index": 0, "relevance_score": 0.1},
        ]})

    monkeypatch.setattr(answers, "search_collection", search)
    monkeypatch.setattr(requests.Session, "post", rerank)
    client = Mock()
    client.chat.return_value = SimpleNamespace(
        message=SimpleNamespace(
            content=json.dumps(
                {"answer": "Internal memos are generally sensitive [1].", "source_ids": [1]}
            )
        )
    )
    monkeypatch.setattr(answer_pipeline, "build_llm", lambda settings: client)
    monkeypatch.setattr(
        answer_pipeline, "collection_prompt_settings", lambda conn, cid: {"format": "bullets"}
    )

    result = answers.ask_collection(
        uuid4(), SearchIn(query="Are internal memos sensitive?"), Mock(), Mock(),
        include_contexts=True,
        settings=Settings(jina_api_key="test"),
    )

    assert result.answer == "Internal memos are generally sensitive [1]."
    assert result.sources[0].passage == passage
    assert result.sources[0].source_id == 1
    assert result.sources[0].rerank_score == 0.98
    assert [item.passage for item in result.retrieved_contexts] == [passage, other]
    messages = client.chat.call_args.args[0]
    assert json.loads(messages[1].content)["passages"][0]["text"] == passage.text
    assert "bulleted list" in messages[0].content
    assert client.chat.call_args.kwargs["generation_config"]["response_schema"] is (
        GeneratedAnswer
    )


def test_empty_retrieval_skips_gemini(monkeypatch) -> None:
    monkeypatch.setattr(answers, "search_collection", lambda *args: [])
    client_factory = Mock()
    monkeypatch.setattr(answer_pipeline, "build_llm", client_factory)

    result = answers.ask_collection(
        uuid4(), SearchIn(query="question"), Mock(), Mock(), settings=Settings()
    )

    assert result.sources == []
    assert "enough evidence" in result.answer
    client_factory.assert_not_called()
