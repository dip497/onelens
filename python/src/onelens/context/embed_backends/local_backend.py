"""
local_backend.py — Fully-local embeddings via ONNX Runtime.

Ships Jina Embeddings v2 base code (161M params, Apache 2.0, 768-dim, 8K
context). Same family of encoder-only transformer as bge / e5, but trained on
code and English. Runs on any NVIDIA GPU with CUDA 12 runtime or CPU.

Why this over the cloud-hosted Qwen3-Embedding-0.6B default:

- **Air-gapped installs.** Some teams ship OneLens into environments with no
  outbound egress. Qwen3 lives on HF; once downloaded it's offline, but
  Modal/OpenAI-compat backends are online-only.
- **Latency floor.** Full sync on a 100k-method repo: Qwen3 via Modal takes
  ~20 min wall time (network round-trips dominate). Local Jina-v2-code on an
  RTX A2000 Laptop hits ~7 min fp32 / ~2 min TRT fp16.
- **No per-query cost.** Modal bills per-GPU-second; local inference is free
  after the model download (~320 MB).

Provider selection is automatic and transparent:

    1. TensorrtExecutionProvider — if `tensorrt-cu12` wheel is importable
       (user opted in via the "Install TensorRT acceleration" button on the
       Semantic settings screen). LayerNorm / Reduce / Pow stay in fp32 —
       TRT's own auto-fallback — so the BF16 instability the Jina paper
       flagged is avoided.
    2. CUDAExecutionProvider — if onnxruntime-gpu loaded its CUDA .so libs
    3. CPUExecutionProvider — always works, 10-30× slower

FP16 / BF16 caveat: the Jina v2 paper reports that *BF16* training gave
"unsatisfactory" MLM/GLUE scores. FP16 inference with TensorRT keeps
LayerNorm and reductions in FP32 (TRT auto-fallback, see the
"Forcing Reduce or Pow Layers in FP32 precision" warning at load time), so
the overflow path the paper hit is avoided — but we still gate TRT on an
env flag so users can compare recall@k on their own corpus.

Config env vars (all optional):
    ONELENS_LOCAL_EMBED_MODEL   default: jinaai/jina-embeddings-v2-base-code
    ONELENS_LOCAL_EMBED_BATCH   default: 64
    ONELENS_LOCAL_EMBED_MAXLEN  default: 256
"""

from __future__ import annotations

import ctypes
import glob
import logging
import os
import time
from pathlib import Path

import numpy as np

from .base import EmbedBackend  # noqa: F401 — Protocol for typing reference

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "jinaai/jina-embeddings-v2-base-code"
JINA_DIM = 768


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if not v:
        return default
    try:
        return max(1, int(v))
    except ValueError:
        return default


def _preload_tensorrt_libs() -> bool:
    """Try to load libnvinfer* into the global scope so onnxruntime-gpu's
    TensorRT provider can find them without LD_LIBRARY_PATH surgery.

    Returns True when TensorRT is importable; False otherwise.

    The pip-installed `tensorrt-cu12` wheel ships its .so files under
    `site-packages/tensorrt_libs/`, which is not on the default loader path.
    Importing the `tensorrt` Python module runs its own loader that
    patches the path; we also `ctypes.CDLL(..., RTLD_GLOBAL)` every nv*.so
    defensively for the case where `tensorrt` is installed but its loader
    hook has been bypassed (conda envs, manual lib copies).
    """
    try:
        import tensorrt  # noqa: F401
    except Exception:
        return False
    # The wheel path differs per Python version; glob everything under
    # site-packages/tensorrt_libs as a belt-and-suspenders step.
    import sysconfig
    site_packages = sysconfig.get_paths()["purelib"]
    pattern = os.path.join(site_packages, "tensorrt_libs", "libnv*.so*")
    for so in glob.glob(pattern):
        try:
            ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
        except OSError:
            pass
    return True


def _build_providers(trt_enabled: bool, cache_slug: str = "jina-v2-code") -> tuple[list, str]:
    """Return (providers list, effective mode tag).

    `cache_slug` scopes the TRT engine cache by model — embedder and
    reranker each need their own subdir, otherwise engine files from one
    model get reused on the other (wrong graph topology → runtime errors).
    """
    try:
        import onnxruntime as ort
        ort.preload_dlls()
        available = ort.get_available_providers()
    except Exception as e:
        logger.warning("onnxruntime unavailable, falling back to CPU: %s", e)
        return (["CPUExecutionProvider"], "cpu")

    providers: list = []
    tag = "cpu"

    if trt_enabled and "TensorrtExecutionProvider" in available and _preload_tensorrt_libs():
        cache_dir = str(Path.home() / ".onelens" / "trt-cache" / cache_slug)
        os.makedirs(cache_dir, exist_ok=True)
        providers.append(
            ("TensorrtExecutionProvider", {
                "trt_fp16_enable": True,
                "trt_engine_cache_enable": True,
                "trt_engine_cache_path": cache_dir,
                # 512 MB workspace fits 4 GB consumer cards (A2000 laptop,
                # RTX 3050/4050 mobile) alongside the embedder + reranker
                # engines + activations. 2 GB was over-budget — the
                # allocator would fail for the second model on card.
                # Override via ONELENS_LOCAL_TRT_WORKSPACE_MB if needed.
                "trt_max_workspace_size": _env_int("ONELENS_LOCAL_TRT_WORKSPACE_MB", 512) * 1024 * 1024,
            }),
        )
        tag = "trt-fp16"

    if "CUDAExecutionProvider" in available:
        providers.append("CUDAExecutionProvider")
        if tag == "cpu":
            tag = "cuda-fp32"

    providers.append("CPUExecutionProvider")
    return (providers, tag)


def _download_model(repo_id: str) -> str:
    """Pull ONNX weights + tokenizer. Cached at `~/.onelens/models/<slug>`.

    Uses `local_dir` (not HF's shared cache) so the model sits next to other
    OneLens state and plugin bundles can ship it offline.
    """
    from huggingface_hub import snapshot_download
    slug = repo_id.rsplit("/", 1)[-1]
    local_dir = Path.home() / ".onelens" / "models" / slug
    return snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        allow_patterns=[
            "onnx/model.onnx",
            "tokenizer.json",
            "tokenizer_config.json",
            "config.json",
            "special_tokens_map.json",
        ],
    )


class LocalEmbedder:
    """Jina-embeddings-v2-base-code via onnxruntime (TRT/CUDA/CPU auto-pick)."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        batch_size: int | None = None,
        max_seq_length: int | None = None,
    ):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._model_name = model_name
        self.batch_size = batch_size or _env_int("ONELENS_LOCAL_EMBED_BATCH", 64)
        self.max_seq_length = max_seq_length or _env_int("ONELENS_LOCAL_EMBED_MAXLEN", 256)

        # Auto-enable TRT: if `tensorrt-cu12` is importable, the user opted in
        # via the Semantic settings screen (plugin) or manual pip install.
        # No env flag — presence of the wheel IS the opt-in signal.
        providers, tag = _build_providers(trt_enabled=True)

        t0 = time.time()
        snapshot = _download_model(model_name)
        onnx_path = os.path.join(snapshot, "onnx", "model.onnx")
        tokenizer_path = os.path.join(snapshot, "tokenizer.json")

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        logger.info("Loading %s (providers=%s, mode=%s)", model_name, [p if isinstance(p, str) else p[0] for p in providers], tag)
        self._session = ort.InferenceSession(onnx_path, sess_options, providers=providers)
        # Report what ORT actually loaded — TRT/CUDA can silently fall back.
        active = self._session.get_providers()
        if tag == "trt-fp16" and "TensorrtExecutionProvider" not in active:
            logger.warning("TRT requested but not active; running on %s", active[0])
        self._active_provider = active[0]

        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.enable_padding()
        self._tokenizer.enable_truncation(max_length=self.max_seq_length)

        self._input_names = {inp.name for inp in self._session.get_inputs()}
        logger.info("LocalEmbedder ready in %.1fs (active=%s)", time.time() - t0, self._active_provider)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, JINA_DIM), dtype=np.float32)
        out = np.empty((len(texts), JINA_DIM), dtype=np.float32)
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start:start + self.batch_size]
            out[start:start + len(chunk)] = self._encode_batch(chunk)
        return out

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        encs = self._tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encs], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feed = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.zeros_like(input_ids)
        out = self._session.run(None, feed)[0]  # (B, T, 768)
        # Mean-pool with attention mask (Jina v2 convention).
        mask = attention_mask[:, :, None].astype(np.float32)
        pooled = (out * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1.0, None)
        # L2 normalize for cosine-dot equivalence.
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.where(norms == 0.0, 1.0, norms)
        return (pooled / norms).astype(np.float32)

    @property
    def dim(self) -> int:
        return JINA_DIM

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def device(self) -> str:
        """String label used by telemetry — parallels QwenEmbedder.device.
        Maps ORT provider → 'cuda' / 'cpu'. `palace.get_embedding_device()`
        and `ChromaBackend.embedding_device` read this."""
        return "cuda" if "CUDAExecutionProvider" in self._active_provider \
            or "TensorrtExecutionProvider" in self._active_provider else "cpu"
