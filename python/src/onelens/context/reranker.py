"""
reranker.py — Cross-encoder reranker via fastembed-gpu (no torch).

Design (2026-04):
- fastembed TextCrossEncoder + onnxruntime-gpu. No torch, no sentence-transformers.
- Default model: BAAI/bge-reranker-base. Swapped from mxbai-rerank-base-v1
  because mxbai has no official ONNX export on HuggingFace. bge-reranker-base
  is in fastembed 0.8's supported list, peer quality to mxbai-base, ~1 GB.
  (v2-m3 is not in fastembed's default list as of 0.8.)
- Two-stage retrieval: hybrid search returns N=50 candidates, reranker
  scores each (query, doc) pair and keeps top-K=10.
- OOM-safe: halves batch on CUDA OOM; final fallback returns zeros so the
  query returns results instead of crashing.
"""

import logging
import math
import os
import time

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-reranker-base"
DEFAULT_MAX_LENGTH = 512
DEFAULT_BATCH_SIZE = 16


def _resolve_providers(device: str | None) -> tuple[list[str], str]:
    if device == "cpu":
        return (["CPUExecutionProvider"], "cpu")
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
    except Exception:
        return (["CPUExecutionProvider"], "cpu")
    if "CUDAExecutionProvider" in available:
        return (["CUDAExecutionProvider", "CPUExecutionProvider"], "cuda")
    return (["CPUExecutionProvider"], "cpu")


class Reranker:
    """Cross-encoder reranker via fastembed. Loads lazily on first score call."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        max_length: int = DEFAULT_MAX_LENGTH,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        providers, effective_device = _resolve_providers(self.device)
        self.device = effective_device

        logger.info("Loading reranker %s via fastembed (providers=%s)...",
                    self.model_name, providers)
        t0 = time.time()
        self._model = TextCrossEncoder(
            model_name=self.model_name,
            providers=providers,
            max_length=self.max_length,
        )
        logger.info("Reranker ready in %.1fs", time.time() - t0)

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Score (query, doc) pairs. Returns one score per doc, sigmoid-
        normalized to [0, 1]. OOM-safe.

        fastembed's `TextCrossEncoder.rerank` surfaces raw model logits
        (bge-reranker-base outputs roughly -10 to +10). Retrieval filters on
        `ONELENS_MIN_RERANK_SCORE = 0.02` which assumes a 0-1 probability
        range — so without this squash every hit lands below threshold and
        `hybrid_retrieve` returns empty. Matches the Modal wrapper's previous
        squash (which is now a passthrough). Ordering is preserved.
        """
        if not documents:
            return []
        self._ensure_loaded()

        bs = self.batch_size
        while bs >= 1:
            try:
                scores = list(self._model.rerank(query, documents, batch_size=bs))
                return [1.0 / (1.0 + math.exp(-float(s))) for s in scores]
            except RuntimeError as e:
                msg = str(e).lower()
                if "out of memory" in msg or ("cuda" in msg and "memory" in msg):
                    if bs <= 1:
                        logger.warning("Reranker OOM even at batch=1, skipping rerank")
                        return [0.0] * len(documents)
                    bs = max(1, bs // 2)
                    logger.warning("Reranker OOM, retrying with batch=%d", bs)
                    continue
                raise
        return [0.0] * len(documents)

    def rerank(
        self,
        query: str,
        hits: list,
        doc_fn=None,
        top_k: int = None,
    ) -> list:
        """Reorder hits by cross-encoder score."""
        if not hits:
            return hits

        if doc_fn is None:
            doc_fn = _default_doc_fn

        docs = [doc_fn(h) or "" for h in hits]
        scores = self.score(query, docs)
        if not scores or all(s == 0.0 for s in scores):
            return hits[:top_k] if top_k else hits

        ranked = sorted(zip(hits, scores), key=lambda x: -x[1])
        for h, s in ranked:
            if hasattr(h, "rerank_score"):
                h.rerank_score = round(s, 4)
            elif isinstance(h, dict):
                h["rerank_score"] = round(s, 4)
        out = [h for h, _ in ranked]
        return out[:top_k] if top_k else out


def _default_doc_fn(hit) -> str:
    snippet = getattr(hit, "snippet", "") or (hit.get("snippet", "") if isinstance(hit, dict) else "")
    context = getattr(hit, "context_text", "") or (hit.get("context", "") if isinstance(hit, dict) else "")
    return snippet or context or ""


_DEFAULT_RERANKER = None


def get_default_reranker():
    """Returns the configured reranker backend (Modal by default; `none` for noop).

    The local ORT `Reranker` class above still exists and is what the Modal
    container loads inside `remote/modal_app.py`. CLI / MCP / retrieval code
    should call this factory instead of instantiating `Reranker()` directly —
    that way switching `ONELENS_RERANK_BACKEND` actually takes effect.
    """
    global _DEFAULT_RERANKER
    if _DEFAULT_RERANKER is None:
        from onelens.context.embed_backends import get_reranker
        _DEFAULT_RERANKER = get_reranker()
    return _DEFAULT_RERANKER
