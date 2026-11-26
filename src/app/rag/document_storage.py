"""Original-file storage for uploads: local folder in local mode, Cloud Storage otherwise."""

import hashlib
from pathlib import Path
from typing import Protocol
from uuid import UUID

from fastapi import Depends

from app.config.settings import Settings, get_settings
from app.exception_handling.exceptions import OriginalNotStoredError, StorageError
from app.schema.models import UploadResult


def validate_upload(filename: str, data: bytes, settings: Settings) -> str | None:
    """Return an error message for a file that must not be stored, or None if it is valid."""
    if not filename.lower().endswith(".pdf"):
        return "Only PDF files are accepted in this milestone."
    if len(data) > settings.max_upload_bytes:
        return f"File is larger than the {settings.max_upload_bytes // (1024 * 1024)} MB limit."
    if not data.startswith(settings.pdf_magic):
        return "File content is not a PDF."
    return None


def original_key(collection_id: UUID, upload_id: str) -> str:
    """Return the storage key of a PDF original, derived from its SHA-256 upload ID."""
    return f"collections/{collection_id}/originals/{upload_id}.pdf"


def require_original(storage: "ObjectStorage", collection_id: UUID, upload_id: str) -> str:
    """Return the key of a stored original, or raise OriginalNotStoredError."""
    key = original_key(collection_id, upload_id)
    if not storage.exists(key):
        raise OriginalNotStoredError(upload_id)
    return key


class ObjectStorage(Protocol):
    """Write-once storage keyed by relative paths such as collections/<id>/originals/<sha>.pdf."""

    def save(self, key: str, data: bytes) -> None:
        """Write the bytes under the key, or raise StorageError."""
        ...

    def load(self, key: str) -> bytes:
        """Read the bytes stored under the key, or raise StorageError."""
        ...

    def exists(self, key: str) -> bool:
        """Return True when an object is stored under the key."""
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

    def _path(self, key: str) -> Path:
        """Validate the key, then return its location under the root folder."""
        validate_key(key)
        return self.root / key

    def save(self, key: str, data: bytes) -> None:
        """Write the bytes to root/key, creating folders as needed."""
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as error:
            raise StorageError(f"could not write {key}") from error

    def load(self, key: str) -> bytes:
        """Read the bytes stored under root/key."""
        try:
            return self._path(key).read_bytes()
        except OSError as error:
            raise StorageError(f"could not read {key}") from error

    def exists(self, key: str) -> bool:
        """Return True when root/key is a file."""
        return self._path(key).is_file()


class CloudStorage:
    """Placeholder for the Google Cloud Storage adapter. Not implemented yet."""

    def save(self, key: str, data: bytes) -> None:
        """Cloud writes are not built yet."""
        raise NotImplementedError("Cloud Storage adapter is not implemented yet")

    def load(self, key: str) -> bytes:
        """Cloud reads are not built yet."""
        raise NotImplementedError("Cloud Storage adapter is not implemented yet")

    def exists(self, key: str) -> bool:
        """Cloud lookups are not built yet."""
        raise NotImplementedError("Cloud Storage adapter is not implemented yet")


def build_storage(settings: Settings) -> ObjectStorage:
    """Pick local folder storage for local mode, Cloud Storage in the cloud."""
    if settings.is_cloud:
        return CloudStorage()
    return LocalStorage(Path(settings.local_storage_path))


def get_storage(settings: Settings = Depends(get_settings)) -> ObjectStorage:
    """Return the storage adapter for the current settings. Used as a FastAPI dependency."""
    return build_storage(settings)


def store_original(
    storage: ObjectStorage, collection_id: UUID, filename: str, data: bytes
) -> UploadResult:
    """Store one validated original under a key derived from its SHA-256 hash."""
    digest = hashlib.sha256(data).hexdigest()
    key = original_key(collection_id, digest)
    try:
        storage.save(key, data)
    except (StorageError, NotImplementedError) as error:
        return UploadResult(filename=filename, status="failed", error=str(error))
    return UploadResult(filename=filename, status="stored", upload_id=digest)
