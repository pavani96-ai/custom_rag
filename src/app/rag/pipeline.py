"""Pure ingest steps: read PDF pages, split them into chunks, and derive stable chunk IDs."""

import hashlib
import io
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from llama_index.core import Document
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode
from pypdf import PdfReader

CHUNK_CHARS = 800
OVERLAP_CHARS = 100


@dataclass(frozen=True)
class Chunk:
    """One searchable passage with its page and stable ID."""

    chunk_id: str
    page: int
    text: str


def normalize(text: str) -> str:
    """Collapse runs of whitespace so equal text hashes the same way."""
    return " ".join(text.split())


def extract_pages(data: bytes) -> list[str]:
    """Return the extracted text of each PDF page, in page order."""
    reader = PdfReader(io.BytesIO(data))
    return [page.extract_text() or "" for page in reader.pages]


def chunk_id_for(document_id: str, page: int, index: int, text: str) -> str:
    """Derive a stable ID from the document, its locator, and the normalized text hash."""
    text_hash = hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
    locator = f"{document_id}|page:{page}|chunk:{index}|{text_hash}"
    return str(uuid5(NAMESPACE_URL, locator))


def build_chunks(document_id: str, pages: list[str]) -> list[Chunk]:
    """Split every page into chunks, numbering pages from 1."""
    documents = _page_documents(document_id, pages)
    if not documents:
        return []
    nodes = _split_documents(documents)
    return _to_chunks(document_id, nodes)


def _page_documents(document_id: str, pages: list[str]) -> list[Document]:
    """Wrap each non-empty page as a LlamaIndex document that keeps its page number."""
    return [
        Document(
            id_=f"{document_id}:{page_number}",
            text=cleaned,
            metadata={"page": page_number},
            excluded_embed_metadata_keys=["page"],
        )
        for page_number, page_text in enumerate(pages, start=1)
        if (cleaned := normalize(page_text))
    ]


def _split_documents(documents: list[Document]) -> list[BaseNode]:
    """Split page documents by character budget, using raw text for the chunk size."""
    splitter = SentenceSplitter(
        chunk_size=CHUNK_CHARS,
        chunk_overlap=OVERLAP_CHARS,
        tokenizer=list,
        include_prev_next_rel=False,
    )
    pipeline = IngestionPipeline(transformations=[splitter], disable_cache=True)
    return list(pipeline.run(documents=documents))


def _to_chunks(document_id: str, nodes: list[BaseNode]) -> list[Chunk]:
    """Turn split nodes into chunks with stable IDs, numbered within each page."""
    chunks: list[Chunk] = []
    next_index: dict[int, int] = {}
    for node in nodes:
        page = node.metadata["page"]
        index = next_index.get(page, 0)
        text = node.get_content()
        chunks.append(Chunk(chunk_id_for(document_id, page, index, text), page, text))
        next_index[page] = index + 1
    return chunks
