"""Tests for the migration runner. A fake connection stands in for PostgreSQL."""

from pathlib import Path

from app.db.migrate import list_migrations

MIGRATIONS = Path(__file__).resolve().parents[1] / "app" / "db" / "migrations"


def test_migrations_are_ordered_and_named() -> None:
    """Migration files sort by number, so the core schema runs before the seed."""
    names = [path.name for path in list_migrations(MIGRATIONS)]
    assert names == [
        "0001_core_schema.sql",
        "0002_seed_dev_fixture.sql",
        "0003_document_pages.sql",
    ]


def test_core_schema_declares_job_and_outbox_tables() -> None:
    """The core migration creates the job, outbox, and index pointer tables."""
    sql = (MIGRATIONS / "0001_core_schema.sql").read_text(encoding="utf-8")
    for table in ["jobs", "outbox", "index_pointers", "artifacts", "messages"]:
        assert f"CREATE TABLE {table} (" in sql
