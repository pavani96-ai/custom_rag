"""Queue side of ingestion: record a stored original as a job and hand it to the Celery worker."""

from uuid import UUID

import psycopg

from app.db.jobs import insert_queued, mark_published
from app.rag.tasks import index_document_task
from app.schema.models import IngestItem
from app.storage import ObjectStorage, require_original


def queue_document(
    conn: psycopg.Connection,
    storage: ObjectStorage,
    collection_id: UUID,
    workspace_id: str,
    item: IngestItem,
) -> tuple[str, str]:
    """Record a stored original as a document and index job, then send the job to Celery."""
    storage_key = require_original(storage, collection_id, item.upload_id)
    document_id, job_id = _record_job(conn, workspace_id, collection_id, item, storage_key)
    _send_job(job_id, document_id, collection_id, workspace_id, item.filename, storage_key)
    mark_published(conn, job_id)
    return document_id, job_id


def _record_job(
    conn: psycopg.Connection,
    workspace_id: str,
    collection_id: UUID,
    item: IngestItem,
    storage_key: str,
) -> tuple[str, str]:
    """Insert the document, job, and outbox rows and return their IDs."""
    return insert_queued(
        conn,
        workspace_id=workspace_id,
        collection_id=collection_id,
        item=item,
        storage_key=storage_key,
    )


def _send_job(
    job_id: str,
    document_id: str,
    collection_id: UUID,
    workspace_id: str,
    filename: str,
    storage_key: str,
) -> None:
    """Send one indexing job to the Celery worker."""
    index_document_task.delay(
        job_id, document_id, str(collection_id), workspace_id, filename, storage_key
    )
