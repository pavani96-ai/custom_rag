"""Structured JSON logging shared by the API and the worker."""

import logging
import sys

import structlog


def configure_logging(level: str) -> None:
    """Send every log line to stdout as one JSON object."""
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=level.upper(), force=True
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
