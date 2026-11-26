"""Domain exceptions raised by storage, providers, search, and the ingest steps."""


class StorageError(Exception):
    """Raised when an original cannot be written to or read from storage."""


class OriginalNotStoredError(Exception):
    """The original for an upload ID is not in storage, so it cannot be indexed."""


class EmbeddingError(Exception):
    """The embedding service could not return usable vectors."""


class RerankError(Exception):
    """Jina did not return a usable reranking result."""


class IndexingError(Exception):
    """Raised when OpenSearch reports a shard failure while counting chunks."""
