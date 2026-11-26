"""Tests for the indexing job. Database status writes are replaced by recorders."""

import io
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from opensearchpy import NotFoundError
from pypdf import PdfWriter

from app.rag import indexing
from app.search.opensearch import INDEX_NAME
from app.storage import LocalStorage

WORKSPACE = "00000000-0000-4000-8000-000000000002"


class FakeEmbedder:
    """Returns a fixed vector per text and records the batch sizes it was given."""

    dimension = 4

    def __init__(self) -> None:
        self.batches: list[int] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return a vector per text without loading a model."""
        self.batches.append(len(texts))
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


def text_pdf() -> bytes:
    """Return a one-page PDF with no text layer, which yields zero chunks."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Replace the database status writes with recorders."""
    calls: dict[str, list] = {"status": [], "success": [], "failure": []}
    monkeypatch.setattr(indexing, "set_status", lambda conn, j, d, s: calls["status"].append(s))
    monkeypatch.setattr(
        indexing, "record_success", lambda conn, j, d, pages: calls["success"].append(pages)
    )
    monkeypatch.setattr(indexing, "record_failure", lambda conn, j, d: calls["failure"].append(d))
    return calls


def run(storage, embedder, search, status="queued"):  # type: ignore[no-untyped-def]
    """Run one indexing job with fixed IDs."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (status,)
    job = indexing.IndexJob(
        job_id="job-1",
        document_id="doc-1",
        collection_id="col-1",
        workspace_id=WORKSPACE,
        filename="report.pdf",
        storage_key="collections/col-1/originals/abc.pdf",
    )
    return indexing.index_document(
        conn=conn, storage=storage, embedder=embedder, search=search, job=job
    )


@pytest.mark.parametrize("status", ["queued", "failed", "ready"])
def test_blank_document_completes_with_zero_chunks(
    tmp_path: Path, recorded: dict[str, list], status: str
) -> None:
    """A scanned page with no text layer is marked succeeded and writes nothing."""
    storage = LocalStorage(tmp_path)
    storage.save("collections/col-1/originals/abc.pdf", text_pdf())
    embedder = FakeEmbedder()
    search = Mock()
    search.count.side_effect = NotFoundError(404, "index_not_found_exception")
    assert run(storage, embedder, search, status=status) == 0
    assert recorded["success"] == [1]
    assert recorded["status"] == ["running"]
    assert recorded["failure"] == []


def test_missing_original_marks_failure(tmp_path, recorded) -> None:  # type: ignore[no-untyped-def]
    """A missing original is recorded as a failed job, and the error is re-raised."""
    with pytest.raises(Exception):
        run(LocalStorage(tmp_path), FakeEmbedder(), Mock())
    assert recorded["failure"] == ["doc-1"]
    assert recorded["success"] == []


def test_ready_document_reuses_existing_chunks(tmp_path: Path, recorded: dict[str, list]) -> None:
    embedder = FakeEmbedder()

    search = Mock()
    search.count.return_value = {"count": 3, "_shards": {"failed": 0}}
    assert run(LocalStorage(tmp_path), embedder, search, status="ready") == 3
    search.count.assert_called_once_with(
        index=INDEX_NAME, body={"query": {"term": {"document_id": "doc-1"}}}
    )

    assert recorded["status"] == ["succeeded"]
    assert recorded["failure"] == []
    assert embedder.batches == []
