"""Tests for the Celery worker wiring. The broker is never contacted."""

from app.rag.tasks import heartbeat
from app.workers.celery_app import celery_app


def test_heartbeat_task_is_registered() -> None:
    """The ingestion heartbeat task is registered under its stable name."""
    assert "ingestion.heartbeat" in celery_app.tasks


def test_heartbeat_returns_status_and_message() -> None:
    """Calling the task directly returns its status payload."""
    assert heartbeat("hello") == {"status": "ok", "message": "hello"}


def test_worker_keeps_json_logging() -> None:
    """Celery must not replace the JSON log setup with its default handler."""
    assert celery_app.conf.worker_hijack_root_logger is False
