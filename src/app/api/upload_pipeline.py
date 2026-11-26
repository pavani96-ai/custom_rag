"""Upload pipeline: validate and store uploaded PDFs, then queue each stored original for indexing.

Routes call these functions after they check the collection. A missing original raises
HTTPException 409 here; a later step can turn that into a domain error that routes map.
"""

from uuid import UUID

import psycopg
from fastapi import HTTPException, UploadFile

from app.config.settings import Settings
from app.exception_handling.exceptions import OriginalNotStoredError
from app.rag.document_storage import (
    ObjectStorage,
    store_original,
    validate_upload,
)
from app.schema.models import IngestItem, IngestOut, UploadResult
from app.workers.ingest import queue_document


async def process_upload(
    storage: ObjectStorage, collection_id: UUID, upload: UploadFile, settings: Settings
) -> UploadResult:
    """Read one upload, reject it if invalid, otherwise store it."""
    filename = upload.filename or ""
    data = await upload.read(settings.max_upload_bytes + 1)
    problem = validate_upload(filename, data, settings)
    if problem:
        return UploadResult(filename=filename, status="failed", error=problem)
    return store_original(storage, collection_id, filename, data)


def accepted_response(document_id: str, job_id: str, filename: str) -> IngestOut:
    """Build the response that tells the browser which job tracks the document."""
    return IngestOut(
        document_id=UUID(document_id),
        job_id=UUID(job_id),
        filename=filename,
        status="queued",
    )


def queue_one(
    conn: psycopg.Connection,
    storage: ObjectStorage,
    collection_id: UUID,
    workspace_id: str,
    item: IngestItem,
) -> IngestOut:
    """Queue indexing for one stored original and return its job IDs. 409 if not stored."""
    try:
        document_id, job_id = queue_document(conn, storage, collection_id, workspace_id, item)
    except OriginalNotStoredError as exc:
        detail = f"Original not stored: {item.filename}"
        raise HTTPException(status_code=409, detail=detail) from exc
    return accepted_response(document_id, job_id, item.filename)
