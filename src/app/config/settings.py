"""Application settings. The only module that reads environment variables.

Each field names its environment variable in validation_alias, so the .env keys stay the same
as before. Attribute names stay lowercase; populate_by_name lets code and tests pass them too.
"""

from functools import lru_cache
from uuid import UUID

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration shared by the API and the Celery worker."""

    # .env at the repo root, read when running from the root or services/api. Missing files
    # are skipped and real environment variables win. extra="ignore" lets .env hold other keys.
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), extra="ignore", populate_by_name=True
    )

    # ---------------------------------------------------------------------------------------
    # Runtime: where the app runs, logging, and the service addresses it connects to
    # ---------------------------------------------------------------------------------------
    app_mode: str = Field("local", validation_alias="APP_MODE")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")
    redis_url: str = Field("redis://localhost:6379/0", validation_alias="REDIS_URL")
    database_url: str = Field("", validation_alias="DATABASE_URL")
    opensearch_url: str = Field("http://localhost:9200", validation_alias="OPENSEARCH_URL")
    # Comma-separated browser origins allowed to call the API (CORS).
    web_origins: str = Field(
        "http://127.0.0.1:3000,http://localhost:3000", validation_alias="WEB_ORIGINS"
    )
    # Base URL of the running API that the eval script queries. Compose sets it to http://api:8000.
    eval_api_base_url: str = Field("http://localhost:8000", validation_alias="EVAL_API_BASE_URL")
    # Stand-in for the signed-in user until milestone 2. Matches the local dev fixture (0002).
    dev_user_id: UUID = Field(
        UUID("00000000-0000-4000-8000-000000000001"), validation_alias="DEV_USER_ID"
    )

    # ---------------------------------------------------------------------------------------
    # Storage: local folder for originals, and Google Cloud project settings
    # ---------------------------------------------------------------------------------------
    local_storage_path: str = Field("data/storage", validation_alias="LOCAL_STORAGE_PATH")
    google_cloud_project: str = Field("", validation_alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field("global", validation_alias="GOOGLE_CLOUD_LOCATION")

    # ---------------------------------------------------------------------------------------
    # Upload rules: size limit and the file signature a PDF must start with
    # ---------------------------------------------------------------------------------------
    max_upload_bytes: int = Field(50 * 1024 * 1024, validation_alias="MAX_UPLOAD_BYTES")
    pdf_magic: bytes = Field(b"%PDF", validation_alias="PDF_MAGIC")
    # Most originals one ingest request may queue at once.
    max_batch_files: int = Field(50, validation_alias="MAX_BATCH_FILES")

    # ---------------------------------------------------------------------------------------
    # Request IDs: longest accepted length and the characters a client ID may use
    # ---------------------------------------------------------------------------------------
    request_id_max_length: int = Field(64, validation_alias="REQUEST_ID_MAX_LENGTH")
    request_id_pattern: str = Field(
        r"^[A-Za-z0-9_-]+$", validation_alias="REQUEST_ID_PATTERN"
    )

    # ---------------------------------------------------------------------------------------
    # Ingest chunking: sizes in characters, and the embedding batch size per Jina request
    # ---------------------------------------------------------------------------------------
    chunk_chars: int = Field(800, validation_alias="CHUNK_CHARS")
    chunk_overlap_chars: int = Field(100, validation_alias="CHUNK_OVERLAP_CHARS")
    embed_batch_size: int = Field(32, validation_alias="EMBED_BATCH_SIZE")

    # ---------------------------------------------------------------------------------------
    # Jina: API key, the embedding and rerank models, and the embedding vector size
    # ---------------------------------------------------------------------------------------
    jina_api_key: SecretStr = Field(SecretStr(""), validation_alias="JINA_API_KEY")
    jina_embedding_model: str = Field(
        "jina-embeddings-v5-text-small", validation_alias="JINA_EMBEDDING_MODEL"
    )
    # Vector size of the chunk index. Changing it needs a new index name and a re-ingest.
    jina_embedding_dimension: int = Field(512, validation_alias="JINA_EMBEDDING_DIMENSION")
    jina_rerank_model: str = Field("jina-reranker-v3.5", validation_alias="JINA_RERANK_MODEL")

    # ---------------------------------------------------------------------------------------
    # Retrieval: weights for fusing vector and keyword (BM25) result lists
    # ---------------------------------------------------------------------------------------
    retrieval_vector_weight: float = Field(0.6, validation_alias="RETRIEVAL_VECTOR_WEIGHT")
    retrieval_keyword_weight: float = Field(0.4, validation_alias="RETRIEVAL_KEYWORD_WEIGHT")

    # ---------------------------------------------------------------------------------------
    # OpenSearch chunk index layout. Changing any of these needs a new index name and re-ingest
    # ---------------------------------------------------------------------------------------
    opensearch_index_name: str = Field(
        "chunks_jina_v5_512_v2", validation_alias="OPENSEARCH_INDEX_NAME"
    )
    opensearch_text_field: str = Field("text", validation_alias="OPENSEARCH_TEXT_FIELD")
    opensearch_embedding_field: str = Field(
        "embedding", validation_alias="OPENSEARCH_EMBEDDING_FIELD"
    )
    opensearch_space_type: str = Field("cosinesimil", validation_alias="OPENSEARCH_SPACE_TYPE")
    opensearch_engine: str = Field("lucene", validation_alias="OPENSEARCH_ENGINE")
    opensearch_hnsw_ef_construction: int = Field(
        256, validation_alias="OPENSEARCH_HNSW_EF_CONSTRUCTION"
    )
    opensearch_hnsw_m: int = Field(48, validation_alias="OPENSEARCH_HNSW_M")

    # ---------------------------------------------------------------------------------------
    # Gemini: API key and models for answers and the offline eval judge
    # ---------------------------------------------------------------------------------------
    gemini_api_key: SecretStr = Field(SecretStr(""), validation_alias="GEMINI_API_KEY")
    # RAG query engine: the model that writes answers in /collections/{id}/ask.
    gemini_model: str = Field("gemini-3.5-flash", validation_alias="GEMINI_MODEL")
    # Offline eval judge: writes eval questions and grades answers. Differs from gemini_model.
    gemini_judge_model: str = Field("gemini-4-hydrogen", validation_alias="GEMINI_JUDGE_MODEL")
    # Answer model call timeout, in milliseconds.
    generation_timeout_ms: int = Field(30_000, validation_alias="GENERATION_TIMEOUT_MS")

    @property
    def is_cloud(self) -> bool:
        """True when the app runs in a cloud environment: any APP_MODE other than local."""
        return self.app_mode != "local"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings loaded from the environment."""
    return Settings()
