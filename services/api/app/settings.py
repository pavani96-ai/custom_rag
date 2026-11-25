"""Application settings. The only module that reads environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration shared by the API and the Celery worker."""

    app_mode: str = "local"
    log_level: str = "INFO"
    redis_url: str = "redis://localhost:6379/0"
    opensearch_url: str = "http://localhost:9200"
    local_storage_path: str = "data/storage"
    database_url: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings loaded from the environment."""
    return Settings()
