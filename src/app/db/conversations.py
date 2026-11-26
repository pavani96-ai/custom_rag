"""PostgreSQL access for chat conversations, messages, and the original-file lookup.

All queries are parameterized. Each function takes an open connection and does not commit
except where it opens its own transaction.
"""

from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

HISTORY_TURNS = 6


def conversation_title(
    conn: psycopg.Connection, conversation_id: UUID, collection_id: UUID, user_id: UUID
) -> str | None:
    """Return the title when the conversation belongs to this user and collection, else None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT title FROM conversations WHERE id = %s AND collection_id = %s AND user_id = %s",
            (conversation_id, collection_id, user_id),
        )
        row = cur.fetchone()
    return row[0] if row else None


def collection_prompt_settings(conn: psycopg.Connection, collection_id: UUID) -> dict:
    """Return the response preferences and author instructions that shape answers."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT response_preferences, instructions FROM collections WHERE id = %s",
            (collection_id,),
        )
        row = cur.fetchone()
    if row is None:
        return {}
    return {**row[0], "instructions": row[1]}


def create_conversation(
    conn: psycopg.Connection,
    *,
    conversation_id: UUID,
    workspace_id: str,
    collection_id: UUID,
    user_id: UUID,
    title: str,
) -> None:
    """Insert a conversation row. Messages are added when a turn completes."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations (id, workspace_id, collection_id, user_id, title)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, workspace_id, collection_id, user_id, title),
        )


def load_history(conn: psycopg.Connection, conversation_id: UUID) -> list[dict[str, str]]:
    """Return the most recent messages, oldest first, as role and content pairs."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT role, content FROM (
                SELECT seq, role, content FROM messages
                WHERE conversation_id = %s ORDER BY seq DESC LIMIT %s
            ) recent ORDER BY seq
            """,
            (conversation_id, HISTORY_TURNS),
        )
        return [{"role": row[0], "content": row[1]} for row in cur.fetchall()]


def save_turn(
    conn: psycopg.Connection,
    *,
    conversation_id: UUID,
    question: str,
    answer: str,
    citations: list[dict],
) -> str:
    """Store the question and answer as the next two messages. Return the answer's ID."""
    with conn.transaction(), conn.cursor() as cur:
        last_seq = _last_sequence(cur, conversation_id)
        _insert_user_message(cur, conversation_id, last_seq + 1, question)
        return _insert_assistant_message(cur, conversation_id, last_seq + 2, answer, citations)


def _last_sequence(cur: psycopg.Cursor, conversation_id: UUID) -> int:
    """Return the highest message sequence number in the conversation, or 0 when empty."""
    cur.execute(
        "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE conversation_id = %s",
        (conversation_id,),
    )
    return cur.fetchone()[0]


def _insert_user_message(
    cur: psycopg.Cursor, conversation_id: UUID, seq: int, question: str
) -> None:
    """Insert the user's question at the given sequence number."""
    cur.execute(
        """
        INSERT INTO messages (id, conversation_id, seq, role, content)
        VALUES (gen_random_uuid(), %s, %s, 'user', %s)
        """,
        (conversation_id, seq, question),
    )


def _insert_assistant_message(
    cur: psycopg.Cursor,
    conversation_id: UUID,
    seq: int,
    answer: str,
    citations: list[dict],
) -> str:
    """Insert the assistant's answer with its citations and return the new message ID."""
    cur.execute(
        """
        INSERT INTO messages (id, conversation_id, seq, role, content, citations)
        VALUES (gen_random_uuid(), %s, %s, 'assistant', %s, %s)
        RETURNING id
        """,
        (conversation_id, seq, answer, Jsonb(citations)),
    )
    return str(cur.fetchone()[0])


def list_conversations(
    conn: psycopg.Connection, collection_id: UUID, user_id: UUID
) -> list[dict]:
    """Return the user's conversations in this collection that have at least one message."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.title, c.created_at FROM conversations c
            WHERE c.collection_id = %s AND c.user_id = %s
              AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id)
            ORDER BY c.created_at DESC
            """,
            (collection_id, user_id),
        )
        return [{"id": r[0], "title": r[1], "created_at": r[2]} for r in cur.fetchall()]


def conversation_messages(conn: psycopg.Connection, conversation_id: UUID) -> list[dict]:
    """Return every message in the conversation, in order."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, role, content, citations, created_at FROM messages
            WHERE conversation_id = %s ORDER BY seq
            """,
            (conversation_id,),
        )
        return [
            {"id": r[0], "role": r[1], "content": r[2], "citations": r[3], "created_at": r[4]}
            for r in cur.fetchall()
        ]


def document_storage_key(
    conn: psycopg.Connection, collection_id: UUID, document_id: UUID
) -> str | None:
    """Return the stored original's key when the document belongs to the collection."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT storage_key FROM documents WHERE id = %s AND collection_id = %s",
            (document_id, collection_id),
        )
        row = cur.fetchone()
    return row[0] if row else None
