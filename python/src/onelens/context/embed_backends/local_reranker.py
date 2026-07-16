"""
local_reranker.py — BGE cross-encoder reranker via onnxruntime.

Pairs with `LocalEmbedder` to provide MRR-boosting rerank on the fully-local
retrieval path. ~280 MB, runs on the same ORT providers (TRT / CUDA / CPU),
Apache 2.0. Typical latency: ~20 ms for top-30 pairs on CUDA.

Design mirrors `LocalEmbedder`: reuse `_build_providers` + `_preload_tensorrt_libs`
so the fp16 / fp32 / cpu choice is consistent across embed and rerank. No env
flags — the presence of `tensorrt` in the venv auto-enables TRT.

Why BAAI/bge-reranker-base over mxbai-rerank-base-v1 or cross-encoder/ms-marco:
- Trained specifically on MS-MARCO + multilingual + code-adjacent pairs; small
  (278 MB) but competitive on code retrieval vs the 440 MB mxbai base.
- Already the rerank model behind the Modal backend — switching keeps
  Modal-vs-local parity on retrieval ordering.
- Exported to ONNX opset-17 by the BAAI team (no custom export needed).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import numpy as np

from .base import RerankerBase
from .local_backend import _build_providers, _download_model  # re-use

logger = logging.getLogger(__name__)

DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-base"


class LocalReranker(RerankerBase):
    """BGE cross-encoder via onnxruntime. Scores (query, doc) pairs."""

    def __init__(self, model_name: str = DEFAULT_RERANK_MODEL):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._model_name = model_name
        providers, tag = _build_providers(trt_enabled=True, cache_slug="bge-reranker-base")
        t0 = time.time()
        snapshot = _download_model(model_name)
        onnx_path = os.path.join(snapshot, "onnx", "model.onnx")
        tokenizer_path = os.path.join(snapshot, "tokenizer.json")

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(onnx_path, sess_options, providers=providers)
        self._active_provider = self._session.get_providers()[0]
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.enable_padding()
        self._tokenizer.enable_truncation(max_length=512)
        self._input_names = {inp.name for inp in self._session.get_inputs()}
        logger.info("LocalReranker ready in %.1fs (active=%s)", time.time() - t0, self._active_provider)

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        # Cross-encoder: encode (query, doc) pairs and take the logit.
        pairs = [(query, d) for d in documents]
        encs = self._tokenizer.encode_batch(pairs)
        input_ids = np.array([e.ids for e in encs], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        feed = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._input_names:
            feed["token_type_ids"] = np.array([e.type_ids for e in encs], dtype=np.int64)
        logits = self._session.run(None, feed)[0]  # (N, 1) or (N,)
        logits = logits.reshape(-1)
        # Apply sigmoid so downstream threshold math matches Modal path (0..1).
        return (1.0 / (1.0 + np.exp(-logits))).astype(np.float32).tolist()
