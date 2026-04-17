"""
mcp_server.py — FastMCP v3 server exposing all OneLens operations as tools.

This is the single source of truth for the CLI and for MCP agents. The
companion CLI (`cli_generated.py`) is auto-generated from this server's tool
schemas via `fastmcp generate-cli mcp_server.py cli_generated.py`.

Run the server (HTTP mode, serves both CLI and agents):
    fastmcp run onelens.mcp_server:mcp --transport http --port 8765

Run as stdio (one-shot, used by generated CLI when no daemon is up):
    fastmcp run onelens.mcp_server:mcp

Warm-path note: models (Qwen3 embedder, mxbai reranker) and graph DB handles
are cached at module level. In HTTP mode, first request triggers load; every
subsequent request is ~200ms.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Warm embedder + reranker on startup when running as a long-lived daemon.

    Gated by ONELENS_WARM_ON_START=1 so one-shot stdio subprocesses (used by
    the generated CLI per call) don't pay the ~30s load tax for structural
    commands that never touch embeddings. The daemon (`onelens daemon start`)
    sets this env so `retrieve` / `search --semantic` are warm.
    """
    if os.environ.get("ONELENS_WARM_ON_START") == "1":
        import time

        t0 = time.time()
        logger.info("Warming embedder + reranker...")
        try:
            # Factory picks the configured backend (Modal / OpenAI-compat).
            from onelens.context.embed_backends import get_embedder

            _STATE["embedder"] = get_embedder()
            _STATE["embedder"].encode(["warmup"])
        except Exception as e:
            logger.warning("Embedder warmup failed: %s", e)
        try:
            from onelens.context.embed_backends import get_reranker

            reranker = get_reranker()
            # Cheap no-op score call — trips a cold start once but keeps the
            # rerank container mapped for the first real query.
            reranker.score("warmup", ["warmup"])
            _STATE["reranker"] = reranker
        except Exception as e:
            logger.warning("Reranker warmup failed: %s", e)
        logger.info("Warm in %.1fs", time.time() - t0)
    yield
    _STATE["db_handles"].clear()


mcp = FastMCP("onelens", lifespan=lifespan)

# ── Module-level warm state ──────────────────────────────────────────────────

_STATE: dict[str, Any] = {
    "db_handles": {},  # (backend, graph, db_path) -> GraphDB
}


def _get_db(backend: str, graph: str, db_path: str):
    """Cache one GraphDB per (backend, graph, db_path) tuple."""
    key = (backend, graph, db_path)
    cache = _STATE["db_handles"]
    if key in cache:
        return cache[key]

    from onelens.graph.db import create_backend

    if backend == "falkordblite":
        db = create_backend(
            backend,
            db_path=str(Path(db_path).expanduser() / graph),
            graph_name=graph,
        )
    elif backend == "falkordb":
        db = create_backend(
            backend, host="localhost", port=17532, graph_name=graph
        )
    elif backend == "neo4j":
        db = create_backend(backend, uri="bolt://localhost:7687")
    else:
        db = create_backend(
            backend,
            db_path=str(Path(db_path).expanduser() / graph),
            graph_name=graph,
        )
    cache[key] = db
    return db


# ── Import / graph lifecycle ─────────────────────────────────────────────────


@mcp.tool
def import_graph(
    export_path: str,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
    clear: bool = False,
    context: bool = False,
) -> dict:
    """Import an export JSON (auto-detects full vs delta) into the knowledge graph.

    Set context=True to also index methods/classes into ChromaDB for semantic search.
    """
    import contextlib
    import json
    import sys

    path = Path(export_path).expanduser()
    with open(path) as f:
        header = json.load(f)
    export_type = header.get("exportType", "full")

    db = _get_db(backend, graph, db_path)

    # Redirect stdout to stderr for the whole import pass. When this tool runs
    # under FastMCP's stdio transport, stdout IS the JSON-RPC channel — every
    # `print(…)` / `rich.Progress` in the loader or miner pollutes it and
    # trips the client-side parser with errors like
    # `Invalid JSON: expected ident at line 1 column 2 …`.
    # Rich detects non-TTY and falls back to plain writes; we just need those
    # writes to land on stderr. The surfaced tool result (dict) still returns
    # over stdout via FastMCP's normal response channel.
    with contextlib.redirect_stdout(sys.stderr):
        if export_type == "delta":
            from onelens.importer.delta_loader import DeltaLoader

            loader = DeltaLoader(db)
            # Delta path delegates context mining to the loader itself — it knows
            # how to cascade-delete removed drawers and upsert only the changed
            # methods/classes via CodeMiner's deterministic IDs. Calling
            # CodeMiner.mine(path) here would be wrong: `mine` expects a full
            # export JSON shape, not a delta.
            stats = loader.apply_delta(path, graph_name=graph, context=context)
            result = {"mode": "delta", "stats": stats}
        else:
            from onelens.importer.loader import GraphLoader

            loader = GraphLoader(db)
            if clear:
                loader.clear()
            stats = loader.load_full(path)
            result = {"mode": "full", "stats": stats}

            if context:
                from onelens.miners.code_miner import CodeMiner

                miner = CodeMiner(graph)
                ctx_stats = miner.mine(path)
                result["context"] = ctx_stats

    return result


@mcp.tool
def delta_import(
    delta_path: str,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
) -> dict:
    """Apply a delta export to an existing graph."""
    from onelens.importer.delta_loader import DeltaLoader

    db = _get_db(backend, graph, db_path)
    loader = DeltaLoader(db)
    return {"stats": loader.apply_delta(Path(delta_path).expanduser())}


@mcp.tool
def stats(
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
) -> dict:
    """Return node counts per label for a graph."""
    from onelens.graph.db import NODE_TYPES

    db = _get_db(backend, graph, db_path)
    counts: dict[str, int] = {}
    for nt in NODE_TYPES:
        try:
            result = db.query(f"MATCH (n:{nt}) RETURN count(n) AS cnt")
            counts[nt] = int(result[0]["cnt"]) if result else 0
        except Exception:
            counts[nt] = 0
    return {"graph": graph, "nodes": counts, "total": sum(counts.values())}


# ── Raw query ────────────────────────────────────────────────────────────────


@mcp.tool
def query(
    cypher: str,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
    limit: int = 100,
) -> list[dict]:
    """Run a raw Cypher query. Returns up to `limit` rows."""
    db = _get_db(backend, graph, db_path)
    result = db.query(cypher) or []
    return [
        {k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v)) for k, v in row.items()}
        for row in result[:limit]
    ]


# ── Search (FTS + semantic) ──────────────────────────────────────────────────


@mcp.tool
def search(
    term: str,
    node_type: str = "",
    semantic: bool = False,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
    n_results: int = 50,
) -> list[dict]:
    """Search code by name (FTS, supports User*, %auth%1) or by meaning (semantic=True).

    node_type: one of "class", "method", "endpoint", or "" for any.
    Semantic requires the graph to have been imported with context=True (ChromaDB).
    """
    if semantic:
        from onelens.context.config import OneLensContextConfig
        from onelens.context.searcher import search_context

        config = OneLensContextConfig()
        out = search_context(
            term,
            config.context_path(graph),
            wing=graph,
            entity_type=node_type or None,
            n_results=n_results,
        )
        return out.get("results", [])

    from onelens.graph.analysis import search_code

    db = _get_db(backend, graph, db_path)
    return search_code(db, term, node_type)[:n_results]


# ── Flow trace ───────────────────────────────────────────────────────────────


@mcp.tool
def trace(
    target: str,
    entry_type: Literal["method", "endpoint"] = "method",
    depth: int = 5,
    http_method: str = "",
    include_external: bool = False,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
) -> list[dict]:
    """Trace execution flow forward from an entry point.

    target: method FQN or endpoint path. depth: 1-5.
    """
    from onelens.graph.analysis import get_endpoint_flow, get_flow_trace

    db = _get_db(backend, graph, db_path)
    if entry_type == "endpoint":
        return get_endpoint_flow(db, target, http_method, depth, include_external)
    return get_flow_trace(db, target, depth, include_external)


@mcp.tool
def entry_points(
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
) -> list[dict]:
    """List all entry points (REST endpoints, @Scheduled methods, main())."""
    from onelens.graph.analysis import get_entry_points

    db = _get_db(backend, graph, db_path)
    return get_entry_points(db)


# ── Impact ───────────────────────────────────────────────────────────────────


@mcp.tool
def impact(
    method_fqn: str,
    depth: int = 5,
    polymorphic: bool = True,
    bean_filter: bool = True,
    precise_only: bool = False,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
) -> list[dict]:
    """Find REST endpoints impacted if method_fqn changes.

    polymorphic: walk OVERRIDES for interface/template-method dispatch (default on).
    bean_filter: narrow polymorphic hits to controllers with a field of the target's type.
    precise_only: show only endpoints reached via direct CALLS edges.
    """
    from onelens.graph.analysis import get_impacted_endpoints

    db = _get_db(backend, graph, db_path)
    results = get_impacted_endpoints(
        db, method_fqn, depth, polymorphic=polymorphic, bean_type_filter=bean_filter
    )
    if precise_only:
        results = [r for r in results if r.get("precision") == "precise"]
    return results


# ── Hybrid retrieve (the headline feature) ───────────────────────────────────


@mcp.tool
def retrieve(
    query: str,
    graph: str = "onelens",
    n_results: int = 10,
    fanout: int = 50,
    include_snippets: bool = True,
    include_neighbors: bool = False,
    rerank: bool = True,
    rerank_pool: int = 100,
    project_root: str = "",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
) -> list[dict]:
    """Hybrid FTS + semantic retrieval with source code snippets (Augment-parity).

    Returns top-K ranked hits with actual source code ready for an LLM to read.
    Requires both FalkorDB (structural) and --context (ChromaDB) indexed.
    project_root can be set via ONELENS_PROJECT_ROOT env if not passed.
    """
    import os

    from onelens.context.config import OneLensContextConfig
    from onelens.context.retrieval import hybrid_retrieve

    if not project_root:
        project_root = os.environ.get("ONELENS_PROJECT_ROOT", "")

    config = OneLensContextConfig()
    db = _get_db(backend, graph, db_path)

    hits = hybrid_retrieve(
        query,
        graph=graph,
        db=db,
        context_path=config.context_path(graph),
        n_results=n_results,
        fanout=fanout,
        include_snippets=include_snippets,
        include_neighbors=include_neighbors,
        rerank=rerank,
        rerank_pool=rerank_pool,
        project_root=project_root,
    )

    return [
        {
            "fqn": h.fqn,
            "type": h.type,
            "score": h.score,
            "rerank_score": h.rerank_score,
            "file_path": h.file_path,
            "line_start": h.line_start,
            "line_end": h.line_end,
            "snippet": h.snippet,
            "context_text": h.context_text,
            "rank_fts": h.rank_fts,
            "rank_semantic": h.rank_semantic,
            "callers": h.callers,
            "callees": h.callees,
        }
        for h in hits
    ]


# ── Context subgroup (ChromaDB / memory stack) ───────────────────────────────


@mcp.tool
def context_import(export_path: str, graph: str = "onelens") -> dict:
    """Index a JSON export into ChromaDB for semantic search (standalone, no FalkorDB)."""
    from onelens.miners.code_miner import CodeMiner

    miner = CodeMiner(graph)
    return miner.mine(Path(export_path).expanduser())


@mcp.tool
def context_search(
    query: str,
    graph: str = "onelens",
    entity_type: str = "",
    room: str = "",
    n_results: int = 10,
) -> list[dict]:
    """Pure semantic search over ChromaDB (no FalkorDB).

    entity_type: one of "method", "class", "endpoint", or "" for any.
    room: Java package name filter, or "" for none.
    """
    from onelens.context.config import OneLensContextConfig
    from onelens.context.searcher import search_context

    config = OneLensContextConfig()
    out = search_context(
        query,
        config.context_path(graph),
        wing=graph,
        room=room or None,
        entity_type=entity_type or None,
        n_results=n_results,
    )
    return out.get("results", [])


@mcp.tool
def context_wakeup(
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordb",
    db_path: str = "~/.onelens/graphs",
) -> str:
    """Generate L0+L1 context (~900 tokens) for AI system prompt injection."""
    from onelens.context.layers import ContextStack

    try:
        db = _get_db(backend, graph, db_path)
    except Exception:
        db = None
    stack = ContextStack(graph, db=db)
    return stack.wake_up()


@mcp.tool
def context_recall(
    graph: str = "onelens",
    room: str = "",
    entity_type: str = "",
    n_results: int = 10,
) -> str:
    """L2 filtered retrieval by package (room) or entity type.

    entity_type: "method", "class", "endpoint", or "" for any.
    """
    from onelens.context.layers import ContextStack

    stack = ContextStack(graph)
    return stack.recall(
        room=room or None,
        entity_type=entity_type or None,
        n_results=n_results,
    )


@mcp.tool
def context_stats(graph: str = "onelens") -> dict:
    """Show context graph (ChromaDB) statistics."""
    from onelens.context.layers import ContextStack

    stack = ContextStack(graph)
    return stack.status()


# ── Entry point for `fastmcp run` and `python -m onelens.mcp_server` ─────────

if __name__ == "__main__":
    mcp.run(show_banner=False)
