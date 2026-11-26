"""Pydantic models for HTTP requests and responses, and provider response payloads."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

ResponseFormat = Literal["auto", "prose", "bullets"]
ResponseLength = Literal["brief", "standard", "detailed"]


class ResponsePreferences(BaseModel):
    """How answers are written in a collection. The defaults keep the model's own style."""

    format: ResponseFormat = "auto"
    length: ResponseLength = "standard"


class CollectionIn(BaseModel):
    """Setup fields for a new collection."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=8000)
    response_preferences: ResponsePreferences = Field(default_factory=ResponsePreferences)


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


class IngestItem(BaseModel):
    """One stored original to index: the upload ID from the upload response, and its name."""

    # A SHA-256 hex digest is always 64 characters.
    upload_id: str = Field(min_length=64, max_length=64)
    filename: str = Field(min_length=1, max_length=255)


class IngestIn(BaseModel):
    """A batch of finalized uploads to index. The batch size limit is checked in the route."""

    documents: list[IngestItem] = Field(min_length=1)


class IngestOut(BaseModel):
    """The queued document and the job that tracks its progress."""

    document_id: UUID
    job_id: UUID
    filename: str
    status: str


class SearchIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class Passage(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page: int
    text: str
    score: float = Field(description="Relative fusion score (60% vector, 40% BM25).")


class GeneratedAnswer(BaseModel):
    answer: str
    source_ids: list[int]


class CitedPassage(BaseModel):
    source_id: int
    passage: Passage
    rerank_score: float


class Answer(BaseModel):
    answer: str
    sources: list[CitedPassage]
    retrieved_contexts: list[CitedPassage] | None = None


class EmbeddingItem(BaseModel):
    index: int
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    data: list[EmbeddingItem]


class RerankedResult(BaseModel):
    index: int
    relevance_score: FiniteFloat


class RerankResponse(BaseModel):
    results: list[RerankedResult]


class JobOut(BaseModel):
    """Progress of one ingest job. The document moves with the job."""

    job_id: UUID
    document_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    error_message: str | None = None


class ChatIn(BaseModel):
    """One question in a conversation. Omit conversation_id to start a new one."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None


class ConversationOut(BaseModel):
    """A saved conversation in the collection's history list."""

    id: UUID
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    """One saved message. Assistant messages carry the citations they used."""

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[CitedPassage]
    created_at: datetime


class ConversationDetail(BaseModel):
    """A conversation with its messages in order."""

    id: UUID
    title: str
    messages: list[MessageOut]
