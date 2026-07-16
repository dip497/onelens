"""
local_backend.py — Fully-local embeddings via ONNX Runtime.

Default: Jina Embeddings v2 base code (161M params, Apache 2.0, 768-dim, 8K
context). Same family of encoder-only transformer as bge / e5, but trained on
code and English. Runs on any NVIDIA GPU with CUDA 12 runtime or CPU.

Opt-in alternatives via `ONELENS_LOCAL_EMBED_PROFILE` (or full
`ONELENS_LOCAL_EMBED_MODEL` repo id):

    PROFILE=balanced  →  jinaai/jina-embeddings-v2-base-code   (default, code-tuned)
    PROFILE=gemma     →  onnx-community/embeddinggemma-300m-ONNX
                         (300M, 768-dim, MTEB Code #1 sub-500M, q4/q8 quants
                          for CPU-only laptops; same dim as Jina so drawer
                          schema is compatible — but cosine similarities are
                          NOT comparable across models, re-mine after switch.)
    PROFILE=tiny      →  BAAI/bge-small-en-v1.5     (33M, 384-dim, CPU-fast,
                         requires fresh drawers — different dim.)

EmbeddingGemma activations don't support fp16; force fp32 (or q4/q8 quant
file via `ONELENS_LOCAL_EMBED_QUANT=q4|q8|fp32`).

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
    ONELENS_LOCAL_EMBED_MAXLEN  default: 512  (Jina v2 was trained at 512;
                                under-truncating here drops recall on
                                code bodies past ~256 tokens.)
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
# Default output dim for the shipped Jina v2 base code model. Used only as
# a placeholder before the session is loaded; `LocalEmbedder._dim` is the
# authoritative dim (probed from `session.get_outputs()[0].shape`).
DEFAULT_DIM = 768

# Profile shorthand → repo id. `ONELENS_LOCAL_EMBED_MODEL` still wins if set.
PROFILE_MODELS = {
    "balanced": "jinaai/jina-embeddings-v2-base-code",
    "gemma": "onnx-community/embeddinggemma-300m-ONNX",
    "tiny": "BAAI/bge-small-en-v1.5",
}


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


def _resolve_onnx_filename(quant: str) -> str:
    """Map quant tag → ONNX file name inside the `onnx/` subdir.

    Mirrors the onnx-community export convention (used by EmbeddingGemma,
    Qwen3, BGE — they all ship a stack of variants). Falls back to plain
    `model.onnx` for repos that only ship one file (e.g. jina-v2-base-code).
    """
    quant = (quant or "").lower()
    if quant in ("q4", "int4"):
        return "model_q4.onnx"
    if quant in ("q8", "int8"):
        return "model_quantized.onnx"
    return "model.onnx"


def _download_model(repo_id: str, quant: str = "fp32") -> tuple[str, str]:
    """Pull ONNX weights + tokenizer. Cached at `~/.onelens/models/<slug>`.

    Uses `local_dir` (not HF's shared cache) so the model sits next to other
    OneLens state and plugin bundles can ship it offline.

    Returns (snapshot_dir, onnx_file_name). The caller joins them — different
    repos use different filenames (model.onnx vs model_q4.onnx vs
    model_quantized.onnx for CPU q8 quant).

    `model.onnx_data` is the >2GB external-weights sidecar produced by
    onnx's `save_model(save_as_external_data=True)`. Without it, ORT loads
    the graph but fails at first run with "Tensor data is empty". Jina v2
    base code is small enough not to need the sidecar; EmbeddingGemma and
    Qwen3 ONNX exports DO. allow_patterns must include both forms so the
    snapshot works for either. `model_*.onnx_data` covers q4/q8 sidecars.
    """
    from huggingface_hub import snapshot_download
    slug = repo_id.rsplit("/", 1)[-1]
    local_dir = Path.home() / ".onelens" / "models" / slug
    onnx_file = _resolve_onnx_filename(quant)
    snapshot_dir = snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        allow_patterns=[
            f"onnx/{onnx_file}",
            f"onnx/{onnx_file}_data",
            "onnx/model.onnx",            # always pull base file as ORT fallback
            "onnx/model.onnx_data",
            "tokenizer.json",
            "tokenizer_config.json",
            "tokenizer.model",            # SentencePiece model (gemma)
            "config.json",
            "special_tokens_map.json",
        ],
    )
    return snapshot_dir, onnx_file


class LocalEmbedder:
    """Jina-embeddings-v2-base-code via onnxruntime (TRT/CUDA/CPU auto-pick)."""

    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int | None = None,
        max_seq_length: int | None = None,
    ):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        # Honor `ONELENS_LOCAL_EMBED_MODEL` — previously documented but
        # silently ignored because the constructor's default param value
        # short-circuited the env lookup. Allows users to swap to
        # jina-v3 / nomic-embed-code / any HF ONNX-exported encoder
        # without recompiling the plugin.
        #
        # Resolution order:
        #   1. explicit model_name kwarg
        #   2. ONELENS_LOCAL_EMBED_MODEL (full repo id, power-user knob)
        #   3. ONELENS_LOCAL_EMBED_PROFILE (shorthand: balanced|gemma|tiny)
        #   4. DEFAULT_MODEL (jina-v2-base-code)
        profile = (os.environ.get("ONELENS_LOCAL_EMBED_PROFILE") or "").lower()
        self._model_name = (
            model_name
            or os.environ.get("ONELENS_LOCAL_EMBED_MODEL")
            or PROFILE_MODELS.get(profile)
            or DEFAULT_MODEL
        )
        # Quant variant (only meaningful for repos that ship multiple
        # `onnx/model_*.onnx` files — EmbeddingGemma, Qwen3, etc.).
        # CPU-only laptops should set `ONELENS_LOCAL_EMBED_QUANT=q4` to halve
        # RAM + disk footprint at ~1pt MTEB cost.
        self._quant = (os.environ.get("ONELENS_LOCAL_EMBED_QUANT") or "fp32").lower()
        self.batch_size = batch_size or _env_int("ONELENS_LOCAL_EMBED_BATCH", 64)
        # Match Jina v2's training seq length (512). The previous 256
        # default truncated mid-method on bodies >256 tokens, masking
        # signal in the second half of code chunks.
        self.max_seq_length = max_seq_length or _env_int("ONELENS_LOCAL_EMBED_MAXLEN", 512)

        # Auto-enable TRT: if `tensorrt-cu12` is importable, the user opted in
        # via the Semantic settings screen (plugin) or manual pip install.
        # No env flag — presence of the wheel IS the opt-in signal.
        #
        # Cache slug must include the QUANT variant — TRT engines are graph-
        # specific, and {model.onnx, model_q4.onnx, model_quantized.onnx}
        # produce different graphs. Sharing one slug across quants corrupts
        # the engine cache when a user flips ONELENS_LOCAL_EMBED_QUANT
        # (silent runtime errors on second start).
        slug = self._model_name.rsplit("/", 1)[-1] + "-" + self._quant
        providers, tag = _build_providers(trt_enabled=True, cache_slug=slug)

        t0 = time.time()
        snapshot, onnx_filename = _download_model(self._model_name, self._quant)
        onnx_path = os.path.join(snapshot, "onnx", onnx_filename)
        if not os.path.exists(onnx_path):
            # Quant variant missing on the repo — fall back to fp32 graph.
            fallback = os.path.join(snapshot, "onnx", "model.onnx")
            if os.path.exists(fallback):
                logger.warning(
                    "Quant variant %s not found on %s; using fp32 model.onnx",
                    onnx_filename, self._model_name,
                )
                onnx_path = fallback
        tokenizer_path = os.path.join(snapshot, "tokenizer.json")

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        logger.info("Loading %s (providers=%s, mode=%s)", self._model_name, [p if isinstance(p, str) else p[0] for p in providers], tag)
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

        # Derive output dim from the loaded session — kills the silent
        # truncation bug where overriding ONELENS_LOCAL_EMBED_MODEL to a
        # non-768 model (jina-v3 = 1024, nomic-embed-code = 768, …)
        # produced corrupt embeddings. Token-embedding ONNX exports
        # surface as `[batch, seq, hidden]`; `hidden` is fixed in every
        # encoder we'd realistically swap to. If the export is fully
        # dynamic, probe with a 1-token input and read the result.
        out_meta = self._session.get_outputs()[0]
        last_dim = out_meta.shape[-1] if out_meta.shape else None
        if isinstance(last_dim, int) and last_dim > 0:
            self._dim = last_dim
        else:
            probe_feed = {
                "input_ids": np.zeros((1, 1), dtype=np.int64),
                "attention_mask": np.ones((1, 1), dtype=np.int64),
            }
            if "token_type_ids" in self._input_names:
                probe_feed["token_type_ids"] = np.zeros((1, 1), dtype=np.int64)
            probe_out = self._session.run(None, probe_feed)[0]
            self._dim = int(probe_out.shape[-1])
        logger.info(
            "LocalEmbedder ready in %.1fs (active=%s, dim=%d, maxlen=%d)",
            time.time() - t0, self._active_provider, self._dim, self.max_seq_length,
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dim), dtype=np.float32)
        out = np.empty((len(texts), self._dim), dtype=np.float32)
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
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def device(self) -> str:
        """String label used by telemetry — `'cuda'` or `'cpu'`.
        Maps ORT provider → 'cuda' / 'cpu'. `palace.get_embedding_device()`
        and `ChromaBackend.embedding_device` read this."""
        return "cuda" if "CUDAExecutionProvider" in self._active_provider \
            or "TensorrtExecutionProvider" in self._active_provider else "cpu"
