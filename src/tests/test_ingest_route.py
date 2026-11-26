"""Tests for the ingest route. Database and queue are replaced by fakes."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import routes as routes
from app.api.main import app
from app.api.routes import get_db, get_storage
from app.config.settings import get_settings
from app.rag.document_storage import LocalStorage
from app.workers import ingest

SHA = "a" * 64


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Replace the queue and DB writes. Records each queued job."""
    calls: list[tuple] = []
    monkeypatch.setattr(routes, "collection_exists", lambda conn, cid: True)
    monkeypatch.setattr(routes, "collection_workspace", lambda conn, cid: str(uuid4()))
    monkeypatch.setattr(
        ingest,
        "insert_queued",
        lambda conn, **kwargs: (str(uuid4()), str(uuid4())),
    )
    monkeypatch.setattr(ingest, "mark_published", lambda conn, job_id: None)

    class FakeTask:
        def delay(self, *args):  # type: ignore[no-untyped-def]
            calls.append(args)

    monkeypatch.setattr(ingest, "index_document_task", FakeTask())
    return calls


@pytest.fixture
def client(tmp_path: Path, queued) -> TestClient:  # type: ignore[no-untyped-def]
    """Client wired to a temporary storage folder and no real database."""
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_storage] = lambda: LocalStorage(tmp_path)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ingest_queues_stored_original(client: TestClient, tmp_path: Path, queued) -> None:  # type: ignore[no-untyped-def]
    """A stored original is queued and the response returns 202 with job IDs."""
    collection_id = uuid4()
    key = f"collections/{collection_id}/originals/{SHA}.pdf"
    (tmp_path / key).parent.mkdir(parents=True)
    (tmp_path / key).write_bytes(b"%PDF-1.4")
    response = client.post(
        f"/collections/{collection_id}/documents/ingest",
        json={"documents": [{"upload_id": SHA, "filename": "report.pdf"}]},
    )
    assert response.status_code == 202
    assert response.json()[0]["status"] == "queued"
    assert len(queued) == 1


def test_ingest_rejects_original_not_in_storage(client: TestClient, queued) -> None:  # type: ignore[no-untyped-def]
    """An upload ID with no stored file gets a 409 and nothing is queued."""
    response = client.post(
        f"/collections/{uuid4()}/documents/ingest",
        json={"documents": [{"upload_id": SHA, "filename": "report.pdf"}]},
    )
    assert response.status_code == 409
    assert queued == []


def test_ingest_rejects_bad_upload_id(client: TestClient) -> None:
    """A malformed upload ID fails validation before any lookup."""
    response = client.post(
        f"/collections/{uuid4()}/documents/ingest",
        json={"documents": [{"upload_id": "../etc", "filename": "x.pdf"}]},
    )
    assert response.status_code == 422


def test_ingest_rejects_batch_over_configured_limit(
    client: TestClient, queued, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """A batch larger than MAX_BATCH_FILES gets a 422 and nothing is queued."""
    monkeypatch.setenv("MAX_BATCH_FILES", "1")
    get_settings.cache_clear()
    try:
        documents = [{"upload_id": SHA, "filename": "a.pdf"}] * 2
        response = client.post(
            f"/collections/{uuid4()}/documents/ingest", json={"documents": documents}
        )
    finally:
        get_settings.cache_clear()
    assert response.status_code == 422
    assert queued == []
