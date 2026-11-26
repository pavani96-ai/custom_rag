"""Tests for the storage adapters. Uses a temporary folder; no cloud calls."""

from pathlib import Path

import pytest

from app.config.settings import Settings
from app.exception_handling.exceptions import StorageError
from app.rag.document_storage import CloudStorage, LocalStorage, build_storage


def test_local_storage_writes_bytes_under_key(tmp_path: Path) -> None:
    """A saved original lands at root/key with the same bytes."""
    LocalStorage(tmp_path).save("collections/c1/originals/abc.pdf", b"%PDF-1.4")
    assert (tmp_path / "collections/c1/originals/abc.pdf").read_bytes() == b"%PDF-1.4"


@pytest.mark.parametrize("key", ["../escape.pdf", "/abs.pdf", "a/../../b.pdf", ""])
def test_local_storage_rejects_unsafe_keys(tmp_path: Path, key: str) -> None:
    """Keys that leave the root folder are refused before any write."""
    with pytest.raises(StorageError):
        LocalStorage(tmp_path).save(key, b"x")


def test_cloud_storage_is_not_implemented_yet() -> None:
    """The cloud adapter is a stub until the Cloud Storage milestone."""
    with pytest.raises(NotImplementedError):
        CloudStorage().save("k.pdf", b"x")


def test_build_storage_picks_local_in_local_mode(tmp_path: Path) -> None:
    """APP_MODE=local selects the folder adapter."""
    settings = Settings(app_mode="local", local_storage_path=str(tmp_path))
    assert isinstance(build_storage(settings), LocalStorage)


def test_build_storage_picks_cloud_outside_local_mode() -> None:
    """Any other APP_MODE selects the cloud adapter."""
    assert isinstance(build_storage(Settings(app_mode="cloud")), CloudStorage)
