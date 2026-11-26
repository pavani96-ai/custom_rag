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
