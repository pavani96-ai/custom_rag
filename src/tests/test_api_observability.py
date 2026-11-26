"""Tests for the health endpoint, request IDs, and JSON log lines. No real services are called."""

import json

from fastapi.testclient import TestClient

from app.api.main import app
from app.observability import configure_logging

client = TestClient(app)


def find_json_log(captured: str, event: str) -> dict:
    """Return the JSON log record with the given event name from stdout."""
    for line in captured.splitlines():
        if line.startswith("{"):
            record = json.loads(line)
            if record.get("event") == event:
                return record
    raise AssertionError(f"no JSON log record for event {event!r}")


def test_health_returns_ok_and_echoes_request_id() -> None:
    """A valid client request ID is returned unchanged."""
    response = client.get("/health", headers={"x-request-id": "req-123"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"] == "req-123"


def test_generates_request_id_when_header_is_missing() -> None:
    """A missing request ID gets a generated 32-character value."""
    response = client.get("/health")
    assert len(response.headers["x-request-id"]) == 32


def test_replaces_overlong_request_id() -> None:
    """A request ID longer than 64 characters is not trusted."""
    response = client.get("/health", headers={"x-request-id": "x" * 65})
    assert len(response.headers["x-request-id"]) == 32


def test_request_log_is_json_with_request_id(capsys) -> None:  # type: ignore[no-untyped-def]
    """Each request writes one JSON line that carries the request ID."""
    configure_logging("INFO")
    client.get("/health", headers={"x-request-id": "abc"})
    record = find_json_log(capsys.readouterr().out, "request_completed")
    assert record["event"] == "request_completed"
    assert record["request_id"] == "abc"
    assert record["status_code"] == 200
    assert record["level"] == "info"
