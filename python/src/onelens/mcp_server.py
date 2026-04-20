"""
mcp_server.py — single unified FastMCP server for OneLens.

All tools live here under the `onelens_*` prefix. There is no longer a
separate `onelens-palace` server — the palace business modules
(`onelens.palace.kg`, `onelens.palace.drawers`, `onelens.palace.diary`, …)
are imported directly and exposed here.

Design rules:
1. Single namespace. Every MCP tool is prefixed `onelens_`.
2. No pure-Cypher wrappers. If a tool is ≤10 lines of Cypher, it belongs in
   the skill as a documented pattern, not as a tool. Dedicated tools earn
   their place by doing real computation the caller can't trivially do in
   Cypher — embedding / rerank / time-bucket / cross-wing similarity.
3. `onelens_status` is the wake-up primitive. Every session starts here. It
   returns `capabilities` flags the skill's decision tree branches off of.
4. `graph` is a first-class parameter on every data tool. Same tool works
   on code graphs (`myapp`) and on the palace memory graph
   (`onelens_palace_kg`).

Run the server:
    fastmcp run onelens.mcp_server:mcp                       # stdio
    fastmcp run onelens.mcp_server:mcp --transport http --port 8765

Warm state (embedder + reranker + DB handles) is cached at module level so
long-lived HTTP servers answer in ~200 ms after the first hit.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP

# Palace business modules are imported eagerly — they're small, no model
# weights or sockets held at import time.
from onelens.palace import diary as diary_mod
from onelens.palace import drawers as drawers_mod
from onelens.palace import kg as kg_mod
from onelens.palace import tunnels as tunnels_mod

logger = logging.getLogger(__name__)


# ── Lifespan + warm state ────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Optional warm-up when daemonised; no-op in stdio one-shot mode.

    Gated by ONELENS_WARM_ON_START=1 so per-CLI-command stdio subprocesses
    don't pay the ~30s embedder load for structural queries that don't use
    it. The `onelens daemon start` command sets the env var.
    """
    if os.environ.get("ONELENS_WARM_ON_START") == "1":
        import time

        t0 = time.time()
        logger.info("Warming embedder + reranker…")
        try:
            from onelens.context.embed_backends import get_embedder

            _STATE["embedder"] = get_embedder()
            _STATE["embedder"].encode(["warmup"])
        except Exception as e:
            logger.warning("Embedder warmup failed: %s", e)
        try:
            from onelens.context.embed_backends import get_reranker

            reranker = get_reranker()
            reranker.score("warmup", ["warmup"])
            _STATE["reranker"] = reranker
        except Exception as e:
            logger.warning("Reranker warmup failed: %s", e)
        logger.info("Warm in %.1fs", time.time() - t0)
    yield
    _STATE["db_handles"].clear()


mcp = FastMCP("onelens", lifespan=lifespan)

_STATE: dict[str, Any] = {"db_handles": {}}  # (backend, graph, db_path) → GraphDB


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
        db = create_backend(backend, host="localhost", port=17532, graph_name=graph)
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


# The labels `onelens_status` probes. Order matters only for readability of
# the returned counts dict; derived flags use explicit key lookups.
_KNOWN_LABELS = [
    # Core code nodes
    "Class", "Method", "Field", "EnumConstant", "Annotation", "Module",
    # Apps + packages
    "App", "Package",
    # Spring / JPA
    "SpringBean", "SpringAutoConfig", "Endpoint",
    "JpaEntity", "JpaColumn", "JpaRepository",
    # SQL surface
    "SqlQuery", "Migration", "SqlStatement",
    # Tests
    "TestCase",
    # Vue3
    "Component", "Composable", "Store", "Route", "ApiCall",
    "JsModule", "JsFunction",
    # Memory (palace graph)
    "Wing", "Room", "Hall", "Drawer", "Concept",
]


def _probe_count(db, label: str) -> int:
    try:
        r = db.query(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        return int(r[0]["cnt"]) if r else 0
    except Exception:
        return 0


def _probe_edge_counts(db) -> dict[str, int]:
    """Return {edge_type: count} across the whole graph, sorted desc by count."""
    try:
        rows = db.query("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS cnt")
        pairs = [(row["t"], int(row["cnt"])) for row in rows]
        pairs.sort(key=lambda p: p[1], reverse=True)
        return dict(pairs)
    except Exception:
        return {}


# ── 1. Wake-up ───────────────────────────────────────────────────────────────


@mcp.tool
def onelens_status(
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordblite",
    db_path: str = "~/.onelens/graphs",
) -> dict:
    """Session wake-up. First tool to call in every session.

    Returns capabilities + node counts so the skill's decision tree knows
    which subsequent tools to invoke (semantic retrieve vs FTS search,
    SQL-surface queries vs code-only, …). Works on any graph — code
    graphs, Vue3 graphs, and the palace memory graph alike.
    """
    db = _get_db(backend, graph, db_path)
    counts = {lbl: _probe_count(db, lbl) for lbl in _KNOWN_LABELS}
    counts = {k: v for k, v in counts.items() if v > 0}  # drop empty labels from payload
    edge_counts = _probe_edge_counts(db)  # {type: count}, sorted desc

    # Semantic layer probe — ChromaDB drawer for this wing must exist.
    has_semantic = False
    try:
        from onelens.context.config import OneLensContextConfig

        cfg = OneLensContextConfig()
        ctx_path = Path(cfg.context_path(graph))
        # ChromaDB dir has a `chroma.sqlite3` when initialised.
        if (ctx_path / "chroma.sqlite3").exists():
            has_semantic = True
    except Exception:
        has_semantic = False

    capabilities = {
        "has_structural": counts.get("Class", 0) + counts.get("Method", 0) > 0,
        "has_semantic": has_semantic,
        "has_spring": counts.get("SpringBean", 0) > 0,
        "has_jpa": counts.get("JpaEntity", 0) > 0,
        "has_sql": counts.get("SqlQuery", 0) + counts.get("Migration", 0) > 0,
        "has_tests": counts.get("TestCase", 0) > 0,
        "has_vue3": counts.get("Component", 0) > 0,
        "has_memory": counts.get("Drawer", 0) + counts.get("Concept", 0) > 0,
        "has_apps": counts.get("App", 0) > 0,
    }

    total = sum(counts.values())
    payload: dict = {
        "protocol": "onelens/v1",
        "graph": graph,
        "backend": backend,
        "capabilities": capabilities,
        "counts": counts,
        "edge_counts": edge_counts,
        "total_nodes": total,
        "total_edges": sum(edge_counts.values()),
    }
    # When the requested graph is empty (or the user guessed wrong), surface the
    # full list of indexed graphs on disk so the caller can pick the right one
    # instead of inventing names.
    if total == 0:
        payload["available_graphs"] = _list_indexed_graphs(db_path)
    return payload


def _list_indexed_graphs(db_path: str) -> list[dict]:
    """Enumerate indexed graph dirs with populated rdb files (falkordblite)."""
    root = Path(db_path).expanduser()
    if not root.is_dir():
        return []
    out: list[dict] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        rdb = child / f"{child.name}.rdb"
        try:
            size = rdb.stat().st_size if rdb.exists() else 0
        except OSError:
            size = 0
        # 2 KB redislite stub → skip. Populated graphs are MB+.
        if size > 10_000:
            out.append({"graph": child.name, "rdb_bytes": size})
    return out


# ── 2. Universal Cypher ──────────────────────────────────────────────────────


@mcp.tool
def onelens_query(
    cypher: str,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordblite",
    db_path: str = "~/.onelens/graphs",
    limit: int = 100,
) -> list[dict]:
    """Run raw Cypher against any graph. Returns up to `limit` rows.

    Use this for impact analysis, trace, entry-point enumeration, schema
    introspection — the skill docs have ready-made patterns for each of
    those. Works on code graphs and the palace memory graph uniformly.
    """
    db = _get_db(backend, graph, db_path)
    result = db.query(cypher) or []
    return [
        {k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v))
         for k, v in row.items()}
        for row in result[:limit]
    ]


# ── 3. Full-text search ──────────────────────────────────────────────────────


@mcp.tool
def onelens_search(
    term: str,
    node_type: str = "",
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordblite",
    db_path: str = "~/.onelens/graphs",
    n_results: int = 50,
) -> list[dict]:
    """Name-based search across graph nodes (FTS, supports `User*`, `%auth%`).

    `node_type`: one of "class", "method", "endpoint", "drawer", or "" for any.
    For conceptual / natural-language questions, use `onelens_retrieve`
    instead — that one reads actual code content.
    """
    from onelens.graph.analysis import search_code

    db = _get_db(backend, graph, db_path)
    return search_code(db, term, node_type)[:n_results]


# ── 4. Hybrid retrieval (the headline capability) ────────────────────────────


@mcp.tool
def onelens_retrieve(
    query: str,
    graph: str = "onelens",
    n_results: int = 10,
    fanout: int = 50,
    include_snippets: bool = True,
    include_neighbors: bool = False,
    rerank: bool = True,
    rerank_pool: int = 100,
    project_root: str = "",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordblite",
    db_path: str = "~/.onelens/graphs",
) -> list[dict]:
    """Hybrid FTS + semantic retrieval with source code snippets.

    Gated by `onelens_status.capabilities.has_semantic` — if false, fall back
    to `onelens_search`. Returns top-K ranked hits with actual source code,
    not just FQNs, so an LLM can read the methods directly.
    """
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
            "fqn": h.fqn, "type": h.type,
            "score": h.score, "rerank_score": h.rerank_score,
            "file_path": h.file_path, "line_start": h.line_start, "line_end": h.line_end,
            "snippet": h.snippet, "context_text": h.context_text,
            "rank_fts": h.rank_fts, "rank_semantic": h.rank_semantic,
            "callers": h.callers, "callees": h.callees,
        }
        for h in hits
    ]


# ── 5. Imports (writes — rarely called by agents) ────────────────────────────


@mcp.tool
def onelens_import(
    export_path: str,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordblite",
    db_path: str = "~/.onelens/graphs",
    clear: bool = False,
    context: bool = False,
) -> dict:
    """Import an export JSON (auto-detects full vs delta).

    `context=True` also runs the ChromaDB semantic mining pass so
    `onelens_retrieve` works afterwards.
    """
    import json as _json

    try:
        import orjson as _orjson
        _use_orjson = True
    except ImportError:
        _orjson = None
        _use_orjson = False

    path = Path(export_path).expanduser()
    with open(path, "rb") as f:
        raw = f.read()
    header = _orjson.loads(raw) if _use_orjson else _json.loads(raw.decode("utf-8"))
    export_type = header.get("exportType", "full")
    db = _get_db(backend, graph, db_path)

    # Redirect stdout to stderr — FastMCP stdio uses stdout as the JSON-RPC
    # channel, so any `print` / `rich.Progress` in the loader pollutes it.
    with contextlib.redirect_stdout(sys.stderr):
        if export_type == "delta":
            from onelens.importer.delta_loader import DeltaLoader

            loader = DeltaLoader(db)
            stats = loader.apply_delta(path, graph_name=graph, context=context)
            return {"mode": "delta", "stats": stats}

        from onelens.importer.loader import GraphLoader

        loader = GraphLoader(db)
        if clear:
            loader.clear()
        stats = loader.load_full(path)
        result = {"mode": "full", "stats": stats}

        if context:
            from onelens.miners.code_miner import CodeMiner

            miner = CodeMiner(graph)
            result["context"] = miner.mine(path)

        return result


@mcp.tool
def onelens_delta_import(
    delta_path: str,
    graph: str = "onelens",
    backend: Literal["falkordb", "falkordblite", "neo4j"] = "falkordblite",
    db_path: str = "~/.onelens/graphs",
    context: bool = False,
) -> dict:
    """Apply a delta export explicitly (bypasses the auto-detect in onelens_import)."""
    from onelens.importer.delta_loader import DeltaLoader

    db = _get_db(backend, graph, db_path)
    loader = DeltaLoader(db)
    with contextlib.redirect_stdout(sys.stderr):
        stats = loader.apply_delta(
            Path(delta_path).expanduser(), graph_name=graph, context=context
        )
    return {"stats": stats}


# ── 6–14. Memory layer (palace) ──────────────────────────────────────────────
# These wrap palace business modules. Their logic is non-Cypher (embedding,
# similarity, time-bucketing, WAL-backed writes) so they stay dedicated tools.


@mcp.tool
def onelens_add_drawer(
    wing: str,
    room: str,
    content: str,
    source_file: str | None = None,
    added_by: str = "mcp",
    hall: str = "hall_fact",
    kind: str = "note",
    importance: float = 1.0,
    fqn: str | None = None,
    force: bool = False,
) -> dict:
    """Store content in a wing/room drawer. Runs embedding + dedups unless force=True."""
    return drawers_mod.add_drawer(
        wing=wing, room=room, content=content,
        source_file=source_file, added_by=added_by,
        hall=hall, kind=kind, importance=importance, fqn=fqn, force=force,
    )


@mcp.tool
def onelens_delete_drawer(drawer_id: str) -> dict:
    """Delete one drawer by id."""
    return drawers_mod.delete_drawer(drawer_id)


@mcp.tool
def onelens_check_duplicate(
    content: str,
    threshold: float = 0.9,
    wing: str | None = None,
) -> dict:
    """Semantic dedup check before `onelens_add_drawer`. Returns hits ≥ threshold."""
    return drawers_mod.check_duplicate(content, threshold=threshold, wing=wing)


@mcp.tool
def onelens_kg_add(
    subject: str,
    predicate: str,
    object: str,
    valid_from: str | None = None,
    confidence: float = 1.0,
    source_closet: str | None = None,
    ended: str | None = None,
    wing: str = "global",
) -> dict:
    """Add a temporal fact triple. Dedupes by hash(s|p|o|valid_from)."""
    return kg_mod.add(
        subject, predicate, object,
        valid_from=valid_from, confidence=confidence,
        source_closet=source_closet, ended=ended, wing=wing,
    )


@mcp.tool
def onelens_kg_invalidate(
    fact_id: str,
    ended_at: str | None = None,
    reason: str = "",
) -> dict:
    """Close an existing fact by id (temporal retraction; history preserved)."""
    return kg_mod.invalidate(fact_id, ended_at=ended_at, reason=reason)


@mcp.tool
def onelens_kg_timeline(
    entity: str,
    predicate: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Time-bucketed view of facts touching an entity — see how knowledge evolved."""
    return kg_mod.timeline(entity, predicate=predicate, since=since, until=until)


@mcp.tool
def onelens_find_tunnels(
    wing_a: str,
    wing_b: str,
    threshold: float = 0.7,
    n_results: int = 20,
) -> list[dict]:
    """Cross-wing semantic similarity — concepts shared across repos / subsystems."""
    return tunnels_mod.find_tunnels(
        wing_a=wing_a, wing_b=wing_b, threshold=threshold, n_results=n_results,
    )


@mcp.tool
def onelens_diary_write(
    wing: str,
    content: str,
    author: str = "mcp",
    date: str | None = None,
) -> dict:
    """Append a diary entry for `wing`. WAL-backed — crash-safe."""
    return diary_mod.write(wing=wing, content=content, author=author, date=date)


@mcp.tool
def onelens_diary_read(
    wing: str,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Read diary entries for a wing, optionally time-ranged."""
    return diary_mod.read(wing=wing, since=since, until=until, limit=limit)


# ── Release snapshots ───────────────────────────────────────────────────────


@mcp.tool
def onelens_snapshot_publish(
    graph: str,
    tag: str,
    repo: str | None = None,
    include_embeddings: bool = False,
    sign: bool = True,
    backend: Literal["local", "github"] = "local",
) -> dict:
    """Bundle `<graph>` as `<graph>@<tag>` snapshot.

    Writes an immutable tarball with bundle-internal `manifest.json`,
    SHA256 checksum, and (when cosign is on PATH) a Sigstore signature.
    `backend='github'` uploads to GitHub Release `<tag>` on `<repo>` and
    maintains a `snapshots.json` index on the pinned `onelens-index` tag.
    """
    from onelens.snapshots import publisher as _pub

    res = _pub.publish(
        graph=graph,
        tag=tag,
        repo=repo,
        include_embeddings=include_embeddings,
        sign=sign,
        backend=backend,
    )
    return {
        "bundle_path": str(res.bundle_path),
        "sha256": res.sha256,
        "signed": res.signed,
        "uploaded_url": res.uploaded_url,
        "manifest": res.manifest,
        "warnings": res.warnings,
    }


@mcp.tool
def onelens_snapshots_list(graph: str, repo: str) -> dict:
    """List release snapshots available for `<graph>` in GitHub `<repo>`.

    Reads the `snapshots.json` asset on the pinned `onelens-index` tag —
    one HTTPS GET, no pagination. Returns an empty list when the repo has
    never published a snapshot.
    """
    from onelens.snapshots import consumer as _cons

    infos = _cons.list_remote(graph, repo)
    return {
        "graph": graph,
        "repo": repo,
        "snapshots": [i.__dict__ for i in infos],
    }


@mcp.tool
def onelens_snapshots_pull(
    graph: str,
    tag: str,
    repo: str,
    verify: bool = True,
) -> dict:
    """Download, verify, and install a release snapshot as `<graph>@<tag>`.

    Authoritative SHA256 comes from the `snapshots.json` index, falling
    back to the `.sha256` sidecar. Optionally cosign-verifies when the
    `.sig` asset is present. Restored graph appears in subsequent
    `onelens_status` calls under `--graph <graph>@<tag>`.
    """
    from onelens.snapshots import consumer as _cons

    return _cons.pull(graph=graph, tag=tag, repo=repo, verify=verify)


@mcp.tool
def onelens_snapshot_promote(graph: str, tag: str) -> dict:
    """Seed the live graph from an installed `<graph>@<tag>` snapshot.

    Copies the snapshot rdb + context dir into the live-graph slot,
    renames the internal FalkorDB Lite graph key back to `<graph>`, and
    writes `~/.onelens/graphs/<graph>/.onelens-baseline` so the next
    delta sync uses the snapshot's commit SHA as the diff base
    (avoiding a full reindex when onboarding from a release snapshot).

    Marker is one-shot — DeltaTracker consumes and deletes it on the
    next sync. Prerequisite: the snapshot is installed (via
    `onelens_snapshots_pull --repo local`).
    """
    from onelens.snapshots import seed as _seed

    return _seed.promote(graph=graph, tag=tag)


# ── Entry point for `fastmcp run` and `python -m onelens.mcp_server` ─────────


if __name__ == "__main__":
    mcp.run(show_banner=False)
