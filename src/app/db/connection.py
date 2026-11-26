"""Database connections for API requests."""

from collections.abc import Iterator

import psycopg
from fastapi import Depends

from app.config.settings import Settings, get_settings


def get_db(settings: Settings = Depends(get_settings)) -> Iterator[psycopg.Connection]:
    """Open an autocommit connection for one request and close it afterwards."""
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        yield conn
