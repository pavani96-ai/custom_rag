"""HTTP route handlers for collections, uploads, search, answers, and chat.

Handlers check the request, then call the pipelines in this package. Business steps live in
answer_pipeline.py and upload_pipeline.py, and data access lives in app/db/.
"""

from collections.abc import Iterator
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from app.api.answer_pipeline import (
    answer_from_generated,
    chat_events,
    generate_answer,
    rerank_sources,
    search_passages,
)
from app.api.upload_pipeline import process_upload, queue_one
from app.config.settings import Settings, get_settings
from app.db.collections import collection_exists, collection_workspace, insert_collection
from app.db.connection import get_db
from app.db.conversations import (
    conversation_messages,
    conversation_title,
    document_storage_key,
    list_conversations,
)
from app.db.jobs import job_status
from app.exception_handling.exceptions import StorageError
from app.rag.document_storage import ObjectStorage, get_storage
from app.rag.embedder import Embedder, get_embedder
from app.rag.prompts import INSUFFICIENT_EVIDENCE
from app.schema.models import (
    Answer,
    ChatIn,
    CollectionIn,
    CollectionOut,
    ConversationDetail,
    ConversationOut,
    IngestIn,
    IngestOut,
    JobOut,
    MessageOut,
    Passage,
    SearchIn,
    UploadResult,
)

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}/collections", status_code=201, response_model=CollectionOut
)
def create_collection(
    workspace_id: UUID, body: CollectionIn, conn: psycopg.Connection = Depends(get_db)
) -> dict:
    """Create a collection in the workspace."""
    return insert_collection(conn, workspace_id, body)


@router.post("/collections/{collection_id}/uploads", response_model=list[UploadResult])
async def upload_files(
    collection_id: UUID,
    files: list[UploadFile],
    conn: psycopg.Connection = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> list[UploadResult]:
    """Store each uploaded PDF and report the outcome per file. Nothing is indexed here."""
    if not collection_exists(conn, collection_id):
        return [
            UploadResult(filename=f.filename or "", status="failed", error="Unknown collection.")
            for f in files
        ]
    return [await process_upload(storage, collection_id, upload, settings) for upload in files]


@router.post(
    "/collections/{collection_id}/documents/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=list[IngestOut],
)
def ingest_documents(
    collection_id: UUID,
    body: IngestIn,
    conn: psycopg.Connection = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> list[IngestOut]:
    """Queue indexing for stored originals. Each file must already be in storage."""
    _check_batch_size(body, settings)
    if not collection_exists(conn, collection_id):
        raise HTTPException(status_code=404, detail="Unknown collection.")
    workspace_id = collection_workspace(conn, collection_id)
    return [queue_one(conn, storage, collection_id, workspace_id, item) for item in body.documents]


def _check_batch_size(body: IngestIn, settings: Settings) -> None:
    """Reject an ingest request that lists more originals than the configured batch limit."""
    if len(body.documents) > settings.max_batch_files:
        raise HTTPException(
            status_code=422,
            detail=f"At most {settings.max_batch_files} files per ingest request.",
        )


@router.post("/collections/{collection_id}/search", response_model=list[Passage])
def search_collection(
    collection_id: UUID,
    body: SearchIn,
    conn: psycopg.Connection = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    settings: Settings = Depends(get_settings),
) -> list[Passage]:
    """Rank passages from ready documents in the collection using semantic and keyword search."""
    if not collection_exists(conn, collection_id):
        raise HTTPException(status_code=404, detail="Unknown collection.")
    return search_passages(conn, collection_id, body, embedder, settings)


@router.post(
    "/collections/{collection_id}/ask", response_model=Answer, response_model_exclude_none=True
)
def ask_collection(
    collection_id: UUID,
    body: SearchIn,
    conn: psycopg.Connection = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    include_contexts: bool = False,
    settings: Settings = Depends(get_settings),
) -> Answer:
    """Answer one question and identify the retrieved passages that support it."""
    candidates = body.model_copy(update={"top_k": 20})
    passages = search_collection(collection_id, candidates, conn, embedder, settings)
    if not passages:
        return Answer(
            answer=INSUFFICIENT_EVIDENCE,
            sources=[],
            retrieved_contexts=[] if include_contexts else None,
        )
    sources = rerank_sources(passages, body.query, min(body.top_k, 5), settings)
    generated = generate_answer(conn, collection_id, body.query, sources, settings)
    return answer_from_generated(generated, sources, include_contexts)


@router.post("/collections/{collection_id}/chat/stream")
def chat_stream(
    collection_id: UUID,
    body: ChatIn,
    conn: psycopg.Connection = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Answer a question in a conversation, streaming text deltas as server-sent events."""
    if not collection_exists(conn, collection_id):
        raise HTTPException(status_code=404, detail="Unknown collection.")
    workspace_id = collection_workspace(conn, collection_id)
    events: Iterator[str] = chat_events(
        conn, embedder, collection_id, workspace_id, body, settings
    )
    return StreamingResponse(
        events, media_type="text/event-stream", headers={"cache-control": "no-cache"}
    )


@router.get("/collections/{collection_id}/conversations", response_model=list[ConversationOut])
def list_collection_conversations(
    collection_id: UUID,
    conn: psycopg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    """List the dev user's conversations in the collection, newest first."""
    if not collection_exists(conn, collection_id):
        raise HTTPException(status_code=404, detail="Unknown collection.")
    return list_conversations(conn, collection_id, settings.dev_user_id)


@router.get(
    "/collections/{collection_id}/conversations/{conversation_id}",
    response_model=ConversationDetail,
)
def get_collection_conversation(
    collection_id: UUID,
    conversation_id: UUID,
    conn: psycopg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return one conversation with its messages and their citations."""
    title = conversation_title(conn, conversation_id, collection_id, settings.dev_user_id)
    if title is None:
        raise HTTPException(status_code=404, detail="Unknown conversation.")
    messages = [
        MessageOut.model_validate(message)
        for message in conversation_messages(conn, conversation_id)
    ]
    return {"id": conversation_id, "title": title, "messages": messages}


@router.get("/collections/{collection_id}/documents/{document_id}/original")
def document_original(
    collection_id: UUID,
    document_id: UUID,
    conn: psycopg.Connection = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
) -> Response:
    """Return the stored original PDF so the source viewer can open a cited page."""
    key = document_storage_key(conn, collection_id, document_id)
    if key is None:
        raise HTTPException(status_code=404, detail="Unknown document.")
    try:
        data = storage.load(key)
    except StorageError as exc:
        raise HTTPException(status_code=404, detail="Original file is not available.") from exc
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"content-disposition": "inline", "x-content-type-options": "nosniff"},
    )


@router.get("/collections/{collection_id}/jobs/{job_id}", response_model=JobOut)
def get_job(collection_id: UUID, job_id: UUID, conn: psycopg.Connection = Depends(get_db)) -> dict:
    """Return the status of one ingest job in the collection, for the upload page to poll."""
    status_row = job_status(conn, collection_id, job_id)
    if status_row is None:
        raise HTTPException(status_code=404, detail="Unknown job.")
    return status_row
