"""Store facade: FalkorDB handles + Chroma collections per wing + embedder/reranker singletons."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .paths import CONTEXT_BASE, GRAPHS_BASE, KG_GRAPH_NAME

logger = logging.getLogger(__name__)

_STATE: dict[str, Any] = {
    "db_handles": {},  # wing -> GraphDB
    "kg_db": None,
    "embedder": None,
    "reranker": None,
    "chroma_cache": {},  # wing -> chromadb.Collection
}


def default_backend() -> str:
    return os.environ.get("ONELENS_BACKEND", "falkordb")


def get_graph_db(wing: str):
    """GraphDB for a code wing."""
    key = (default_backend(), wing)
    cache = _STATE["db_handles"]
    if key in cache:
        return cache[key]
    from onelens.graph.db import create_backend

    backend = default_backend()
    if backend == "falkordb":
        db = create_backend(backend, host="localhost", port=17532, graph_name=wing)
    else:
        db = create_backend(backend, db_path=str(GRAPHS_BASE / wing), graph_name=wing)
    cache[key] = db
    return db


def get_kg_db():
    """Dedicated FalkorDB graph for Palace Entity/ASSERTS triples."""
    if _STATE["kg_db"] is None:
        from onelens.graph.db import create_backend

        backend = default_backend()
        if backend == "falkordb":
            _STATE["kg_db"] = create_backend(
                backend, host="localhost", port=17532, graph_name=KG_GRAPH_NAME
            )
        else:
            _STATE["kg_db"] = create_backend(
                backend,
                db_path=str(GRAPHS_BASE / KG_GRAPH_NAME),
                graph_name=KG_GRAPH_NAME,
            )
    return _STATE["kg_db"]


def get_chroma_collection(wing: str):
    """Per-wing ChromaDB collection (matches miner layout ~/.onelens/context/<wing>/)."""
    if wing in _STATE["chroma_cache"]:
        return _STATE["chroma_cache"][wing]
    from onelens.context.palace import get_collection

    path = CONTEXT_BASE / wing
    col = get_collection(str(path), create=False)
    _STATE["chroma_cache"][wing] = col
    return col


def list_context_wings() -> list[str]:
    """Wings discovered from ChromaDB context directories."""
    if not CONTEXT_BASE.exists():
        return []
    return sorted([p.name for p in CONTEXT_BASE.iterdir() if p.is_dir()])


def list_graph_wings() -> list[str]:
    """Wings discovered from FalkorDBLite graph directories."""
    if not GRAPHS_BASE.exists():
        return []
    return sorted([p.name for p in GRAPHS_BASE.iterdir() if p.is_dir()])


def all_wings(include_agents: bool = False) -> list[str]:
    wings = set(list_context_wings()) | set(list_graph_wings())
    wings.discard(KG_GRAPH_NAME)
    if not include_agents:
        wings = {w for w in wings if not w.startswith("agent:")}
    return sorted(wings)


def get_embedder():
    if _STATE["embedder"] is None:
        from onelens.context.embed_backends import get_embedder as _ge

        _STATE["embedder"] = _ge()
    return _STATE["embedder"]


def get_reranker():
    if _STATE["reranker"] is None:
        from onelens.context.embed_backends import get_reranker as _gr

        _STATE["reranker"] = _gr()
    return _STATE["reranker"]
