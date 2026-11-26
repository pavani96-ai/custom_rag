"""LlamaIndex embedding adapter. Every vector call goes through our Jina embedders."""

from llama_index.core.embeddings import BaseEmbedding
from pydantic import PrivateAttr

from app.rag.providers.embedder import Embedder

EMBED_BATCH_SIZE = 32


class JinaLlamaEmbedding(BaseEmbedding):
    """Embed index writes with the passage embedder and queries with the query embedder."""

    _index_embedder: Embedder = PrivateAttr()
    _query_embedder: Embedder = PrivateAttr()

    def __init__(self, index_embedder: Embedder, query_embedder: Embedder) -> None:
        """Keep both embedders. Batches are sized to match our provider calls."""
        super().__init__(embed_batch_size=EMBED_BATCH_SIZE, model_name="jina-embeddings-v5")
        self._index_embedder = index_embedder
        self._query_embedder = query_embedder

    def _get_query_embedding(self, query: str) -> list[float]:
        """Embed one question with the query task."""
        return self._query_embedder.embed([query])[0]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        """Async callers use the same synchronous provider call."""
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        """Embed one chunk with the passage task."""
        return self._index_embedder.embed([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunks with the passage task."""
        return self._index_embedder.embed(texts)
