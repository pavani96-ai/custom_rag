"""Tests for chat turns: citation checks, streamed events, saved turns, and the chat routes.

Gemini, the database, and storage are replaced by fakes. No test calls a real service.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import routes
from app.api.main import app
from app.rag.chat import (
    build_contents,
    citations_are_valid,
    cited_ids,
    sse_frame,
)
from app.rag.prompts import with_style
from app.schema.models import CitedPassage, CollectionIn, Passage
from app.storage import LocalStorage


def passage(source_id: int, text: str) -> CitedPassage:
    """Build a cited passage for tests."""
    return CitedPassage(
        source_id=source_id,
        rerank_score=0.9,
        passage=Passage(
            chunk_id=uuid4(),
            document_id=uuid4(),
            filename="guide.pdf",
            page=3,
            text=text,
            score=0.5,
        ),
    )


def chunks(*texts: str) -> list[SimpleNamespace]:
    """Fake streamed chunks from the LlamaIndex model."""
    return [SimpleNamespace(delta=text) for text in texts]


def parse_events(body: str) -> list[tuple[str, dict]]:
    """Split a server-sent event body into (event, data) pairs."""
    events = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_style_rules_follow_collection_prompt_settings() -> None:
    """Format and length settings add their rules; the defaults add nothing."""
    base = "Base instruction."
    assert with_style(base, {}) == base
    assert with_style(base, {"format": "auto", "length": "standard"}) == base
    styled = with_style(base, {"format": "bullets", "length": "brief"})
    assert "bulleted list" in styled
    assert "two or three sentences" in styled
    assert with_style(base, {"format": "prose"}).endswith("Do not use bullet points.")


def test_unknown_preference_values_are_rejected() -> None:
    """The collection model only accepts the listed format and length values."""
    with pytest.raises(ValidationError):
        CollectionIn(title="Notes", response_preferences={"format": "table"})
    assert CollectionIn(title="Notes").response_preferences.format == "auto"


def test_cited_ids_are_distinct_and_in_order() -> None:
    """Repeated markers count once, and order follows the answer text."""
    assert cited_ids("First [2], then [1], and [2] again.") == [2, 1]
    assert cited_ids("Both [1, 2] and [3][1].") == [1, 2, 3]
    assert cited_ids("No citations here.") == []


def test_citations_must_refer_to_supplied_passages() -> None:
    """IDs outside 1..count are rejected."""
    assert citations_are_valid([1, 2], 2)
    assert citations_are_valid([], 0)
    assert not citations_are_valid([3], 2)
    assert not citations_are_valid([0], 2)


def test_build_contents_keeps_passages_and_history_as_data() -> None:
    """The model input is JSON with the question, history, and passage IDs."""
    sources = [passage(1, "Memos are sensitive.")]
    history = [{"role": "user", "content": "earlier"}]
    payload = json.loads(build_contents("Are memos sensitive?", history, sources))
    assert payload["question"] == "Are memos sensitive?"
    assert payload["history"] == history
    assert payload["passages"] == [{"source_id": 1, "text": "Memos are sensitive."}]


def test_sse_frame_is_one_event_with_json_data() -> None:
    """Each frame has an event line and a single data line that parses as JSON."""
    frame = sse_frame("delta", {"text": "a\nb"})
    assert frame.startswith("event: delta\ndata: ")
    assert frame.endswith("\n\n")
    assert json.loads(frame.split("data: ", 1)[1]) == {"text": "a\nb"}


def test_turn_streams_deltas_then_saves_cited_turn(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Deltas stream in order, the turn is saved once, and done carries the cited passage."""
    sources = [passage(1, "Memos are sensitive."), passage(2, "Other text.")]
    client = Mock()
    client.stream_chat.return_value = chunks("Memos are sensitive [1].", "")
    saved = {}

    def fake_persist(settings, conversation_id, question, answer, citations):  # type: ignore[no-untyped-def]
        saved.update(question=question, answer=answer, citations=citations)
        return "message-id"

    monkeypatch.setattr(routes, "persist_turn", fake_persist)
    conversation_id = uuid4()
    body = "".join(
        routes.turn_events(
            llm=client,
            settings=Mock(),
            conversation_id=conversation_id,
            question="Are memos sensitive?",
            contents="{}",
            instruction="rules",
            sources=sources,
        )
    )
    events = parse_events(body)

    assert events[0] == ("conversation", {"conversation_id": str(conversation_id)})
    assert events[1] == ("delta", {"text": "Memos are sensitive [1]."})
    done = events[-1]
    assert done[0] == "done"
    assert done[1]["answer"] == "Memos are sensitive [1]."
    assert [c["source_id"] for c in done[1]["citations"]] == [1]
    assert saved["citations"][0]["passage"]["text"] == "Memos are sensitive."


def test_turn_with_invalid_citation_reports_error_and_saves_nothing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An answer citing a passage that was not supplied is not saved."""
    client = Mock()
    client.stream_chat.return_value = chunks("Wrong source [5].")
    persist = Mock()
    monkeypatch.setattr(routes, "persist_turn", persist)
    body = "".join(
        routes.turn_events(
            llm=client,
            settings=Mock(),
            conversation_id=uuid4(),
            question="q",
            contents="{}",
            instruction="rules",
            sources=[passage(1, "text")],
        )
    )
    assert parse_events(body)[-1][0] == "error"
    persist.assert_not_called()


def test_turn_without_passages_abstains_without_calling_gemini(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """No retrieved passages means no model call, an abstention answer, and a saved turn."""
    persist = Mock(return_value="message-id")
    monkeypatch.setattr(routes, "persist_turn", persist)
    body = "".join(
        routes.turn_events(
            llm=None,
            settings=Mock(),
            conversation_id=uuid4(),
            question="q",
            contents="{}",
            instruction="rules",
            sources=[],
        )
    )
    done = parse_events(body)[-1]
    assert done[0] == "done"
    assert "enough evidence" in done[1]["answer"]
    assert done[1]["citations"] == []
    persist.assert_called_once()


def test_gemini_failure_reports_error_without_saving(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A provider error becomes an error event, and the turn is not saved."""
    client = Mock()
    client.stream_chat.side_effect = routes.GoogleAuthError("no credentials")
    persist = Mock()
    monkeypatch.setattr(routes, "persist_turn", persist)
    body = "".join(
        routes.turn_events(
            llm=client,
            settings=Mock(),
            conversation_id=uuid4(),
            question="q",
            contents="{}",
            instruction="rules",
            sources=[passage(1, "text")],
        )
    )
    assert parse_events(body)[-1] == ("error", {"detail": routes.GENERATION_UNAVAILABLE})
    persist.assert_not_called()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Test client with the database and storage replaced by fakes."""
    monkeypatch.setattr(routes, "collection_exists", lambda conn, cid: True)
    app.dependency_overrides[routes.get_db] = lambda: None
    app.dependency_overrides[routes.get_storage] = lambda: LocalStorage(tmp_path)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_chat_stream_rejects_unknown_collection(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A question for a missing collection gets 404 before any retrieval."""
    monkeypatch.setattr(routes, "collection_exists", lambda conn, cid: False)
    response = client.post(f"/collections/{uuid4()}/chat/stream", json={"query": "hi"})
    assert response.status_code == 404


def test_chat_stream_rejects_empty_question(client: TestClient) -> None:
    """Empty questions fail validation before any database call."""
    response = client.post(f"/collections/{uuid4()}/chat/stream", json={"query": " "})
    assert response.status_code == 422


def test_chat_stream_creates_conversation_for_first_turn(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A first turn creates the conversation with a title from the question."""
    created = {}
    monkeypatch.setattr(routes, "collection_workspace", lambda conn, cid: str(uuid4()))
    monkeypatch.setattr(
        routes, "create_conversation", lambda conn, **kw: created.update(kw)
    )
    monkeypatch.setattr(routes, "retrieve_for_question", lambda *args: [])
    monkeypatch.setattr(routes, "collection_prompt_settings", lambda conn, cid: {})
    monkeypatch.setattr(routes, "persist_turn", lambda *args: "message-id")
    response = client.post(
        f"/collections/{uuid4()}/chat/stream", json={"query": "What is deep learning?"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert created["title"] == "What is deep learning?"
    assert created["user_id"] == routes.get_settings().dev_user_id
    events = parse_events(response.text)
    assert events[0][0] == "conversation"
    assert events[-1][0] == "done"


def test_chat_stream_rejects_other_collection_conversation(
    client: TestClient, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """A follow-up naming a conversation that is not in this collection gets 404."""
    monkeypatch.setattr(routes, "collection_workspace", lambda conn, cid: str(uuid4()))
    monkeypatch.setattr(routes, "conversation_title", lambda *args: None)
    response = client.post(
        f"/collections/{uuid4()}/chat/stream",
        json={"query": "follow up", "conversation_id": str(uuid4())},
    )
    assert response.status_code == 404


def test_conversation_detail_returns_messages_with_citations(
    client: TestClient, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Reopening a conversation returns messages in order with their saved citations."""
    cited = passage(1, "Memos are sensitive.").model_dump(mode="json")
    now = "2026-11-26T10:00:00+00:00"
    monkeypatch.setattr(routes, "conversation_title", lambda *args: "Memos")
    monkeypatch.setattr(
        routes,
        "conversation_messages",
        lambda conn, cid: [
            {"id": uuid4(), "role": "user", "content": "q", "citations": [], "created_at": now},
            {"id": uuid4(), "role": "assistant", "content": "a [1]", "citations": [cited],
             "created_at": now},
        ],
    )
    response = client.get(f"/collections/{uuid4()}/conversations/{uuid4()}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Memos"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][1]["citations"][0]["passage"]["text"] == "Memos are sensitive."


def test_original_returns_stored_pdf(client: TestClient, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The source viewer gets the stored bytes for a document in the collection."""
    key = "collections/c/originals/abc.pdf"
    (tmp_path / key).parent.mkdir(parents=True)
    (tmp_path / key).write_bytes(b"%PDF-1.4 test")
    monkeypatch.setattr(routes, "document_storage_key", lambda conn, cid, did: key)
    response = client.get(f"/collections/{uuid4()}/documents/{uuid4()}/original")
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 test"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == "inline"


def test_original_unknown_document_is_404(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A document outside the collection is reported as not found."""
    monkeypatch.setattr(routes, "document_storage_key", lambda conn, cid, did: None)
    response = client.get(f"/collections/{uuid4()}/documents/{uuid4()}/original")
    assert response.status_code == 404


def test_author_instructions_are_added_to_the_prompt() -> None:
    """Collection instructions join the system prompt, below the citation rules."""
    styled = with_style("Base.", {"instructions": "  Write for new staff.  "})
    assert "Write for new staff." in styled
    assert "unless they conflict" in styled
    assert with_style("Base.", {"instructions": "   "}) == "Base."


def test_job_status_returns_the_worker_state(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The status endpoint reports the job's state and document for the upload page."""
    job_id = uuid4()
    document_id = uuid4()
    monkeypatch.setattr(
        routes,
        "job_status",
        lambda conn, cid, jid: {
            "job_id": job_id,
            "document_id": document_id,
            "status": "running",
            "error_message": None,
        },
    )
    response = client.get(f"/collections/{uuid4()}/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_unknown_job_is_404(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A job outside the collection, or one that does not exist, is not found."""
    monkeypatch.setattr(routes, "job_status", lambda conn, cid, jid: None)
    response = client.get(f"/collections/{uuid4()}/jobs/{uuid4()}")
    assert response.status_code == 404
