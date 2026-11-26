"""PostgreSQL access for ingest job status. The worker writes the status; this only reads it."""

from uuid import UUID, uuid4

import psycopg

from app.schema.models import IngestItem


def job_status(conn: psycopg.Connection, collection_id: UUID, job_id: UUID) -> dict | None:
    """Return the job's status and document, or None when the job is not in this collection."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, document_id, status, error_message FROM jobs
            WHERE id = %s AND collection_id = %s
            """,
            (job_id, collection_id),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {"job_id": row[0], "document_id": row[1], "status": row[2], "error_message": row[3]}


def insert_queued(
    conn: psycopg.Connection,
    *,
    workspace_id: str,
    collection_id: UUID,
    item: IngestItem,
    storage_key: str,
) -> tuple[str, str]:
    """Insert the document, job, and outbox entry in one transaction. Return their IDs."""
    document_id = str(uuid4())
    job_id = str(uuid4())
    with conn.transaction(), conn.cursor() as cur:
        _insert_document(cur, workspace_id, collection_id, document_id, item, storage_key)
        _insert_job_and_outbox(cur, workspace_id, collection_id, document_id, job_id)
    return document_id, job_id


def _insert_document(
    cur: psycopg.Cursor,
    workspace_id: str,
    collection_id: UUID,
    document_id: str,
    item: IngestItem,
    storage_key: str,
) -> None:
    """Insert the document row for a stored original."""
    cur.execute(
        """
        INSERT INTO documents
            (id, workspace_id, collection_id, filename, content_hash,
             storage_key, storage_generation, uploaded_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'local', now())
        """,
        (document_id, workspace_id, collection_id, item.filename, item.upload_id, storage_key),
    )


def _insert_job_and_outbox(
    cur: psycopg.Cursor, workspace_id: str, collection_id: UUID, document_id: str, job_id: str
) -> None:
    """Insert the indexing job and its outbox message for the document."""
    cur.execute(
        """
        INSERT INTO jobs (id, workspace_id, collection_id, document_id, kind)
        VALUES (%s, %s, %s, %s, 'index')
        """,
        (job_id, workspace_id, collection_id, document_id),
    )
    cur.execute(
        "INSERT INTO outbox (job_id, topic, payload) VALUES (%s, 'ingestion.index_document', "
        "jsonb_build_object('job_id', %s::text, 'document_id', %s::text))",
        (job_id, job_id, document_id),
    )


def mark_published(conn: psycopg.Connection, job_id: str) -> None:
    """Record that the queue accepted the job."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE outbox SET published_at = now() WHERE job_id = %s AND published_at IS NULL",
            (job_id,),
        )


def set_status(conn: psycopg.Connection, job_id: str, document_id: str, status: str) -> None:
    """Move the job and its document to a new status in one transaction."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = %s, updated_at = now() WHERE id = %s",
            (status, job_id),
        )
        cur.execute(
            "UPDATE documents SET status = %s, updated_at = now() WHERE id = %s",
            (_document_status(status), document_id),
        )


def _document_status(job_status: str) -> str:
    """Map a job status to the document status the UI shows."""
    return {"running": "processing", "succeeded": "ready", "failed": "failed"}[job_status]


def record_failure(conn: psycopg.Connection, job_id: str, document_id: str) -> None:
    """Mark the job and document failed with a safe message. Raw errors stay in worker logs."""
    message = "Indexing failed. An operator can find details in the worker logs."
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'failed', error_message = %s, updated_at = now() "
            "WHERE id = %s",
            (message, job_id),
        )
        cur.execute(
            "UPDATE documents SET status = 'failed', error_message = %s, updated_at = now() "
            "WHERE id = %s",
            (message, document_id),
        )


def record_success(conn: psycopg.Connection, job_id: str, document_id: str, pages: int) -> None:
    """Store the page count and mark the job and document as finished."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET page_count = %s WHERE id = %s", (pages, document_id)
        )
    set_status(conn, job_id, document_id, "succeeded")
