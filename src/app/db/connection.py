"""Database connections for API requests."""

from collections.abc import Iterator

import psycopg

from app.config.settings import get_settings


def get_db() -> Iterator[psycopg.Connection]:
    """Open an autocommit connection for one request and close it afterwards."""
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        yield conn
