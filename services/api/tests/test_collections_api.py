"""Tests for collection creation and upload routes. Database and storage are replaced by fakes."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import collections as routes
from app.main import app
from app.storage import LocalStorage, StorageError

PDF_BYTES = b"%PDF-1.4\n% test document\n"


class FailingStorage:
    """Storage that always fails, to test the per-file error path."""

    def save(self, key: str, data: bytes) -> None:
        """Simulate a failed write."""
        raise StorageError("disk full")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Test client with a fake database and a temporary storage folder."""
    monkeypatch.setattr(routes, "collection_exists", lambda conn, cid: True)
    app.dependency_overrides[routes.get_db] = lambda: None
    app.dependency_overrides[routes.get_storage] = lambda: LocalStorage(tmp_path)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_collection_returns_201(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A valid collection body is stored and returned with its id."""
    workspace_id = str(uuid4())
    monkeypatch.setattr(
        routes,
        "insert_collection",
        lambda conn, ws, body: {"id": uuid4(), "workspace_id": ws, "title": body.title},
    )
    response = client.post(
        f"/workspaces/{workspace_id}/collections", json={"title": "Contracts"}
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Contracts"


def test_create_collection_rejects_empty_title(client: TestClient) -> None:
    """An empty title fails Pydantic validation before any database call."""
    response = client.post(f"/workspaces/{uuid4()}/collections", json={"title": ""})
    assert response.status_code == 422


def test_valid_pdf_is_stored(client: TestClient, tmp_path: Path) -> None:
    """A PDF is written to the storage folder and reported as stored."""
    collection_id = uuid4()
    response = client.post(
        f"/collections/{collection_id}/uploads",
        files=[("files", ("report.pdf", PDF_BYTES, "application/pdf"))],
    )
    result = response.json()[0]
    assert result["status"] == "stored"
    assert result["upload_id"] is not None
    assert (tmp_path / f"collections/{collection_id}/originals/{result['upload_id']}.pdf").exists()


def test_non_pdf_is_rejected_without_storing(client: TestClient, tmp_path: Path) -> None:
    """A file with the wrong extension is reported failed and nothing is written."""
    response = client.post(
        f"/collections/{uuid4()}/uploads",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert response.json()[0]["status"] == "failed"
    assert not any(tmp_path.rglob("*.txt"))


def test_pdf_extension_with_wrong_content_is_rejected(client: TestClient) -> None:
    """The PDF header is checked, not just the file name."""
    response = client.post(
        f"/collections/{uuid4()}/uploads",
        files=[("files", ("fake.pdf", b"not a pdf", "application/pdf"))],
    )
    assert response.json()[0]["status"] == "failed"


def test_storage_failure_reports_per_file_error(client: TestClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A storage failure shows as a per-file error and no upload ID is issued."""
    app.dependency_overrides[routes.get_storage] = lambda: FailingStorage()
    response = client.post(
        f"/collections/{uuid4()}/uploads",
        files=[("files", ("report.pdf", PDF_BYTES, "application/pdf"))],
    )
    result = response.json()[0]
    assert result["status"] == "failed"
    assert result["error"] == "disk full"
    assert result["upload_id"] is None
