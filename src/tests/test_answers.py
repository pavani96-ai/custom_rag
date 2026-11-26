"""Check that answers cite passages from the existing retrieval pipeline."""

import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx

from app.api import answer_pipeline
from app.api import routes as answers
from app.api.routes import Passage, SearchIn
from app.config.settings import Settings
from app.schema.models import GeneratedAnswer


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

    def search(_collection, body, _conn, _embedder):
        assert body.top_k == 20
        return [other, passage, duplicate]

    def rerank(url, *, headers, json, timeout):
        assert url == "https://api.jina.ai/v1/rerank"
        assert headers["Authorization"] == "Bearer test"
        assert json["documents"] == [other.text, passage.text]
        assert json["top_n"] == 2
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"results": [
                {"index": 1, "relevance_score": 0.98},
                {"index": 0, "relevance_score": 0.1},
            ]},
        )

    monkeypatch.setattr(answers, "search_collection", search)
    monkeypatch.setattr(httpx, "post", rerank)
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
    monkeypatch.setattr(answers, "get_settings", lambda: Settings(jina_api_key="test"))

    result = answers.ask_collection(
        uuid4(), SearchIn(query="Are internal memos sensitive?"), Mock(), Mock(),
        include_contexts=True,
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

    result = answers.ask_collection(uuid4(), SearchIn(query="question"), Mock(), Mock())

    assert result.sources == []
    assert "enough evidence" in result.answer
    client_factory.assert_not_called()
