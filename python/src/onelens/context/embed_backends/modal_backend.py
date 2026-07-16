"""Modal-backed embedder + reranker.

Client-side wrapper that calls a deployed Modal app (see
`onelens.remote.modal_app`). Bulk path fan-outs via `modal.Function.map()`
so Modal's autoscaler spreads work across multiple GPU containers.
"""

from __future__ import annotations

import logging
import os
import time

import numpy as np

from .base import RerankerBase

logger = logging.getLogger(__name__)


def _retry_remote(fn, *args, attempts: int = 3, backoff: float = 1.0, **kwargs):
    """Retry a Modal .remote()/.map() call with exponential backoff.

    Transient failures on Modal — container evictions, scale-to-zero races,
    network blips — surface as generic exceptions. Cheap to retry since
    embedding + rerank are idempotent.
    """
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if i == attempts - 1:
                raise
            sleep_s = backoff * (2 ** i)
            logger.warning("Modal call failed (%s); retrying in %.1fs", e, sleep_s)
            time.sleep(sleep_s)
    # Unreachable but makes type-checker happy.
    raise last_exc or RuntimeError("retry exhausted")

DEFAULT_APP = "onelens-embed"
DEFAULT_CLASS = "Embedder"
DEFAULT_CHUNK_SIZE = 96    # docs per Modal call — L4 24GB OOMs at 256 on Qwen3 seq=512; 96 is safe
DEFAULT_DIM = 1024         # Qwen3-Embedding-0.6B


class ModalEmbedder:
    """Client for the deployed OneLens Modal embedding app."""

    def __init__(
        self,
        app_name: str | None = None,
        class_name: str = DEFAULT_CLASS,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ):
        self.app_name = app_name or os.environ.get("ONELENS_MODAL_APP", DEFAULT_APP)
        self.class_name = class_name
        self.chunk_size = chunk_size
        self._cls = None

    def _resolve(self):
        if self._cls is not None:
            return self._cls
        import modal
        # `from_name` is lazy — first call loads the deployed class reference
        # (one metadata round-trip; no container spin-up yet).
        self._cls = modal.Cls.from_name(self.app_name, self.class_name)
        return self._cls

    @property
    def dim(self) -> int:
        return DEFAULT_DIM

    @property
    def model_name(self) -> str:
        return "Qwen/Qwen3-Embedding-0.6B (modal)"

    @property
    def device(self) -> str:
        return "modal:L4"

    def encode(self, texts: list[str]) -> np.ndarray:
        """Sequential single-container calls — no `.map()`.

        `.map()` fan-out across multiple GPU containers produced ~85% NaN
        vectors in dogfood (verified with both Qwen3 and arctic-embed-l
        models — not model-specific). Same input sent via single
        `.remote()` returned 0 NaN. Root cause: concurrent cold-boot of
        several snapshot-restored L4 containers leaves some with broken
        CUDA / embedder state that silently produces NaN. Single-container
        sequential is slower but deterministic. fastembed on L4 already
        batches internally, so one container handles 2-3K docs comfortably.

        For very large imports we chunk client-side and call `.remote()`
        per chunk — keeps the same container warm across calls.
        """
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)
        cls = self._resolve()
        instance = cls()

        if len(texts) <= self.chunk_size:
            vecs = _retry_remote(instance.embed.remote, texts)
            return np.asarray(vecs, dtype=np.float32)

        chunks = [texts[i : i + self.chunk_size] for i in range(0, len(texts), self.chunk_size)]
        logger.info(
            "ModalEmbedder: %d docs → %d chunks, sequential single-call",
            len(texts), len(chunks),
        )
        pieces = [
            np.asarray(_retry_remote(instance.embed.remote, chunk), dtype=np.float32)
            for chunk in chunks
        ]
        return np.concatenate(pieces, axis=0)


class ModalReranker(RerankerBase):
    """Client for the deployed OneLens Modal rerank endpoint."""

    def __init__(self, app_name: str | None = None, class_name: str = DEFAULT_CLASS):
        self.app_name = app_name or os.environ.get("ONELENS_MODAL_APP", DEFAULT_APP)
        self.class_name = class_name
        self._cls = None

    def _resolve(self):
        if self._cls is not None:
            return self._cls
        import modal
        self._cls = modal.Cls.from_name(self.app_name, self.class_name)
        return self._cls

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        cls = self._resolve()
        scores = _retry_remote(cls().rerank.remote, query, documents)
        return [float(s) for s in scores]
 