"""Application settings. The only module that reads environment variables."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration shared by the API and the Celery worker."""

    # .env at the repo root, read when running from the root or services/api. Missing files
    # are skipped and real environment variables win. extra="ignore" lets .env hold other keys.
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    app_mode: str = "local"
    log_level: str = "INFO"
    redis_url: str = "redis://localhost:6379/0"
    opensearch_url: str = "http://localhost:9200"
    local_storage_path: str = "data/storage"
    database_url: str = ""
    jina_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    # RAG query engine: the model that writes answers in /collections/{id}/ask.
    gemini_model: str = "gemini-3.5-flash"
    # Offline eval judge: writes eval questions and grades answers. Differ from gemini_model.
    gemini_judge_model: str = "gemini-4-hydrogen"
    # Base URL of the running API that the eval script queries. Compose sets it to http://api:8000.
    eval_api_base_url: str = "http://localhost:8000"
    # Comma-separated browser origins allowed to call the API (CORS).
    web_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    google_cloud_project: str = ""
    google_cloud_location: str = "global"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings loaded from the environment."""
    return Settings()
