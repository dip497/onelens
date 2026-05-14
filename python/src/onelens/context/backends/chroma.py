"""ChromaDB-backed MemPalace collection adapter."""

import logging
import os
import sqlite3

import chromadb

from .base import BaseCollection

logger = logging.getLogger(__name__)


class EmbedderMismatchError(RuntimeError):
    """Raised when the embedder serving a query is not the one that wrote
    the drawers. Cosine similarity across model families is noise — we
    fail loudly rather than return mysteriously-bad retrieval.

    Recovery: re-mine with `onelens import-graph <json> --graph <name>
    --clear --context` (or wipe `~/.onelens/palace/<graph>/` and re-sync
    from the IDE). Only happens when the user changes
    `ONELENS_LOCAL_EMBED_PROFILE` / `ONELENS_LOCAL_EMBED_MODEL` against
    a graph that was already mined with a different embedder.
    """

    def __init__(self, *, collection_name, stored_model, current_model,
                 stored_dim, current_dim):
        self.collection_name = collection_name
        self.stored_model = stored_model
        self.current_model = current_model
        self.stored_dim = stored_dim
        self.current_dim = current_dim
        super().__init__(
            f"Drawer collection {collection_name!r} was written by "
            f"{stored_model!r} (dim={stored_dim}); current process is "
            f"running {current_model!r} (dim={current_dim}). Cosine "
            f"similarity across embedder families is noise — re-mine "
            f"with `--clear` to switch profiles."
        )


class UnstampedLegacyCollectionError(RuntimeError):
    """Raised when a ChromaDB collection has no `onelens_embedder_model`
    metadata stamp. Collections written before EP-6 (drawer version
    stamp) fall here. We fail-closed because we have no proof of which
    embedder wrote the vectors — backfilling the stamp with the current
    embedder would be a lie if the data was actually produced by a
    different model.

    Recovery: re-mine with `onelens import-graph <json> --graph <name>
    --clear --context`. The fresh collection picks up the stamp on
    creation and subsequent runs are validated normally.
    """

    def __init__(self, *, collection_name, current_model, current_dim):
        self.collection_name = collection_name
        self.current_model = current_model
        self.current_dim = current_dim
        super().__init__(
            f"Drawer collection {collection_name!r} has no embedder "
            f"stamp — it was written before OneLens started recording "
            f"which model produced each collection (EP-6, 2026-05-08). "
            f"Current process is running {current_model!r} "
            f"(dim={current_dim}); reading these legacy drawers would "
            f"risk silent retrieval corruption if the original embedder "
            f"differed. Re-mine with `--clear` to fix: "
            f"`onelens import-graph <json> --graph <name> --clear "
            f"--context`."
        )


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

    Embeddings are computed by the attached `LocalEmbedder` (not by
    ChromaDB's default EF). The factory in `embed_backends/__init__.py`
    picks the active backend (local ONNX / OpenAI-compat / Modal); the
    drawer write path is provider-agnostic.
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

    We embed externally via `LocalEmbedder` (see
    `embed_backends/local_backend.py`) for full control over batch size,
    max_seq_length, and provider selection. ChromaDB collections are
    created WITHOUT an embedding_function — all upserts pass pre-computed
    embeddings directly.
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

        embedder = self._get_embedder()
        # Stamp the embedder's identity into the collection metadata at
        # creation time. Reads against an existing collection check that
        # the current process's embedder matches what wrote the drawers —
        # cosine similarity across model families (Jina vs Gemma vs BGE)
        # is noise, not partial recall, so a silent mismatch must surface
        # as a hard error instead of mysteriously bad retrieval.
        stamp = {
            "hnsw:space": "cosine",
            "onelens_embedder_model": embedder.model_name,
            "onelens_embedder_dim": int(embedder.dim),
        }
        if create:
            collection = self._client.get_or_create_collection(
                collection_name, metadata=stamp,
            )
        else:
            collection = self._client.get_collection(collection_name)

        # Single validation path — handles three states:
        #   1. New collection (created by us this call) → stamp is in `stamp`
        #      and ChromaDB just persisted it. _validate_stamp() passes trivially.
        #   2. Existing collection with our stamp → match check, raise on
        #      mismatch.
        #   3. Existing collection without our stamp (legacy, pre-EP-6) →
        #      fail-closed: raise UnstampedLegacyCollectionError. We refuse
        #      to read because we have no way to know what model wrote those
        #      drawers; cosine similarity across embedder families is noise.
        #      Recovery is `--clear` + re-mine, same as a real mismatch.
        #      Backfilling the stamp with the current embedder would be a
        #      lie if that embedder is different from what actually wrote
        #      the data, so we don't.
        self._validate_stamp(collection, collection_name, embedder)
        return ChromaCollection(collection, embedder=embedder)

    @staticmethod
    def _validate_stamp(collection, collection_name: str, embedder) -> None:
        """Check the collection's embedder stamp matches the current embedder.

        Raises:
            EmbedderMismatchError: stamp is present and points at a
                different model than the one we'd query with.
            UnstampedLegacyCollectionError: collection has no stamp at
                all. Pre-EP-6 collections fall here. Fail-closed because
                we cannot prove the data was written by an embedder we
                trust.
        """
        md = collection.metadata or {}
        stored_model = md.get("onelens_embedder_model")
        stored_dim = md.get("onelens_embedder_dim")
        if stored_model is None:
            raise UnstampedLegacyCollectionError(
                collection_name=collection_name,
                current_model=embedder.model_name,
                current_dim=embedder.dim,
            )
        if stored_model != embedder.model_name:
            raise EmbedderMismatchError(
                collection_name=collection_name,
                stored_model=stored_model, current_model=embedder.model_name,
                stored_dim=stored_dim, current_dim=embedder.dim,
            )

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
