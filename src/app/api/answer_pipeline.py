"""Answer pipeline: scoped search, reranking, cited answers, and streamed chat turns.

Route handlers call these functions after they check the collection and resolve its workspace.
Functions here raise HTTPException for upstream failures; a later step can turn those into
domain errors that routes map to HTTP.
"""

import json
from collections.abc import Generator, Iterator
from contextlib import closing
from uuid import UUID, uuid4

import psycopg
from fastapi import HTTPException
from google.auth.exceptions import GoogleAuthError
from google.genai import errors
from httpx import RequestError
from llama_index.core.base.llms.types import ChatResponse
from llama_index.llms.google_genai import GoogleGenAI
from opensearchpy import OpenSearch, OpenSearchException
from pydantic import ValidationError

from app.config.settings import Settings, get_settings
from app.db.collections import ready_document_ids
from app.db.conversations import (
    collection_prompt_settings,
    conversation_title,
    create_conversation,
    load_history,
    save_turn,
)
from app.rag.chat import (
    build_contents,
    citations_are_valid,
    cited_ids,
    cited_passages,
    sse_frame,
    stream_answer,
)
from app.rag.llm import build_llm, make_messages
from app.rag.prompts import (
    INSUFFICIENT_EVIDENCE,
    STREAM_INSTRUCTION,
    SYSTEM_INSTRUCTION,
    with_style,
)
from app.rag.providers.embedder import Embedder, EmbeddingError
from app.rag.providers.reranker import RerankError
from app.rag.retrieval import (
    SearchTimeout,
    build_search_filters,
    fused_search,
    rerank_passages,
    to_passage,
)
from app.schema.models import (
    Answer,
    ChatIn,
    CitedPassage,
    GeneratedAnswer,
    Passage,
    SearchIn,
)

GENERATION_UNAVAILABLE = "Gemini generation is unavailable."
SEARCH_UNAVAILABLE = "Search service unavailable."
SAVE_FAILED = "The answer could not be saved."
INVALID_CITED_ANSWER = "Gemini returned an invalid cited answer."


GENERATION_UNAVAILABLE = "Gemini generation is unavailable."


SAVE_FAILED = "The answer could not be saved."


INVALID_CITED_ANSWER = "Gemini returned an invalid cited answer."


SEARCH_UNAVAILABLE = "Search service unavailable."


def search_passages(
    conn: psycopg.Connection, collection_id: UUID, body: SearchIn, embedder: Embedder
) -> list[Passage]:
    """Rank passages from ready documents in the collection. 503 when search is unavailable."""
    document_ids = ready_document_ids(conn, collection_id)
    if not document_ids:
        return []
    filters = build_search_filters(str(collection_id), document_ids)
    try:
        return _run_search(filters, body, embedder)
    except (EmbeddingError, SearchTimeout) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenSearchException as exc:
        raise HTTPException(status_code=503, detail=SEARCH_UNAVAILABLE) from exc


def _run_search(filters: list[dict], body: SearchIn, embedder: Embedder) -> list[Passage]:
    """Open the search client, run the fused search, and convert the matches to passages."""
    with closing(OpenSearch(hosts=[get_settings().opensearch_url], timeout=30)) as client:
        matches = fused_search(client, filters, body.top_k, embedder, body.query)
    return [to_passage(match) for match in matches]


def rerank_sources(
    passages: list[Passage], query: str, top_n: int, settings: Settings
) -> list[CitedPassage]:
    """Rerank passages for citation. Empty input gives no sources. 503 when reranking fails."""
    if not passages:
        return []
    try:
        return rerank_passages(passages, query, top_n, settings)
    except RerankError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def generate_answer(
    conn: psycopg.Connection,
    collection_id: UUID,
    question: str,
    sources: list[CitedPassage],
    settings: Settings,
) -> GeneratedAnswer:
    """Ask Gemini for a structured, cited answer. 502 when the reply does not parse."""
    preferences = collection_prompt_settings(conn, collection_id)
    response = _call_structured_llm(settings, preferences, question, sources)
    try:
        return GeneratedAnswer.model_validate_json(response.message.content or "")
    except ValidationError:
        raise HTTPException(status_code=502, detail="Gemini returned an invalid answer.") from None


def _call_structured_llm(
    settings: Settings,
    preferences: dict,
    question: str,
    sources: list[CitedPassage],
) -> ChatResponse:
    """Send the question and passages to Gemini with a JSON response schema."""
    try:
        return build_llm(settings).chat(
            make_messages(
                with_style(SYSTEM_INSTRUCTION, preferences), _question_payload(question, sources)
            ),
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": GeneratedAnswer,
            },
        )
    except (errors.APIError, GoogleAuthError, RequestError) as exc:
        raise HTTPException(status_code=503, detail=GENERATION_UNAVAILABLE) from exc


def _question_payload(question: str, sources: list[CitedPassage]) -> str:
    """Serialize the question and numbered passages as the model's user message."""
    return json.dumps({
        "question": question,
        "passages": [
            {"source_id": source.source_id, "text": source.passage.text} for source in sources
        ],
    })


def answer_from_generated(
    generated: GeneratedAnswer, sources: list[CitedPassage], include_contexts: bool
) -> Answer:
    """Check the citations in a generated answer and build the response."""
    retrieved_contexts = sources if include_contexts else None
    source_ids = list(dict.fromkeys(generated.source_ids))
    if not source_ids:
        return Answer(
            answer=INSUFFICIENT_EVIDENCE, sources=[], retrieved_contexts=retrieved_contexts
        )
    valid_sources = all(1 <= index <= len(sources) for index in source_ids)
    if not generated.answer.strip() or not valid_sources:
        raise HTTPException(status_code=502, detail="Gemini returned an invalid cited answer.")
    return Answer(
        answer=generated.answer,
        sources=[sources[index - 1] for index in source_ids],
        retrieved_contexts=retrieved_contexts,
    )


def resolve_conversation(
    conn: psycopg.Connection,
    body: ChatIn,
    collection_id: UUID,
    workspace_id: str,
    user_id: UUID,
) -> UUID:
    """Return the conversation to continue, or create one for a first turn. 404 if unknown."""
    if body.conversation_id is None:
        return _create_conversation(conn, body, collection_id, workspace_id, user_id)
    if conversation_title(conn, body.conversation_id, collection_id, user_id) is None:
        raise HTTPException(status_code=404, detail="Unknown conversation.")
    return body.conversation_id


def _create_conversation(
    conn: psycopg.Connection,
    body: ChatIn,
    collection_id: UUID,
    workspace_id: str,
    user_id: UUID,
) -> UUID:
    """Create a conversation titled from the first question and return its ID."""
    conversation_id = uuid4()
    create_conversation(
        conn,
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        collection_id=collection_id,
        user_id=user_id,
        title=body.query[:80],
    )
    return conversation_id


def retrieve_for_question(
    conn: psycopg.Connection,
    embedder: Embedder,
    collection_id: UUID,
    query: str,
    settings: Settings,
) -> list[CitedPassage]:
    """Return the reranked passages that may support an answer. Empty when nothing matched."""
    passages = search_passages(conn, collection_id, SearchIn(query=query, top_k=20), embedder)
    return rerank_sources(passages, query, 5, settings)


def answer_deltas(
    llm: GoogleGenAI | None, contents: str, sources: list[CitedPassage], instruction: str
) -> Iterator[str]:
    """Yield answer text. With no passages there is nothing to send to the model."""
    if not sources or llm is None:
        yield INSUFFICIENT_EVIDENCE
        return
    yield from stream_answer(llm, contents, instruction)


def persist_turn(
    settings: Settings, conversation_id: UUID, question: str, answer: str, citations: list[dict]
) -> str:
    """Save one completed turn on its own connection, since the request connection is closed."""
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        return save_turn(
            conn,
            conversation_id=conversation_id,
            question=question,
            answer=answer,
            citations=citations,
        )


def turn_events(
    *,
    llm: GoogleGenAI | None,
    settings: Settings,
    conversation_id: UUID,
    question: str,
    contents: str,
    sources: list[CitedPassage],
    instruction: str,
) -> Iterator[str]:
    """Stream one answer as server-sent events, then save the turn only if its citations hold."""
    yield sse_frame("conversation", {"conversation_id": str(conversation_id)})
    try:
        raw = yield from _stream_deltas(llm, contents, sources, instruction)
    except (errors.APIError, GoogleAuthError, RequestError):
        yield sse_frame("error", {"detail": GENERATION_UNAVAILABLE})
        return
    yield from _finish_turn(settings, conversation_id, question, raw.strip(), sources)


def _stream_deltas(
    llm: GoogleGenAI | None, contents: str, sources: list[CitedPassage], instruction: str
) -> Generator[str, None, str]:
    """Stream text deltas as SSE frames and return the full raw answer text."""
    parts: list[str] = []
    for delta in answer_deltas(llm, contents, sources, instruction):
        parts.append(delta)
        yield sse_frame("delta", {"text": delta})
    return "".join(parts)


def _finish_turn(
    settings: Settings,
    conversation_id: UUID,
    question: str,
    answer: str,
    sources: list[CitedPassage],
) -> Iterator[str]:
    """Validate the citations, save the turn, and send the final event."""
    ids = cited_ids(answer)
    if not answer or not citations_are_valid(ids, len(sources)):
        yield sse_frame("error", {"detail": INVALID_CITED_ANSWER})
        return
    citations = [passage.model_dump(mode="json") for passage in cited_passages(sources, ids)]
    try:
        message_id = persist_turn(settings, conversation_id, question, answer, citations)
    except psycopg.Error:
        yield sse_frame("error", {"detail": SAVE_FAILED})
        return
    yield sse_frame("done", {"message_id": message_id, "answer": answer, "citations": citations})


def _history(conn: psycopg.Connection, body: ChatIn, conversation_id: UUID) -> list[dict]:
    """Return earlier turns for an existing conversation. A new conversation has none."""
    return [] if body.conversation_id is None else load_history(conn, conversation_id)


def chat_events(
    conn: psycopg.Connection,
    embedder: Embedder,
    collection_id: UUID,
    workspace_id: str,
    body: ChatIn,
    settings: Settings,
) -> Iterator[str]:
    """Prepare one chat turn (conversation, history, retrieval, model) and return its events."""
    conversation_id = resolve_conversation(
        conn, body, collection_id, workspace_id, settings.dev_user_id
    )
    sources = retrieve_for_question(conn, embedder, collection_id, body.query, settings)
    return turn_events(
        llm=build_llm(settings) if sources else None,
        instruction=_turn_instruction(conn, collection_id),
        settings=settings,
        conversation_id=conversation_id,
        question=body.query,
        contents=build_contents(body.query, _history(conn, body, conversation_id), sources),
        sources=sources,
    )




def _turn_instruction(conn: psycopg.Connection, collection_id: UUID) -> str:
    """Return the streaming instruction with this collection's answer style added."""
    return with_style(STREAM_INSTRUCTION, collection_prompt_settings(conn, collection_id))
