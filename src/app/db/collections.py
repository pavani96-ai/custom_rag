"""Collection and document lookups scoped to one collection."""

from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.schema.models import CollectionIn


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
                Jsonb(body.response_preferences.model_dump()),
            ),
        )
        row = cur.fetchone()
    return {"id": row[0], "workspace_id": row[1], "title": row[2]}


def collection_exists(conn: psycopg.Connection, collection_id: UUID) -> bool:
    """Return True when a collection with this id exists."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM collections WHERE id = %s", (collection_id,))
        return cur.fetchone() is not None


def collection_workspace(conn: psycopg.Connection, collection_id: UUID) -> str:
    """Return the workspace that owns the collection."""
    with conn.cursor() as cur:
        cur.execute("SELECT workspace_id FROM collections WHERE id = %s", (collection_id,))
        row = cur.fetchone()
    return str(row[0])


def ready_document_ids(conn: psycopg.Connection, collection_id: UUID) -> list[str]:
    """Return the IDs of the collection's documents that are ready to search."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM documents WHERE collection_id = %s AND status = 'ready'",
            (collection_id,),
        )
        return [str(row[0]) for row in cur.fetchall()]
