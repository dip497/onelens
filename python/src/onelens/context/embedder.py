"""
embedder.py — Optimized Qwen3 embedding for OneLens context graph.

Design decisions (2026-04):
- Qwen3-Embedding-0.6B (+41% accuracy over MiniLM on code queries)
- bf16 default (fp16 was actually slower on Ampere)
- max_seq_length=512 (our docs are <500 tokens; avoids padding waste)
- Flash Attention 2 when available — Qwen3 README explicitly recommends it;
  fuses the attention kernel, drops the O(S²) attention matrix, gives ~2-3×
  throughput on Ampere+ vs SDPA fallback
- torch.compile OFF by default — varied input lengths thrash recompilation
  and negate kernel wins on mixed workloads (methods, classes, endpoints)
- batch size auto-scales with VRAM (_auto_batch_size); Modal sets
  ONELENS_EMBED_BATCH to override for remote runs
- expandable_segments: prevents VRAM fragmentation on long imports
"""

import logging
import os
import time

logger = logging.getLogger(__name__)

# Prevent VRAM fragmentation from dynamic-shape torch.compile on small GPUs.
# Must be set BEFORE torch is imported for the first time.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_MAX_SEQ = 512


def _auto_batch_size() -> int:
    """Pick a batch size that fills the GPU without OOM.

    The attention cost scales as B * H * S^2 * 4B. At S=512, H=16, one sample
    costs ~16MB for attention plus activations. Empirical safe caps per tier:
        4GB (A2000, 3050 Ti): 64 — the old hardcoded default
        16GB (T4, V100):      192
        24GB (A10G, L4, 3090, 4090): 256
        40GB+ (A100, H100):   512
    Override with ONELENS_EMBED_BATCH — Modal images set this so remote runs
    don't inherit the local 4GB tuning.
    """
    override = os.environ.get("ONELENS_EMBED_BATCH")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass
    try:
        import torch
        if not torch.cuda.is_available():
            return 32
        total_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    except Exception:
        return 64
    if total_gb >= 40:
        return 512
    if total_gb >= 20:
        return 256
    if total_gb >= 14:
        return 192
    return 64


DEFAULT_BATCH = _auto_batch_size()


class QwenEmbedder:
    """Wraps SentenceTransformer with optimizations for Qwen3 on small GPUs."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str = None,
        max_seq_length: int = DEFAULT_MAX_SEQ,
        batch_size: int = DEFAULT_BATCH,
        use_compile: bool = False,           # off by default: varied shapes → recompile thrash
        attn_impl: str = None,               # "flash_attention_2" | "sdpa" | "eager"; auto if None
    ):
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_float32_matmul_precision("high")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size
        self._calls = 0

        # Flash Attention 2 — Qwen3 README explicitly recommends it; gives ~2-3×
        # throughput on Ampere+ by fusing the attention kernel and dropping the
        # O(S²) materialized attention matrix. We only enable it when the wheel
        # is importable, so CPU / non-Ampere / no-wheel paths fall back to SDPA.
        resolved_attn = attn_impl or self._pick_attn_impl()
        model_kwargs = {"attn_implementation": resolved_attn} if resolved_attn else {}

        logger.info("Loading %s on %s (attn=%s)...", model_name, self.device, resolved_attn or "sdpa")
        t0 = time.time()
        self._model = SentenceTransformer(
            model_name, device=self.device, model_kwargs=model_kwargs
        )
        self._model.max_seq_length = max_seq_length
        self._model_name = model_name
        self._attn_impl = resolved_attn or "sdpa"

        # torch.compile is OFF by default. Reason: our inputs have highly varied
        # token counts (bodies 0-512 tokens, classes <100), which either triggers
        # constant recompiles (reduce-overhead mode) or adds per-call overhead
        # that negates the kernel wins (dynamic mode). Measured net slowdown on
        # varied-batch workloads. Opt in with use_compile=True for benchmarks.
        if use_compile and self.device == "cuda":
            try:
                self._model[0].auto_model = torch.compile(
                    self._model[0].auto_model, dynamic=True
                )
                self._model.encode(["warmup"] * 4, batch_size=4, show_progress_bar=False)
                logger.info("torch.compile enabled (dynamic shapes)")
            except Exception as e:
                logger.warning("torch.compile failed, falling back: %s", e)

        logger.info("Model ready in %.1fs", time.time() - t0)

    @staticmethod
    def _pick_attn_impl() -> str | None:
        """Return 'flash_attention_2' if the wheel is available on a supported
        GPU, else None to let transformers fall back to SDPA.

        Flash Attention 2 requires CUDA + Ampere (SM80) or newer. On pre-Ampere
        cards (T4, V100) or CPU it must not be selected or the model load errors.
        """
        override = os.environ.get("ONELENS_ATTN_IMPL")
        if override:
            return override if override.lower() != "auto" else None
        try:
            import torch
            if not torch.cuda.is_available():
                return None
            # SM80+ = Ampere (A100, A10, A10G, A40, RTX 3090/A2000/A4000/A5000/A6000)
            major, minor = torch.cuda.get_device_capability(0)
            if major < 8:
                return None
        except Exception:
            return None
        try:
            import flash_attn  # noqa: F401
        except ImportError:
            return None
        return "flash_attention_2"

    def encode(self, texts: list[str], batch_size: int = None, show_progress: bool = False):
        """Encode a list of texts. Returns numpy array (N, dim)."""
        bs = batch_size or self.batch_size
        out = self._model.encode(
            texts,
            batch_size=bs,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        self._calls += 1
        # Periodically release reserved-but-unallocated blocks to fight
        # fragmentation from dynamic-shape compilation.
        if self.device == "cuda" and self._calls % 10 == 0:
            import torch
            torch.cuda.empty_cache()
        return out

    @property
    def dim(self) -> int:
        return self._model.get_sentence_embedding_dimension()

    @property
    def model_name(self) -> str:
        return self._model_name
