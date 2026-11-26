"""Tests for browser CORS rules. The web UI runs on another origin than the API."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app, parse_origins


def test_parse_origins_drops_blanks_and_spaces() -> None:
    """Origins are split on commas and trimmed."""
    assert parse_origins(" http://a:3000 , ,http://b:3000 ") == ["http://a:3000", "http://b:3000"]


def test_preflight_allows_configured_web_origin() -> None:
    """A preflight from the web origin gets the CORS allow header back."""
    client = TestClient(app)
    response = client.options(
        "/collections/00000000-0000-4000-8000-000000000003/uploads",
        headers={
            "origin": "http://127.0.0.1:3000",
            "access-control-request-method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


@pytest.mark.parametrize("origin", ["https://evil.example", "http://attacker.local:3000"])
def test_preflight_rejects_unknown_origin(origin: str) -> None:
    """Origins outside the configured list get no allow header."""
    client = TestClient(app)
    response = client.options(
        "/health",
        headers={"origin": origin, "access-control-request-method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers
