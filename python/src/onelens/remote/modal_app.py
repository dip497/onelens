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
HF_MODEL_EMBED = "onnx-community/Qwen3-Embedding-0.6B-ONNX"
HF_MODEL_RERANK = "BAAI/bge-reranker-base"

app = modal.App(APP_NAME)

# Image mirrors what `onelens[context]` would install, minus chromadb
# (Modal-side doesn't persist drawers — those stay on the client machine).
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgomp1")
    .pip_install(
        "onnxruntime-gpu>=1.20.0",
        "fastembed-gpu>=0.4.0",
        "tokenizers>=0.21",
        "huggingface-hub>=0.24",
        "numpy>=1.24",
    )
    # Ship the `onelens` package itself so the container can `import
    # onelens.context.embedder` — the local ORT path this app wraps.
    .add_local_python_source("onelens")
)

# Named volume — survives deploys, shared across containers; Modal mounts it
# at /cache/hf so HuggingFace downloads resolve once per workspace.
models_volume = modal.Volume.from_name("onelens-models", create_if_missing=True)


@app.cls(
    image=image,
    gpu="L4",
    volumes={"/cache/hf": models_volume},
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
    scaledown_window=600,         # 10 min idle → scale to 0
    max_containers=20,            # cap parallelism for bulk imports
)
class Embedder:

    @modal.enter(snap=True)
    def load(self):
        """Runs once per cold container; output is captured in the snapshot.

        Everything heavy (weight download, ORT session warm-up, tokenizer init,
        reranker load) happens here so the snapshot contains a fully ready
        pipeline. Subsequent cold starts replay from the snapshot in ~2s.
        """
        import os

        # Redirect HF cache onto the Modal volume so repeated deploys reuse
        # weights. Must be set BEFORE any HF import.
        os.environ.setdefault("HF_HOME", "/cache/hf")
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", "/cache/hf/hub")

        from onelens.context.embedder import QwenEmbedder
        from onelens.context.reranker import Reranker

        # Embedder loads ORT session on GPU (CUDA provider) + tokenizer.
        self._embedder = QwenEmbedder()
        # Reranker is lazy by default — force-load inside snapshot so the
        # first warm call doesn't pay for it.
        self._reranker = Reranker()
        self._reranker._ensure_loaded()

    @modal.method()
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return (N, 1024) float32 embeddings as nested lists (JSON-safe)."""
        vecs = self._embedder.encode(texts)
        return vecs.tolist()

    @modal.method()
    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Score (query, doc) pairs; higher = more relevant."""
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
