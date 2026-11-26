"""FastAPI application entry point."""

import re
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.routes import router
from app.config.settings import get_settings
from app.observability import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.stdlib.get_logger(__name__)


def parse_origins(raw: str) -> list[str]:
    """Split a comma-separated origin list, dropping blanks and surrounding spaces."""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Document workspace API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_origins(settings.web_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["content-type", "x-request-id"],
    expose_headers=["x-request-id"],
)
app.include_router(router)


def resolve_request_id(header_value: str | None) -> str:
    """Reuse a client request ID made of letters, digits, '-' or '_', else generate one."""
    if header_value and _is_safe_request_id(header_value):
        return header_value
    return uuid.uuid4().hex


def _is_safe_request_id(value: str) -> bool:
    """Return True when the ID is short enough and contains only safe characters."""
    return len(value) <= settings.request_id_max_length and re.fullmatch(
        settings.request_id_pattern, value
    ) is not None


@app.middleware("http")
async def add_request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Bind a request ID to every log line and log one line per request."""
    request_id = resolve_request_id(request.headers.get("x-request-id"))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started = time.perf_counter()
    response: Response = await call_next(request)
    response.headers["x-request-id"] = request_id
    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}
