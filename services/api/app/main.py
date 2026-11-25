"""FastAPI application entry point."""

import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import Response

from app.collections import router as collections_router
from app.observability import configure_logging
from app.settings import get_settings

MAX_REQUEST_ID_LENGTH = 64

configure_logging(get_settings().log_level)
logger = structlog.stdlib.get_logger(__name__)

app = FastAPI(title="Document workspace API")
app.include_router(collections_router)


def resolve_request_id(header_value: str | None) -> str:
    """Reuse a sane client request ID, otherwise generate one."""
    if header_value and len(header_value) <= MAX_REQUEST_ID_LENGTH:
        return header_value
    return uuid.uuid4().hex


@app.middleware("http")
async def add_request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
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
