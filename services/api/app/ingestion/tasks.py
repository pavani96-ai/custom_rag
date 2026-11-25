"""Ingestion Celery tasks. Milestone 1 starts with a heartbeat that proves the worker runs."""

import structlog

from app.celery_app import celery_app

logger = structlog.stdlib.get_logger(__name__)


@celery_app.task(name="ingestion.heartbeat")
def heartbeat(message: str = "ok") -> dict[str, str]:
    """Log a heartbeat so the JSON logs and Flower show the worker is running."""
    logger.info("ingestion_heartbeat", message=message)
    return {"status": "ok", "message": message}
