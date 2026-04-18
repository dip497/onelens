"""Modal deployment for OneLens embedding + rerank.

Deploy once per Modal workspace:

    modal deploy python/src/onelens/remote/modal_app.py

The client (onelens.context.embed_backends.modal_backend) looks up this app
by name and calls the `embed` / `rerank` methods.

Architecture:
- Qwen3-Embedding-0.6B + BGE-reranker-base, ONNX + onnxruntime-gpu (no torch).
- Weights live on a named Modal Volume — download once, cached across cold
  starts and container replicas.
- `enable_memory_snapshot=True` + `enable_gpu_snapshot=True` flatten cold
  start from ~30s to ~2-3s by freezing the loaded ORT session + CUDA context
  into a snapshot Modal can restore instantly.
- `scaledown_window=600` keeps a warm container for 10 min after last call,
  so bursty dev usage (10 queries/min, then idle) pays for just one warm
  window per burst (~$0.13 on L4).

Cost sanity (April 2026, L4 @ $0.80/hr = $0.000222/sec):
- Cold start (snapshot): ~3s → $0.0007
- Warm query (embed + rerank 50 docs): ~100ms → $0.00002
- Full import (10K methods via .map, 4 containers): ~30s wall, ~120 GPU-s → $0.027
- Daily idle tax (5 bursts × 10 min window): ~$0.65
"""

from __future__ import annotations

import modal

APP_NAME = "onelens-embed"
# snowflake/snowflake-arctic-embed-l — 1024-dim, ~55 BEIR, fastembed-
# native. Qwen3-Embedding-0.6B is higher quality on paper (~62 BEIR) but
# its ONNX export has an unfixable left-padding + attention bug on CUDA
# that produces all-NaN vectors when short and long sequences are batched
# together — reproduced cleanly (8 mixed-length docs → 6/8 NaN, same 8
# one-at-a-time → 0 NaN). batch_size=1 workaround costs 5-10× throughput
# for correctness, which isn't worth the quality delta. Arctic-embed-l
# via fastembed's TextEmbedding path is NaN-free, no custom ORT
# wrangling, 1024-dim so ChromaDB schema is unchanged.
HF_MODEL_EMBED = "snowflake/snowflake-arctic-embed-l"
# BAAI/bge-reranker-base — picked after an A/B with
# jinaai/jina-reranker-v2-base-multilingual on the Vue 3 + JVM corpus:
# jina scored higher on "password reset" but worse on "authenticate",
# "file upload", "notification", "ticket create form" — it over-weights
# short docs with noisy imports/boilerplate. Real gains (BEIR +7) need
# mxbai-rerank-large-v2 via sentence-transformers, deferred until the
# Component embedding doc carries more semantic payload than the
# current truncated SFC.
HF_MODEL_RERANK = "BAAI/bge-reranker-base"

app = modal.App(APP_NAME)


def _prefetch_weights():
    """Run at image-build time: warm the fastembed cache for both embedder
    and reranker so container cold-starts skip the HF fetch.
    """
    import os
    os.environ.setdefault("HF_HOME", "/cache/hf")
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", "/cache/hf/hub")
    from fastembed import TextEmbedding
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    TextEmbedding(model_name=HF_MODEL_EMBED, cache_dir="/cache/fastembed")
    TextCrossEncoder(model_name=HF_MODEL_RERANK, cache_dir="/cache/fastembed")


# Base image ships CUDA 12.4 + cuDNN 9 runtime libs so onnxruntime-gpu
# can actually load CUDAExecutionProvider. debian_slim lacks libcublasLt /
# libcudnn and silently falls back to CPU — strictly worse than no-GPU.
image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04",
        add_python="3.11",
    )
    .apt_install("libgomp1")
    .pip_install(
        "onnxruntime-gpu>=1.20.0",
        "fastembed-gpu>=0.4.0",  # reranker uses fastembed.rerank.cross_encoder
        "tokenizers>=0.21",
        "huggingface-hub>=0.24",
        "numpy>=1.24",
    )
    .env({
        "HF_HOME": "/cache/hf",
        "HUGGINGFACE_HUB_CACHE": "/cache/hf/hub",
        "FASTEMBED_CACHE_PATH": "/cache/fastembed",
    })
    # Bake weights into the image — runs once per image build, not per
    # container. Uses build-time network so HF rate limits don't hit
    # cold-start latency.
    .run_function(_prefetch_weights)
    # Ship the `onelens` package itself so the container can `import
    # onelens.context.embedder` — the local ORT path this app wraps.
    .add_local_python_source("onelens")
)


@app.cls(
    image=image,
    gpu="L4",
    # Volume removed — weights now live in the image (see `_prefetch_weights`
    # above). The `onelens-models` volume was the trigger for the 9p
    # snapshot-restore failures that added 30s to every cold-start retry.
    enable_memory_snapshot=True,
    # GPU snapshot disabled — the experimental flag crashed container
    # restores with SIGSEGV (exit 139), which then fell back to full cold
    # boot and silently re-downloaded weights from HuggingFace on every
    # container. Plain CPU memory snapshot is more stable; we pay a small
    # per-cold-start CUDA-init cost (~1-2s) to avoid the segfault loop.
    scaledown_window=1800,         # 30 min idle → scale to 0 (iteration-friendly)
    max_containers=12,             # cap parallelism for bulk imports
)
class Embedder:

    # Two-phase startup, per Modal's recommendation for CPU-only memory
    # snapshots. Without `enable_gpu_snapshot`, GPU is NOT available inside
    # `@modal.enter(snap=True)` — attempting CUDA init there triggers the
    # SIGSEGV (exit 139) we observed in production logs. Split:
    #
    #   1. snap=True   — CPU-safe init (imports, not yet touched)
    #   2. snap=False  — runs AFTER snapshot restore, with GPU attached;
    #                    builds ORT session + reranker model.
    #
    # Net cold-start with weights baked into image: ~2-5s (CUDA init +
    # ORT session open), no HF download, no segfault.

    @modal.enter(snap=True)
    def _warmup_cpu(self):
        """Pre-import fastembed on CPU — no CUDA binding yet."""
        import fastembed  # noqa: F401
        import fastembed.rerank.cross_encoder  # noqa: F401

    @modal.enter(snap=False)
    def _init_gpu(self):
        """Runs after snapshot restore with GPU attached."""
        from fastembed import TextEmbedding
        from onelens.context.reranker import Reranker
        self._embedder = TextEmbedding(
            model_name=HF_MODEL_EMBED,
            cache_dir="/cache/fastembed",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self._reranker = Reranker(model_name=HF_MODEL_RERANK)
        self._reranker._ensure_loaded()

    @modal.method()
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return (N, 1024) float32 embeddings as nested lists (JSON-safe)."""
        return [v.tolist() for v in self._embedder.embed(texts)]

    @modal.method()
    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Score (query, doc) pairs; higher = more relevant.

        Returns sigmoid-normalized 0-1 probabilities. The squash now lives
        in `Reranker.score` so local and Modal paths produce the same
        range (retrieval filters on `ONELENS_MIN_RERANK_SCORE=0.02`
        assuming 0-1). This wrapper is a plain passthrough.
        """
        return self._reranker.score(query, documents)


# Heartbeat is DISABLED by default. Pinging every 5 min with a 600s
# scaledown window keeps one L4 alive 24/7 = ~$19/day = ~$576/mo. That's
# the exact cost we designed snapshots to avoid.
#
# Enable manually ONLY when you want workday-warm behavior. Cron below
# pings every 5 min, Mon-Fri, 9-17 UTC — ~$6/workday.
#
# @app.function(image=image, schedule=modal.Cron("*/5 9-17 * * 1-5"))
# def heartbeat():
#     Embedder().embed.remote(["ping"])
 