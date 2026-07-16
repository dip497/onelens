"""TEI (HuggingFace Text Embeddings Inference) backend — opt-in runtime.

TEI is a Rust-based inference server with Flash Attention, token-based
dynamic batching, and OpenAI-compatible embedding output. It supports
the JinaBERT family (our default Jina-v2-base-code) and BGE rerankers
natively via ONNX or Candle backends.

Use this backend when you already run TEI (e.g. on a shared workstation
or CI runner) and want OneLens to point at it instead of loading the
ONNX model in-process. Wins:

- 2-4× faster indexing on Linux GPU via Flash Attention + dynamic batching
- One model load shared across multiple OneLens callers (plugin + Claude
  Code + bench harness) without us managing a singleton on top of ours
- Production observability for free (Prometheus, OpenTelemetry)

Limitations:

- TEI is **one model per instance** (upstream issue #92, closed
  not-planned Nov 2023). Embedder + reranker = two TEI processes.
- No bundled install path. User runs TEI themselves:
      cargo install --path router -F ort               # Linux x86 ONNX
      cargo install --path router -F metal             # Mac M-series
      docker run ghcr.io/huggingface/text-embeddings-inference:cuda-1.9
- macOS GPU support is Metal (works, less optimised than CUDA path).

Embedding via TEI is already covered by the `openai_compat` backend —
TEI exposes `POST /v1/embeddings`. Set:

    ONELENS_EMBED_BACKEND=openai
    ONELENS_EMBED_BASE_URL=http://127.0.0.1:8080/v1
    ONELENS_EMBED_MODEL=jinaai/jina-embeddings-v2-base-code   (TEI ignores; only for our logging)
    ONELENS_EMBED_DIM=768

This module adds the rerank half — TEI's `POST /rerank` has no OpenAI
analogue, so we hit the native endpoint directly.

Config env vars:
    ONELENS_TEI_RERANK_URL   default: http://127.0.0.1:8081
    ONELENS_TEI_API_KEY      optional bearer token (TEI behind a proxy)
    ONELENS_TEI_TIMEOUT_S    default: 30
"""

from __future__ import annotations

import logging
import os

from .base import RerankerBase

logger = logging.getLogger(__name__)


class TEIReranker(RerankerBase):
    """Cross-encoder reranker backed by a TEI `/rerank` endpoint.

    Response shape (per TEI README):
        POST /rerank
        { "query": str, "texts": [str, ...], "raw_scores": bool,
          "return_text": bool, "truncate": bool }
        →
        [ { "index": int, "score": float, "text": str | null }, ... ]

    Indices in the response refer back to positions in the input `texts`
    array. We re-emit scores aligned with the caller's original order so
    `RerankerBase.rerank()` can sort without further bookkeeping.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_s: float | None = None,
    ):
        # httpx is already a transitive dep via openai_compat; no new wheel.
        import httpx

        self.base_url = (
            base_url
            or os.environ.get("ONELENS_TEI_RERANK_URL")
            or "http://127.0.0.1:8081"
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("ONELENS_TEI_API_KEY") or ""
        self.timeout_s = timeout_s or float(os.environ.get("ONELENS_TEI_TIMEOUT_S", "30"))

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_s,
        )
        logger.info("TEIReranker → %s", self.base_url)

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        try:
            resp = self._client.post(
                "/rerank",
                json={
                    "query": query,
                    "texts": documents,
                    "raw_scores": False,        # TEI applies sigmoid by default
                    "return_text": False,
                    "truncate": True,
                },
            )
            resp.raise_for_status()
        except Exception as e:
            # Match LocalReranker / NoopReranker semantics: failures must
            # not crash retrieval. Returning zeros makes RerankerBase.rerank
            # short-circuit to the input order (FTS+semantic RRF stays
            # authoritative).
            logger.warning("TEI rerank request failed: %s — returning zero scores", e)
            return [0.0] * len(documents)

        rows = resp.json()
        if not isinstance(rows, list):
            logger.warning("TEI rerank returned non-list payload: %r", rows)
            return [0.0] * len(documents)

        scores = [0.0] * len(documents)
        for row in rows:
            try:
                idx = int(row["index"])
                score = float(row["score"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= idx < len(scores):
                scores[idx] = score
        return scores

    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass
