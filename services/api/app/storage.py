"""Object storage for original files. Local folder in local mode, Cloud Storage otherwise."""

from pathlib import Path
from typing import Protocol

from app.settings import Settings


class StorageError(Exception):
    """Raised when an original cannot be written to storage."""


class ObjectStorage(Protocol):
    """Write-once storage keyed by relative paths such as collections/<id>/originals/<sha>.pdf."""

    def save(self, key: str, data: bytes) -> None:
        """Write the bytes under the key, or raise StorageError."""
        ...


def validate_key(key: str) -> None:
    """Reject absolute paths and parent-directory segments in storage keys."""
    parts = Path(key).parts
    if not key or key.startswith("/") or ".." in parts:
        raise StorageError(f"invalid storage key: {key!r}")


class LocalStorage:
    """Stores originals in a folder on the local disk. Used when APP_MODE is local."""

    def __init__(self, root: Path) -> None:
        """Remember the root folder; it is created on first write."""
        self.root = root

    def save(self, key: str, data: bytes) -> None:
        """Write the bytes to root/key, creating folders as needed."""
        validate_key(key)
        target = self.root / key
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as error:
            raise StorageError(f"could not write {key}") from error


class CloudStorage:
    """Placeholder for the Google Cloud Storage adapter. Not implemented yet."""

    def save(self, key: str, data: bytes) -> None:
        """Cloud writes are not built yet."""
        raise NotImplementedError("Cloud Storage adapter is not implemented yet")


def build_storage(settings: Settings) -> ObjectStorage:
    """Pick local folder storage for local mode, Cloud Storage for every other mode."""
    if settings.app_mode == "local":
        return LocalStorage(Path(settings.local_storage_path))
    return CloudStorage()
