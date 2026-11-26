"""Celery application shared by the worker and Flower."""

from typing import Any

import structlog
from celery import Celery
from celery.signals import setup_logging, task_prerun

from app.config.settings import get_settings
from app.observability import configure_logging


def create_celery() -> Celery:
    """Build the Celery app using Redis as broker and result backend."""
    settings = get_settings()
    app = Celery(
        "rag",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.rag.tasks"],
    )
    app.conf.worker_hijack_root_logger = False
    app.conf.task_track_started = True
    return app


celery_app = create_celery()


@setup_logging.connect
def use_json_logging(**_kwargs: Any) -> None:
    """Replace Celery's default log setup with JSON logging."""
    configure_logging(get_settings().log_level)


@task_prerun.connect
def bind_job_context(task_id: str | None = None, task: Any = None, **_kwargs: Any) -> None:
    """Attach the job ID and task name to every log line from this task."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        job_id=task_id, task_name=getattr(task, "name", None)
    )
