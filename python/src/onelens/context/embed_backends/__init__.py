"""Factory for embedding + rerank backends.

Read config from env vars (plugin settings populate these):
    ONELENS_EMBED_BACKEND=modal|openai|local
    ONELENS_RERANK_BACKEND=modal|none

    # Local (onnxruntime) specific — no extra config needed; auto-picks
    # TRT fp16 / CUDA fp32 / CPU. See local_backend.py for opt-in TRT flag.

    # OpenAI-compat specific:
    ONELENS_EMBED_BASE_URL=https://api.openai.com/v1
    ONELENS_EMBED_MODEL=text-embedding-3-small
    ONELENS_EMBED_API_KEY=sk-...
    ONELENS_EMBED_DIM=1536

    # Modal specific:
    ONELENS_MODAL_APP=onelens-embed
"""

from __future__ import annotations

import logging
import os

from .base import EmbedBackend, NoopReranker, RerankerBase

logger = logging.getLogger(__name__)

# Default = local. Plugin's OneLensSettings.embedderBackend already
# defaults to "local" on first run (Phase S); the CLI / standalone MCP
# child should match so users without the IDE in the loop don't
# accidentally hit Modal cloud (which needs auth + costs $).
DEFAULT_EMBED_BACKEND = "local"
DEFAULT_RERANK_BACKEND = "local"


def get_embedder() -> EmbedBackend:
    name = os.environ.get("ONELENS_EMBED_BACKEND", DEFAULT_EMBED_BACKEND).lower()
    if name == "modal":
        from .modal_backend import ModalEmbedder
        return ModalEmbedder()
    if name in ("openai", "openai_compat", "openai-compat"):
        from .openai_compat import OpenAICompatEmbedder
        return OpenAICompatEmbedder()
    if name in ("local", "onnx", "jina-local"):
        from .local_backend import LocalEmbedder
        return LocalEmbedder()
    raise ValueError(f"Unknown ONELENS_EMBED_BACKEND={name!r} (expected: modal | openai | local)")


def get_reranker() -> RerankerBase:
    name = os.environ.get("ONELENS_RERANK_BACKEND", DEFAULT_RERANK_BACKEND).lower()
    if name == "modal":
        from .modal_backend import ModalReranker
        return ModalReranker()
    if name in ("local", "onnx"):
        from .local_reranker import LocalReranker
        return LocalReranker()
    if name == "tei":
        # Opt-in HuggingFace Text Embeddings Inference. User runs TEI
        # themselves (we don't bundle the rust install). Reranker URL
        # via ONELENS_TEI_RERANK_URL (default http://127.0.0.1:8081).
        # Embedding side already supported via ONELENS_EMBED_BACKEND=openai
        # pointed at TEI's /v1/embeddings — TEI is OpenAI-compat there.
        from .tei_backend import TEIReranker
        return TEIReranker()
    if name in ("none", "noop", "disabled"):
        logger.info("Reranker disabled; falling back to embedding-score order.")
        return NoopReranker()
    raise ValueError(
        f"Unknown ONELENS_RERANK_BACKEND={name!r} (expected: modal | local | tei | none). "
        "OpenAI has no rerank standard; set ONELENS_RERANK_BACKEND=none to skip."
    )
