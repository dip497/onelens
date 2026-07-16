"""OpenAI-compatible embedding backend.

Works against any `POST {base_url}/v1/embeddings` endpoint that follows the
OpenAI schema: OpenAI, Voyage (compat), Together, Mistral, Groq, Nomic,
self-hosted vLLM, HuggingFace TEI, Ollama.

Bulk-optimized path (for full imports):
- Requests run concurrently via httpx.AsyncClient + asyncio.gather, bounded
  by a semaphore so we don't flood a provider's rate limit.
- `max_per_request` batches many texts into one HTTP call (providers accept
  up to 2048 inputs typically — dropping chunks = roundtrip overhead dominates).
- Retries with exponential backoff on 429 / 5xx. Idempotent since embeddings
  are deterministic and we're only POST-ing.
"""

from __future__ import annotations

import asyncio
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)


class OpenAICompatEmbedder:
    """Embedder backed by any OpenAI-compatible /v1/embeddings endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        max_per_request: int = 2048,
        max_concurrency: int = 16,
        timeout_s: float = 60.0,
        max_retries: int = 4,
    ):
        self.base_url = (base_url or os.environ.get("ONELENS_EMBED_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("ONELENS_EMBED_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("ONELENS_EMBED_MODEL", "text-embedding-3-small")
        # `dim` is NOT auto-probed — an empty request would cost money. Let
        # the caller declare it (or we infer from the first real batch).
        # For text-embedding-3-large / -small, passing `dimensions=N` to
        # the API reduces the output vector size (supported natively by
        # OpenAI). We only send the `dimensions` field when the user has
        # explicitly requested a size AND the model supports it.
        env_dim = os.environ.get("ONELENS_EMBED_DIM")
        self._dim: int | None = dim or (int(env_dim) if env_dim else None)
        self.max_per_request = max_per_request
        self.max_concurrency = max_concurrency
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    @property
    def dim(self) -> int:
        if self._dim is None:
            raise RuntimeError(
                "Embedding dim unknown — set ONELENS_EMBED_DIM or call encode() first."
            )
        return self._dim

    @property
    def model_name(self) -> str:
        return self.model

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            # Dim unknown yet → empty (0, 0) array is fine, callers check .size.
            return np.empty((0, self._dim or 0), dtype=np.float32)
        # `asyncio.run` raises if a loop is already running (e.g. called from
        # inside an async MCP handler). Detect that and run in a fresh thread.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._encode_async(texts))
        # Running inside an event loop — run the coroutine in a worker thread
        # with its own loop so we don't deadlock the outer one.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(self._encode_async(texts))).result()

    async def _encode_async(self, texts: list[str]) -> np.ndarray:
        import httpx

        chunks = [
            texts[i : i + self.max_per_request]
            for i in range(0, len(texts), self.max_per_request)
        ]
        sem = asyncio.Semaphore(self.max_concurrency)
        # Shared client → connection pool reuse across all chunks.
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            tasks = [self._embed_chunk(client, sem, chunk) for chunk in chunks]
            results = await asyncio.gather(*tasks)

        out = np.concatenate(results, axis=0).astype(np.float32)
        # Cache dim from the first real response.
        if self._dim is None and out.size:
            self._dim = int(out.shape[1])
        # L2-normalize so downstream cosine = dot product. OpenAI's endpoint
        # already returns unit vectors, but other providers (Voyage, Mistral)
        # don't guarantee it — cheap to enforce uniformly.
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms = np.where(norms == 0.0, 1.0, norms)
        return out / norms

    async def _embed_chunk(
        self,
        client,
        sem: asyncio.Semaphore,
        chunk: list[str],
    ) -> np.ndarray:
        import httpx

        url = f"{self.base_url}/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict = {"model": self.model, "input": chunk}
        # Only the text-embedding-3-* family supports the `dimensions`
        # reducer. We send it only when the user has explicitly asked
        # for a size different from the model's default — keeps
        # compatibility with older endpoints (ada-002) that 400 on
        # unknown params, and with any OpenAI-compat provider that
        # ignores the field.
        if self._dim and self.model.startswith("text-embedding-3"):
            payload["dimensions"] = self._dim

        backoff = 1.0
        async with sem:
            for attempt in range(self.max_retries + 1):
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()["data"]
                        # Provider may return in any order — sort by index.
                        data.sort(key=lambda d: d["index"])
                        return np.array([d["embedding"] for d in data], dtype=np.float32)
                    # 429 rate limit or 5xx → backoff and retry.
                    if resp.status_code in (408, 425, 429) or resp.status_code >= 500:
                        if attempt >= self.max_retries:
                            resp.raise_for_status()
                        logger.warning(
                            "Embedding API %s on attempt %d, sleeping %.1fs",
                            resp.status_code, attempt, backoff,
                        )
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 30.0)
                        continue
                    resp.raise_for_status()
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                    if attempt >= self.max_retries:
                        raise
                    logger.warning("Embedding transport error %s, retry %d", e, attempt)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
        # Unreachable given the raise_for_status above, but type-safe.
        raise RuntimeError("Embedding request exhausted retries")
