"""Apply SQL migrations in filename order. Each file runs once, inside its own transaction."""

import sys
from pathlib import Path

import psycopg

from app.config.settings import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def list_migrations(directory: Path) -> list[Path]:
    """Return the migration files in the directory, sorted by name."""
    return sorted(directory.glob("*.sql"))


def apply_migrations(conn: psycopg.Connection, directory: Path) -> list[str]:
    """Apply every migration not yet recorded and return the versions applied."""
    applied: list[str] = []
    with conn.cursor() as cur:
        cur.execute(CREATE_TRACKING_TABLE)
        cur.execute("SELECT version FROM schema_migrations")
        done = {row[0] for row in cur.fetchall()}
    for path in list_migrations(directory):
        if path.name in done:
            continue
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,)
            )
        applied.append(path.name)
    return applied


def main() -> int:
    """Connect using DATABASE_URL and apply pending migrations."""
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 1
    with psycopg.connect(url, autocommit=True) as conn:
        for version in apply_migrations(conn, MIGRATIONS_DIR):
            print(f"applied {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
