"""Collection and upload routes. Originals are stored before any indexing job is queued."""

import hashlib
from collections.abc import Iterator
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, UploadFile
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.settings import get_settings
from app.storage import ObjectStorage, StorageError, build_storage

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
PDF_MAGIC = b"%PDF"


class CollectionIn(BaseModel):
    """Setup fields for a new collection."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=8000)
    response_preferences: dict[str, str] = Field(default_factory=dict)


class CollectionOut(BaseModel):
    """Stored collection returned to the caller."""

    id: UUID
    workspace_id: UUID
    title: str


class UploadResult(BaseModel):
    """Per-file outcome. Only stored files may be ingested."""

    filename: str
    status: Literal["stored", "failed"]
    upload_id: str | None = None
    error: str | None = None


def get_db() -> Iterator[psycopg.Connection]:
    """Open a database connection for one request."""
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        yield conn


def get_storage() -> ObjectStorage:
    """Return the storage adapter selected by APP_MODE."""
    return build_storage(get_settings())


def insert_collection(conn: psycopg.Connection, workspace_id: UUID, body: CollectionIn) -> dict:
    """Insert a collection row and return its id, workspace, and title."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO collections
                (id, workspace_id, title, description, instructions, response_preferences)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s)
            RETURNING id, workspace_id, title
            """,
            (
                workspace_id,
                body.title,
                body.description,
                body.instructions,
                Jsonb(body.response_preferences),
            ),
        )
        row = cur.fetchone()
    return {"id": row[0], "workspace_id": row[1], "title": row[2]}


def collection_exists(conn: psycopg.Connection, collection_id: UUID) -> bool:
    """Return True when a collection with this id exists."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM collections WHERE id = %s", (collection_id,))
        return cur.fetchone() is not None


def validate_upload(filename: str, data: bytes) -> str | None:
    """Return an error message for a file that must not be stored, or None if it is valid."""
    if not filename.lower().endswith(".pdf"):
        return "Only PDF files are accepted in this milestone."
    if len(data) > MAX_UPLOAD_BYTES:
        return "File is larger than the 50 MB limit."
    if not data.startswith(PDF_MAGIC):
        return "File content is not a PDF."
    return None


def store_one(
    storage: ObjectStorage, collection_id: UUID, filename: str, data: bytes
) -> UploadResult:
    """Store one validated original under a key derived from its SHA-256 hash."""
    digest = hashlib.sha256(data).hexdigest()
    key = f"collections/{collection_id}/originals/{digest}.pdf"
    try:
        storage.save(key, data)
    except (StorageError, NotImplementedError) as error:
        return UploadResult(filename=filename, status="failed", error=str(error))
    return UploadResult(filename=filename, status="stored", upload_id=digest)


@router.post(
    "/workspaces/{workspace_id}/collections", status_code=201, response_model=CollectionOut
)
def create_collection(
    workspace_id: UUID, body: CollectionIn, conn: psycopg.Connection = Depends(get_db)
) -> dict:
    """Create a collection in the workspace."""
    return insert_collection(conn, workspace_id, body)


@router.post("/collections/{collection_id}/uploads", response_model=list[UploadResult])
async def upload_files(
    collection_id: UUID,
    files: list[UploadFile],
    conn: psycopg.Connection = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
) -> list[UploadResult]:
    """Store each uploaded PDF and report the outcome per file. Nothing is indexed here."""
    if not collection_exists(conn, collection_id):
        return [
            UploadResult(filename=f.filename or "", status="failed", error="Unknown collection.")
            for f in files
        ]
    results: list[UploadResult] = []
    for upload in files:
        filename = upload.filename or ""
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
        problem = validate_upload(filename, data)
        if problem:
            results.append(UploadResult(filename=filename, status="failed", error=problem))
            continue
        results.append(store_one(storage, collection_id, filename, data))
    return results
