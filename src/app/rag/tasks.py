"""Ingestion Celery tasks: heartbeat and the per-document indexing job."""

from contextlib import closing

import psycopg
import structlog
from opensearchpy import OpenSearch

from app.config.settings import get_settings
from app.rag.indexing import index_document
from app.rag.providers.embedder import JinaEmbedder
from app.storage import build_storage
from app.workers.celery_app import celery_app

logger = structlog.stdlib.get_logger(__name__)


@celery_app.task(name="ingestion.heartbeat")
def heartbeat(message: str = "ok") -> dict[str, str]:
    """Log a heartbeat so the JSON logs and Flower show the worker is running."""
    logger.info("ingestion_heartbeat", message=message)
    return {"status": "ok", "message": message}


@celery_app.task(name="ingestion.index_document")
def index_document_task(
    job_id: str,
    document_id: str,
    collection_id: str,
    workspace_id: str,
    filename: str,
    storage_key: str,
) -> int:
    """Index one stored document. Connections are opened per task and closed on exit."""
    settings = get_settings()
    embedder = JinaEmbedder(settings.jina_api_key, "retrieval.passage")
    with (
        psycopg.connect(settings.database_url, autocommit=True) as conn,
        closing(OpenSearch(hosts=[settings.opensearch_url], timeout=60)) as search,
    ):
        # Serialize workers for this document until the task connection closes.
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (document_id,))
        return index_document(
            conn=conn,
            storage=build_storage(settings),
            embedder=embedder,
            search=search,
            job_id=job_id,
            document_id=document_id,
            collection_id=collection_id,
            workspace_id=workspace_id,
            filename=filename,
            storage_key=storage_key,
        )
