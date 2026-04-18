"""
embedder.py — Qwen3-Embedding-0.6B via onnxruntime (no torch, no fastembed).

Why direct ORT + tokenizers:
- fastembed 0.8 PoolingType has no LAST_TOKEN; Qwen3 spec requires last-token
  pooling (not MEAN/CLS). Third-party wrappers (qwen3-embed, fastembed-qwen3)
  either pin to a re-exported model or are stale.
- Direct ORT against upstream `onnx-community/Qwen3-Embedding-0.6B-ONNX` gives
  identical math to the HuggingFace reference, zero wrapper drift, ~40 LOC.

Pipeline (matches SentenceTransformer's implementation for Qwen3):
1. HuggingFace tokenizer, left-padding, pad_id=151643 (`<|endoftext|>`)
2. ONNX model emits `last_hidden_state` shape (B, T, 1024)
3. Last-token extract: with left-padding, `hidden[:, -1, :]` IS the last real
   token for every row (padding sits at the front)
4. L2 normalize → cosine-space vectors, same as before
5. 1024-dim output → existing ChromaDB drawers compatible

Model cache: fastembed/HF conventions — respects HF_HOME. First call blocks on
the 1.2 GB ONNX download via huggingface_hub.snapshot_download.

Install footprint vs old torch stack: ~300 MB (onnxruntime-gpu + tokenizers +
huggingface_hub + numpy) vs 2.5 GB (torch + sentence-transformers + deps).
"""

import logging
import os
import time

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "onnx-community/Qwen3-Embedding-0.6B-ONNX"
DEFAULT_ONNX_FILE = "onnx/model.onnx"
QWEN3_DIM = 1024
QWEN3_PAD_ID = 151643  # <|endoftext|> — same token for pad, per Qwen3 tokenizer
DEFAULT_MAX_SEQ = 512

# Qwen3-Embedding-0.6B architecture constants (from config.json).
# The ONNX export is decoder-style: it expects past_key_values inputs even
# for a single forward pass. We supply zero-length KV cache tensors per layer.
QWEN3_NUM_LAYERS = 28
QWEN3_NUM_KV_HEADS = 8
QWEN3_HEAD_DIM = 128


def _auto_batch_size() -> int:
    """Batch size sized to VRAM. Override via ONELENS_EMBED_BATCH."""
    override = os.environ.get("ONELENS_EMBED_BATCH")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        total_gb = pynvml.nvmlDeviceGetMemoryInfo(h).total / (1024 ** 3)
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


def _download_model(repo_id: str) -> str:
    """Pull the ONNX model + tokenizer from HuggingFace Hub.

    Returns the local path to the model.onnx file. Tokenizer files land
    alongside it so `Tokenizer.from_file(...)` via the snapshot dir just works.
    """
    from huggingface_hub import snapshot_download

    snapshot = snapshot_download(
        repo_id=repo_id,
        allow_patterns=[
            DEFAULT_ONNX_FILE,
            "onnx/model.onnx_data",    # weights sidecar for >2GB graphs
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "config.json",
        ],
    )
    return os.path.join(snapshot, DEFAULT_ONNX_FILE)


class QwenEmbedder:
    """Qwen3-Embedding-0.6B via onnxruntime + HuggingFace tokenizers (no torch)."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        max_seq_length: int = DEFAULT_MAX_SEQ,
        batch_size: int = DEFAULT_BATCH,
    ):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        providers, effective_device = _resolve_providers(device)
        self.device = effective_device
        self.batch_size = batch_size
        self.max_seq_length = max_seq_length
        self._model_name = model_name

        logger.info("Loading %s via onnxruntime (providers=%s)...", model_name, providers)
        t0 = time.time()
        onnx_path = _download_model(model_name)

        # ONNX session — session options keep memory bounded on long imports.
        # use_tf32=0 + deterministic compute fix the FP16 NaN drift we hit on
        # L4 during bulk imports. Documented Qwen3 ONNX bug: short token
        # sequences (header-only component docs) produced all-NaN vectors
        # under the default CUDA execution provider. Microsoft's ORT issues
        # #11384 / #15752 and the Qwen3 HF discussion (token 474 = "import"
        # → NaN on 8B model, instability on 0.6B) all point to TF32 /
        # non-deterministic math as the trigger. Forcing TF32 off and
        # turning on deterministic compute resolves the non-determinism
        # at the cost of a small throughput hit. Verified in-repo after
        # 2220/3429 drawers wrote NaN with the stock config.
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.use_deterministic_compute = True
        resolved_providers = providers
        if "CUDAExecutionProvider" in providers:
            # Provider-option types matter: ORT treats these as ints, not
            # strings. `{"use_tf32": "0"}` is silently ignored (the option
            # is parsed as the integer 1 for any non-zero / unparseable
            # value), which is how we originally hit 2220 NaN drawers
            # despite "disabling" TF32. Integer 0 is the correct disable.
            cuda_opts = {
                "device_id": 0,
                # Disable TF32 — the main suspect for non-deterministic NaN
                # on Ampere/Ada GPUs (Qwen3 ONNX FP16 bug per Microsoft
                # ORT issues #11384 / #15752 and Qwen HF discussions).
                # With TF32 off, matmul/gemm use stable FP32 math.
                "use_tf32": 0,
                # Force cuDNN to pick deterministic tensor-core algorithms
                # instead of benchmarking per call (which can select
                # different kernels between otherwise identical runs).
                "cudnn_conv_use_max_workspace": 1,
                "cudnn_conv_algo_search": "DEFAULT",
                "do_copy_in_default_stream": 1,
            }
            resolved_providers = [
                ("CUDAExecutionProvider", cuda_opts),
                "CPUExecutionProvider",
            ]
        self._session = ort.InferenceSession(onnx_path, sess_options, providers=resolved_providers)
        # The provider list we pass is an intent, not a guarantee — ORT falls
        # back to CPU if CUDAExecutionProvider fails to load (missing cuDNN 9
        # / CUDA 12 libs). Report what actually loaded so callers (UI, logs)
        # aren't lied to.
        active_providers = self._session.get_providers()
        self.device = "cuda" if "CUDAExecutionProvider" in active_providers else "cpu"
        if effective_device == "cuda" and self.device == "cpu":
            logger.warning(
                "CUDAExecutionProvider requested but failed to load; running on CPU. "
                "Install cuDNN 9 + CUDA 12 runtime libs for GPU acceleration."
            )

        # Tokenizer lives next to the ONNX file in the snapshot dir.
        tokenizer_path = os.path.join(os.path.dirname(os.path.dirname(onnx_path)), "tokenizer.json")
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        # Qwen3-Embedding pooling requires left-padding: with padding on the
        # left, `hidden[:, -1, :]` is the last real token for every row.
        # Right-padding would force us to gather by attention_mask.sum()-1.
        self._tokenizer.enable_padding(
            direction="left", pad_id=QWEN3_PAD_ID, pad_token="<|endoftext|>"
        )
        self._tokenizer.enable_truncation(max_length=max_seq_length)

        # Cache the input names — ONNX sessions re-query these on every run
        # otherwise. Output is just the first tensor (`last_hidden_state`).
        self._input_names = {inp.name for inp in self._session.get_inputs()}

        logger.info("Model ready in %.1fs", time.time() - t0)

    def encode(
        self,
        texts: list[str],
        batch_size: int | None = None,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode texts → (N, dim) numpy array, L2-normalized.

        Sorts by length before batching. Left-padding + attention over
        heavily-padded positions triggers Qwen3 ONNX NaN when a short
        sequence sits next to a long one in the same batch (dogfood
        reproduced: 8 docs batched together → 6/8 NaN; same 8 docs
        embedded individually → 0 NaN). Length-sorted batches keep the
        pad ratio low per batch and eliminate the NaN path without
        sacrificing throughput.
        """
        if not texts:
            return np.empty((0, QWEN3_DIM), dtype=np.float32)

        bs = batch_size or self.batch_size
        # Sort by character length (good proxy for token length). Track
        # original indices so we can restore output order.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        sorted_texts = [texts[i] for i in order]

        sorted_vecs: list[np.ndarray] = []
        for start in range(0, len(sorted_texts), bs):
            chunk = sorted_texts[start:start + bs]
            sorted_vecs.append(self._encode_batch(chunk))
        sorted_array = np.concatenate(sorted_vecs, axis=0)

        # Invert the permutation so results line up with the input order.
        out = np.empty_like(sorted_array)
        for new_pos, orig_i in enumerate(order):
            out[orig_i] = sorted_array[new_pos]
        return out

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        encs = self._tokenizer.encode_batch(texts)
        input_ids = np.array([e.ids for e in encs], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        batch_size, seq_len = input_ids.shape

        feed = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "position_ids" in self._input_names:
            feed["position_ids"] = np.broadcast_to(
                np.arange(seq_len, dtype=np.int64), input_ids.shape
            ).copy()

        # Qwen3 ONNX export is decoder-style: requires 2*N_LAYERS past_kv
        # inputs. For single-pass feature extraction we pass zero-length KV
        # tensors (past_seq = 0). Shape: (B, num_kv_heads, 0, head_dim).
        empty_kv = np.zeros(
            (batch_size, QWEN3_NUM_KV_HEADS, 0, QWEN3_HEAD_DIM), dtype=np.float32
        )
        for layer in range(QWEN3_NUM_LAYERS):
            feed[f"past_key_values.{layer}.key"] = empty_kv
            feed[f"past_key_values.{layer}.value"] = empty_kv

        # Only request last_hidden_state; present_kv outputs are discarded.
        outputs = self._session.run(["last_hidden_state"], feed)
        hidden = outputs[0]  # (B, T, 1024)

        # Left-padding → last token is always hidden[:, -1, :].
        last_token = hidden[:, -1, :].astype(np.float32)

        # L2 normalize → cosine-space vectors.
        norms = np.linalg.norm(last_token, axis=1, keepdims=True)
        norms = np.where(norms == 0.0, 1.0, norms)
        return last_token / norms

    @property
    def dim(self) -> int:
        return QWEN3_DIM

    @property
    def model_name(self) -> str:
        return self._model_name
