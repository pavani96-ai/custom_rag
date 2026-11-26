"""Structured JSON logging for the API and the Celery worker."""

from app.observability.logs import configure_logging

__all__ = ["configure_logging"]
