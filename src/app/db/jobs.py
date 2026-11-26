"""PostgreSQL access for ingest job status. The worker writes the status; this only reads it."""

from uuid import UUID

import psycopg


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
