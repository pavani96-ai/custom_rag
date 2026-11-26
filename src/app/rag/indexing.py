"""Index one document: parse, chunk, embed, write to OpenSearch, then mark it ready or failed."""

import psycopg
import structlog
from opensearchpy import OpenSearch

from app.rag.pipeline import build_chunks, extract_pages
from app.rag.providers.embedder import Embedder
from app.search.opensearch import bulk_index, count_chunks, ensure_index
from app.storage import ObjectStorage

logger = structlog.stdlib.get_logger(__name__)
EMBED_BATCH = 32


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


def index_document(
    *,
    conn: psycopg.Connection,
    storage: ObjectStorage,
    embedder: Embedder,
    search: OpenSearch,
    job_id: str,
    document_id: str,
    collection_id: str,
    workspace_id: str,
    filename: str,
    storage_key: str,
) -> int:
    """Run the full indexing steps for one document and return its chunk count."""
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
    if row == ("ready",):
        chunk_count = count_chunks(search, document_id)
        if chunk_count:
            set_status(conn, job_id, document_id, "succeeded")
            logger.info("index_reused", job_id=job_id, document_id=document_id, chunks=chunk_count)
            return chunk_count

    set_status(conn, job_id, document_id, "running")
    try:
        data = storage.load(storage_key)
        pages = extract_pages(data)
        chunks = build_chunks(document_id, pages)
        vectors = _embed_all(embedder, [chunk.text for chunk in chunks])
        ensure_index(search, embedder.dimension)
        documents = [
            {
                "chunk_id": chunk.chunk_id,
                "workspace_id": workspace_id,
                "collection_id": collection_id,
                "document_id": document_id,
                "filename": filename,
                "page": chunk.page,
                "text": chunk.text,
                "embedding": vector,
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        bulk_index(search, documents)
    except Exception:
        logger.exception("index_failed", job_id=job_id, document_id=document_id)
        record_failure(conn, job_id, document_id)
        raise
    record_success(conn, job_id, document_id, len(pages))
    logger.info("index_succeeded", job_id=job_id, pages=len(pages), chunks=len(chunks))
    return len(chunks)


def _embed_all(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    """Embed texts in fixed-size batches to bound memory use."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        vectors.extend(embedder.embed(texts[start : start + EMBED_BATCH]))
    return vectors
