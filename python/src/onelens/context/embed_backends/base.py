"""Protocols for pluggable embedding + rerank backends.

Two remote backends ship today:
- `modal` — GPU-snapshot Modal deployment, Qwen3-Embedding-0.6B + bge-reranker-base
- `openai_compat` — any /v1/embeddings-compatible API (OpenAI, Voyage, Together,
  Mistral, vLLM, TEI, Ollama)

Rerank has no OpenAI standard — only Modal ships rerank out of the box.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class EmbedBackend(Protocol):
    """Embedder contract. Implementations MUST return (N, dim) float32,
    L2-normalized so downstream cosine math uses dot-product directly."""

    def encode(self, texts: list[str]) -> np.ndarray: ...

    @property
    def dim(self) -> int: ...

    @property
    def model_name(self) -> str: ...


class RerankerBase:
    """Base class for reranker backends.

    Subclasses implement `score()`. The `rerank()` helper reorders a list of
    hits using those scores — matches the retrieval-pipeline API that used
    to live on the local `Reranker` class.
    """

    def score(self, query: str, documents: list[str]) -> list[float]:
        raise NotImplementedError

    def rerank(
        self,
        query: str,
        hits: list,
        doc_fn=None,
        top_k: int | None = None,
    ) -> list:
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


class NoopReranker(RerankerBase):
    """Fallback when no rerank backend is configured. Returns zeros so
    retrieval keeps the embedding-score order."""

    def score(self, query: str, documents: list[str]) -> list[float]:
        return [0.0] * len(documents)


def _default_doc_fn(hit) -> str:
    snippet = getattr(hit, "snippet", "") or (hit.get("snippet", "") if isinstance(hit, dict) else "")
    context = getattr(hit, "context_text", "") or (hit.get("context", "") if isinstance(hit, dict) else "")
    return snippet or context or ""
