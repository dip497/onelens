"""
reranker.py — Cross-encoder reranker for two-stage retrieval.

Design (2026 benchmarks, see docs for sources):
- mixedbread-ai/mxbai-rerank-base-v1 (352 MB, standard DeBERTa-v3 arch).
  Picked over jina-reranker-v2 (531 MB, custom code incompatible with
  transformers>=5.x) and bge-reranker-large (2.1 GB, won't fit alongside
  our 1.2 GB embedder on a 4 GB GPU).
- Two-stage retrieval: hybrid search returns N=50 candidates, reranker
  scores each (query, doc) pair and keeps top-K=10 (N >> K principle).
- Measured on RTX A2000 4 GB: peak VRAM 1.6 GB (both embedder + reranker
  loaded), 50 pairs scored in ~0.1-1.3 s depending on seq length.
- Fallback: if OOM during scoring, halve batch and retry; ultimately skip
  reranking rather than crash the query.
"""

import logging
import time

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "mixedbread-ai/mxbai-rerank-base-v1"
DEFAULT_MAX_LENGTH = 512
DEFAULT_BATCH_SIZE = 16  # conservative; mxbai-base is cheap enough


class Reranker:
    """Cross-encoder reranker with OOM-safe scoring.

    Loads lazily (first score call) so the model isn't paid for when
    reranking is disabled.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = None,
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
        import torch
        from sentence_transformers import CrossEncoder

        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info("Loading reranker %s on %s...", self.model_name, self.device)
        t0 = time.time()
        self._model = CrossEncoder(self.model_name, device=self.device, max_length=self.max_length)
        logger.info("Reranker ready in %.1fs", time.time() - t0)

    def score(self, query: str, documents: list[str]) -> list[float]:
        """Score (query, document) pairs. Returns one score per doc.

        OOM-safe: halves batch size and retries on CUDA OOM; final fallback
        returns zeros (rerank disabled) rather than crashing.
        """
        if not documents:
            return []
        self._ensure_loaded()

        pairs = [(query, d) for d in documents]
        bs = self.batch_size
        while bs >= 1:
            try:
                scores = self._model.predict(pairs, batch_size=bs, show_progress_bar=False)
                return [float(s) for s in scores]
            except RuntimeError as e:
                msg = str(e).lower()
                if "out of memory" in msg or "cuda" in msg and "memory" in msg:
                    if self.device == "cuda":
                        import torch
                        torch.cuda.empty_cache()
                    if bs <= 1:
                        logger.warning("Reranker OOM even at batch=1, skipping rerank")
                        return [0.0] * len(documents)
                    bs = max(1, bs // 2)
                    logger.warning("Reranker OOM, retrying with batch=%d", bs)
                    continue
                raise

    def rerank(
        self,
        query: str,
        hits: list,
        doc_fn=None,
        top_k: int = None,
    ) -> list:
        """Reorder a list of hits by cross-encoder score.

        Args:
            query: original user query
            hits: list of items to rerank (any objects/dicts)
            doc_fn: callable extracting document text from each hit
                    (default: hit.snippet or hit.context_text for RetrievalHit)
            top_k: truncate to top_k after reranking (default: keep all)
        """
        if not hits:
            return hits

        if doc_fn is None:
            doc_fn = _default_doc_fn

        docs = [doc_fn(h) or "" for h in hits]
        scores = self.score(query, docs)
        if not scores or all(s == 0.0 for s in scores):
            return hits[:top_k] if top_k else hits

        ranked = sorted(zip(hits, scores), key=lambda x: -x[1])
        # Attach the rerank score onto each hit when possible
        for h, s in ranked:
            if hasattr(h, "rerank_score"):
                h.rerank_score = round(s, 4)
            elif isinstance(h, dict):
                h["rerank_score"] = round(s, 4)
        out = [h for h, _ in ranked]
        return out[:top_k] if top_k else out


def _default_doc_fn(hit) -> str:
    """Extract document text for cross-encoder scoring.

    Prefers the actual code snippet (richer signal); falls back to the
    embedding doc text (FQN + metadata) when snippet unavailable.
    """
    snippet = getattr(hit, "snippet", "") or (hit.get("snippet", "") if isinstance(hit, dict) else "")
    context = getattr(hit, "context_text", "") or (hit.get("context", "") if isinstance(hit, dict) else "")
    return snippet or context or ""


# Module-level singleton so the model stays loaded across queries in a session.
_DEFAULT_RERANKER: Reranker = None


def get_default_reranker() -> Reranker:
    """Return a lazily-initialized shared Reranker instance."""
    global _DEFAULT_RERANKER
    if _DEFAULT_RERANKER is None:
        _DEFAULT_RERANKER = Reranker()
    return _DEFAULT_RERANKER
