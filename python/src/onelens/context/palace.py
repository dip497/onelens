"""
palace.py — Shared context collection operations.

Provides the ChromaDB collection factory for the context graph.
"""

from .backends.chroma import ChromaBackend
from .config import DEFAULT_COLLECTION_NAME

_DEFAULT_BACKEND = ChromaBackend()


def get_collection(
    context_path: str,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    create: bool = True,
):
    """Get the ChromaDB collection for a graph's context."""
    return _DEFAULT_BACKEND.get_collection(
        context_path,
        collection_name=collection_name,
        create=create,
    )


def get_max_batch_size() -> int:
    """Max batch size supported by the current ChromaDB client."""
    return _DEFAULT_BACKEND.max_batch_size


def get_embedding_device() -> str:
    """Device used for embedding: 'cuda', 'cpu', or 'cpu-onnx'."""
    return _DEFAULT_BACKEND.embedding_device
