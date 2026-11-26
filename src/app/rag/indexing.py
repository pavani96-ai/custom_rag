"""Index one document: parse, chunk, embed, write to OpenSearch, then mark it ready or failed."""

from dataclasses import dataclass

import psycopg
import structlog
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import TextNode
from opensearchpy import OpenSearch

from app.config.settings import Settings
from app.db.jobs import record_failure, record_success, set_status
from app.rag.document_storage import ObjectStorage
from app.rag.embedder import Embedder
from app.rag.llm import JinaLlamaEmbedding
from app.rag.pipeline import Chunk, build_chunks, extract_pages
from app.rag.vectorstore import build_vector_store, count_chunks

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True)
class IndexJob:
    """Identifiers and source location for one document's indexing run."""

    job_id: str
    document_id: str
    collection_id: str
    workspace_id: str
    filename: str
    storage_key: str


def index_document(
    *,
    conn: psycopg.Connection,
    storage: ObjectStorage,
    embedder: Embedder,
    search: OpenSearch,
    job: IndexJob,
    settings: Settings,
) -> int:
    """Run the full indexing steps for one document and return its chunk count."""
    reused = _reuse_ready_index(conn, search, job.job_id, job.document_id, settings)
    if reused is not None:
        return reused

    set_status(conn, job.job_id, job.document_id, "running")
    return _run_steps(conn, storage, embedder, search, job, settings)


def _run_steps(
    conn: psycopg.Connection,
    storage: ObjectStorage,
    embedder: Embedder,
    search: OpenSearch,
    job: IndexJob,
    settings: Settings,
) -> int:
    """Load, chunk, embed, and write one document, then record success or failure."""
    try:
        pages, chunks = _load_chunks(storage, job.storage_key, job.document_id, settings)
        _write_chunks(embedder, search, chunks, job, settings)
    except Exception:
        logger.exception("index_failed", job_id=job.job_id, document_id=job.document_id)
        record_failure(conn, job.job_id, job.document_id)
        raise
    record_success(conn, job.job_id, job.document_id, pages)
    logger.info("index_succeeded", job_id=job.job_id, pages=pages, chunks=len(chunks))
    return len(chunks)


def _reuse_ready_index(
    conn: psycopg.Connection,
    search: OpenSearch,
    job_id: str,
    document_id: str,
    settings: Settings,
) -> int | None:
    """Return the existing chunk count when a ready document is already indexed, else None."""
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
    if row != ("ready",):
        return None
    chunk_count = count_chunks(search, document_id, settings)
    if not chunk_count:
        return None
    set_status(conn, job_id, document_id, "succeeded")
    logger.info("index_reused", job_id=job_id, document_id=document_id, chunks=chunk_count)
    return chunk_count


def _load_chunks(
    storage: ObjectStorage, storage_key: str, document_id: str, settings: Settings
) -> tuple[int, list[Chunk]]:
    """Read the stored PDF and return its page count and chunks."""
    pages = extract_pages(storage.load(storage_key))
    return len(pages), build_chunks(document_id, pages, settings)


def _write_chunks(
    embedder: Embedder,
    search: OpenSearch,
    chunks: list[Chunk],
    job: IndexJob,
    settings: Settings,
) -> None:
    """Embed the chunks through LlamaIndex and write them to the chunk vector store."""
    if not chunks:
        return
    storage = StorageContext.from_defaults(
        vector_store=build_vector_store(search, embedder.dimension, settings)
    )
    nodes = [_chunk_node(chunk, job) for chunk in chunks]
    VectorStoreIndex(
        nodes,
        storage_context=storage,
        embed_model=JinaLlamaEmbedding(embedder, embedder, settings.embed_batch_size),
        show_progress=False,
    )


def _chunk_node(chunk: Chunk, job: IndexJob) -> TextNode:
    """Build one node with a stable ID. Its metadata is kept out of the embedded text."""
    metadata = {
        "chunk_id": chunk.chunk_id,
        "workspace_id": job.workspace_id,
        "collection_id": job.collection_id,
        "source_document_id": job.document_id,
        "filename": job.filename,
        "page": chunk.page,
    }
    keys = list(metadata)
    return TextNode(
        id_=chunk.chunk_id,
        text=chunk.text,
        metadata=metadata,
        excluded_embed_metadata_keys=keys,
        excluded_llm_metadata_keys=keys,
    )
