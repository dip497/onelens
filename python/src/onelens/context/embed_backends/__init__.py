"""Factory for embedding + rerank backends.

Read config from env vars (plugin settings populate these):
    ONELENS_EMBED_BACKEND=modal|openai
    ONELENS_RERANK_BACKEND=modal|none

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

DEFAULT_EMBED_BACKEND = "modal"
DEFAULT_RERANK_BACKEND = "modal"


def get_embedder() -> EmbedBackend:
    name = os.environ.get("ONELENS_EMBED_BACKEND", DEFAULT_EMBED_BACKEND).lower()
    if name == "modal":
        from .modal_backend import ModalEmbedder
        return ModalEmbedder()
    if name in ("openai", "openai_compat", "openai-compat"):
        from .openai_compat import OpenAICompatEmbedder
        return OpenAICompatEmbedder()
    raise ValueError(f"Unknown ONELENS_EMBED_BACKEND={name!r} (expected: modal | openai)")


def get_reranker() -> RerankBackend:
    name = os.environ.get("ONELENS_RERANK_BACKEND", DEFAULT_RERANK_BACKEND).lower()
    if name == "modal":
        from .modal_backend import ModalReranker
        return ModalReranker()
    if name in ("none", "noop", "disabled"):
        logger.info("Reranker disabled; falling back to embedding-score order.")
        return NoopReranker()
    raise ValueError(
        f"Unknown ONELENS_RERANK_BACKEND={name!r} (expected: modal | none). "
        "OpenAI has no rerank standard; set ONELENS_RERANK_BACKEND=none to skip."
    )
