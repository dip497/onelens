"""ChromaDB-backed MemPalace collection adapter."""

import logging
import os
import sqlite3

import chromadb

from .base import BaseCollection

logger = logging.getLogger(__name__)


def _fix_blob_seq_ids(palace_path: str):
    """Fix ChromaDB 0.6.x -> 1.5.x migration bug: BLOB seq_ids -> INTEGER.

    ChromaDB 0.6.x stored seq_id as big-endian 8-byte BLOBs. ChromaDB 1.5.x
    expects INTEGER. The auto-migration doesn't convert existing rows, causing
    the Rust compactor to crash with "mismatched types; Rust type u64 (as SQL
    type INTEGER) is not compatible with SQL type BLOB".

    Must run BEFORE PersistentClient is created (the compactor fires on init).
    """
    db_path = os.path.join(palace_path, "chroma.sqlite3")
    if not os.path.isfile(db_path):
        return
    try:
        with sqlite3.connect(db_path) as conn:
            for table in ("embeddings", "max_seq_id"):
                try:
                    rows = conn.execute(
                        f"SELECT rowid, seq_id FROM {table} WHERE typeof(seq_id) = 'blob'"
                    ).fetchall()
                except sqlite3.OperationalError:
                    continue
                if not rows:
                    continue
                updates = [(int.from_bytes(blob, byteorder="big"), rowid) for rowid, blob in rows]
                conn.executemany(f"UPDATE {table} SET seq_id = ? WHERE rowid = ?", updates)
                logger.info("Fixed %d BLOB seq_ids in %s", len(updates), table)
            conn.commit()
    except Exception:
        logger.exception("Could not fix BLOB seq_ids in %s", db_path)


class ChromaCollection(BaseCollection):
    """Thin adapter over a ChromaDB collection with external embedder.

    Embeddings are computed by the attached QwenEmbedder (not by ChromaDB's
    default EF). This lets us batch-encode with torch.compile, control
    max_seq_length, and use bf16.
    """

    def __init__(self, collection, embedder=None):
        self._collection = collection
        self._embedder = embedder

    def _embed(self, documents):
        if self._embedder is None:
            raise RuntimeError("ChromaCollection has no embedder attached")
        return self._embedder.encode(documents).tolist()

    def add(self, *, documents, ids, metadatas=None):
        embeddings = self._embed(documents)
        self._collection.add(
            documents=documents, ids=ids, metadatas=metadatas, embeddings=embeddings
        )

    def upsert(self, *, documents, ids, metadatas=None):
        embeddings = self._embed(documents)
        self._collection.upsert(
            documents=documents, ids=ids, metadatas=metadatas, embeddings=embeddings
        )

    def query(self, *, query_texts=None, **kwargs):
        # Embed query text with the same model so query/doc vectors live in same space
        if query_texts is not None and "query_embeddings" not in kwargs:
            kwargs["query_embeddings"] = self._embed(query_texts)
            return self._collection.query(**kwargs)
        return self._collection.query(query_texts=query_texts, **kwargs)

    def get(self, **kwargs):
        return self._collection.get(**kwargs)

    def delete(self, **kwargs):
        self._collection.delete(**kwargs)

    def count(self):
        return self._collection.count()


class ChromaBackend:
    """Factory for OneLens context ChromaDB backend.

    We embed externally via QwenEmbedder (see context/embedder.py) for full
    control over batch size, max_seq_length, and torch.compile. ChromaDB
    collections are created WITHOUT an embedding_function — all upserts pass
    pre-computed embeddings directly.
    """

    def __init__(self):
        self._client = None
        self._client_path = None
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            # Route through the backend factory so the chosen remote
            # (Modal / OpenAI-compat) is honored. The local ORT path is
            # still available but only as the Modal container's internals.
            from onelens.context.embed_backends import get_embedder
            self._embedder = get_embedder()
        return self._embedder

    def get_collection(self, palace_path: str, collection_name: str, create: bool = False):
        if not create and not os.path.isdir(palace_path):
            raise FileNotFoundError(palace_path)

        if create:
            os.makedirs(palace_path, exist_ok=True)
            try:
                os.chmod(palace_path, 0o700)
            except (OSError, NotImplementedError):
                pass

        _fix_blob_seq_ids(palace_path)
        if self._client is None or self._client_path != palace_path:
            self._client = chromadb.PersistentClient(path=palace_path)
            self._client_path = palace_path

        if create:
            collection = self._client.get_or_create_collection(
                collection_name, metadata={"hnsw:space": "cosine"}
            )
        else:
            collection = self._client.get_collection(collection_name)
            # Dim sanity check: if the collection was written with a different
            # embedder (e.g. Qwen3 1024-dim), querying it with Jina (768-dim)
            # gives silently wrong results — ChromaDB hashes the query to the
            # stored space and the cosine becomes meaningless. Catch it early
            # with a clear message so the user re-syncs with --clear.
            embedder = self._get_embedder()
            try:
                sample = collection.peek(limit=1)
                stored = sample.get("embeddings") or []
                if stored and len(stored[0]) and len(stored[0]) != embedder.dim:
                    raise ValueError(
                        f"Embedder dimension mismatch: collection '{collection_name}' "
                        f"was written with dim={len(stored[0])} but the active "
                        f"embedder ({embedder.model_name}) is dim={embedder.dim}. "
                        f"Re-sync with --clear to rebuild the index, or switch "
                        f"ONELENS_EMBED_BACKEND back to whatever wrote it."
                    )
            except ValueError:
                raise
            except Exception:
                # Peek can fail on an empty collection — not an error.
                pass
        return ChromaCollection(collection, embedder=self._get_embedder())

    @property
    def embedding_device(self) -> str:
        if self._embedder is None:
            return "not-loaded"
        return self._embedder.device

    @property
    def max_batch_size(self) -> int:
        """Max batch size from the current client (write batch, not embed batch)."""
        if self._client:
            for attr in ("max_batch_size", "get_max_batch_size"):
                fn = getattr(self._client, attr, None)
                if fn is not None:
                    return fn() if callable(fn) else fn
        return 5000
