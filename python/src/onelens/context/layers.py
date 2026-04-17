"""
layers.py — 4-Layer Context Stack for OneLens
================================================

Load only what you need, when you need it.

    Layer 0: Project Identity    (~100 tokens)  — Always loaded. Graph stats + key services.
    Layer 1: Key Code Elements   (~800 tokens)  — Always loaded. Top methods by importance.
    Layer 2: Package Recall      (~200-500 each) — Loaded when a specific package comes up.
    Layer 3: Deep Semantic Search (unlimited)    — Full ChromaDB semantic search.

Wake-up cost: ~900 tokens (L0+L1). Leaves 95%+ of context free.

Adapted from MemPalace's layers.py for engineering context.
"""

from collections import defaultdict
from pathlib import Path

from .config import OneLensContextConfig, DEFAULT_COLLECTION_NAME
from .palace import get_collection as _get_collection
from .searcher import build_where_filter


# ---------------------------------------------------------------------------
# Layer 0 — Project Identity
# ---------------------------------------------------------------------------


class Layer0:
    """
    ~100 tokens. Always loaded.
    Generates project overview from FalkorDB stats or ChromaDB metadata.
    """

    def __init__(self, graph_name: str, db=None):
        self.graph_name = graph_name
        self.db = db

    def render(self) -> str:
        """Return project identity string."""
        parts = [f"## L0 — PROJECT IDENTITY\nGraph: {self.graph_name}"]

        # Try FalkorDB stats if available
        if self.db:
            try:
                stats = self._get_falkordb_stats()
                if stats:
                    parts.append(stats)
                    return "\n".join(parts)
            except Exception:
                pass

        # Fallback: ChromaDB metadata
        try:
            config = OneLensContextConfig()
            col = _get_collection(config.context_path(self.graph_name), create=False)
            count = col.count()
            parts.append(f"Context drawers: {count}")

            # Count by type
            type_counts = defaultdict(int)
            offset = 0
            while offset < min(count, 5000):
                batch = col.get(limit=1000, offset=offset, include=["metadatas"])
                if not batch.get("metadatas"):
                    break
                for m in batch["metadatas"]:
                    type_counts[m.get("type", "unknown")] += 1
                offset += len(batch["metadatas"])

            if type_counts:
                counts_str = " | ".join(f"{t}: {c}" for t, c in sorted(type_counts.items()))
                parts.append(counts_str)
        except Exception:
            parts.append("(no context indexed yet)")

        return "\n".join(parts)

    def _get_falkordb_stats(self) -> str:
        """Query FalkorDB for graph stats."""
        lines = []
        # Node counts
        for label in ["Class", "Method", "Endpoint", "SpringBean"]:
            try:
                result = self.db.query(f"MATCH (n:{label}) RETURN count(n) as cnt")
                if result:
                    lines.append(f"{label}: {result[0]['cnt']}")
            except Exception:
                continue

        if not lines:
            return ""

        # Top services by fan-in
        try:
            result = self.db.query("""
                MATCH (caller:Method)-[:CALLS]->(callee:Method)<-[:HAS_METHOD]-(c:Class)
                WHERE NOT callee.external = true
                RETURN c.name as name, count(DISTINCT caller) as fanIn
                ORDER BY fanIn DESC LIMIT 5
            """)
            if result:
                top = ", ".join(f"{r['name']} ({r['fanIn']} callers)" for r in result)
                lines.append(f"Key services: {top}")
        except Exception:
            pass

        return " | ".join(lines)


# ---------------------------------------------------------------------------
# Layer 1 — Key Code Elements (top by importance)
# ---------------------------------------------------------------------------


class Layer1:
    """
    ~800 tokens. Always loaded.
    Top 15 drawers by importance score, grouped by package (room).
    """

    MAX_DRAWERS = 15
    MAX_CHARS = 3200
    MAX_SCAN = 3000

    def __init__(self, graph_name: str):
        self.graph_name = graph_name

    def generate(self) -> str:
        """Pull top drawers from ChromaDB and format as compact L1 text."""
        config = OneLensContextConfig()
        try:
            col = _get_collection(config.context_path(self.graph_name), create=False)
        except Exception:
            return "## L1 — No context found. Run: onelens import <json> --graph <name> --context"

        # Fetch drawers in batches
        docs, metas = [], []
        offset = 0
        while True:
            kwargs = {"include": ["documents", "metadatas"], "limit": 500, "offset": offset}
            try:
                batch = col.get(**kwargs)
            except Exception:
                break
            batch_docs = batch.get("documents", [])
            batch_metas = batch.get("metadatas", [])
            if not batch_docs:
                break
            docs.extend(batch_docs)
            metas.extend(batch_metas)
            offset += len(batch_docs)
            if len(docs) >= self.MAX_SCAN:
                break

        if not docs:
            return "## L1 — No context drawers yet."

        # Score by importance metadata
        scored = []
        for doc, meta in zip(docs, metas):
            importance = 0.0
            for key in ("importance", "weight"):
                val = meta.get(key)
                if val is not None:
                    try:
                        importance = float(val)
                    except (ValueError, TypeError):
                        pass
                    break
            scored.append((importance, meta, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: self.MAX_DRAWERS]

        # Group by room (package)
        by_room = defaultdict(list)
        for imp, meta, doc in top:
            room = meta.get("room", "general")
            by_room[room].append((imp, meta, doc))

        # Build compact text
        lines = ["## L1 — KEY CODE ELEMENTS"]
        total_len = 0

        for room, entries in sorted(by_room.items()):
            # Shorten package name for display
            room_short = room.split(".")[-2] + "." + room.split(".")[-1] if room.count(".") > 1 else room
            room_line = f"\n[{room_short}]"
            lines.append(room_line)
            total_len += len(room_line)

            for imp, meta, doc in entries:
                snippet = doc.strip().replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."

                entry_line = f"  - {snippet} (imp={imp})"
                if total_len + len(entry_line) > self.MAX_CHARS:
                    lines.append("  ... (more in L3 search)")
                    return "\n".join(lines)

                lines.append(entry_line)
                total_len += len(entry_line)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Layer 2 — Package Recall (filtered retrieval)
# ---------------------------------------------------------------------------


class Layer2:
    """
    ~200-500 tokens per retrieval.
    Loaded when a specific package or service area comes up.
    """

    def __init__(self, graph_name: str):
        self.graph_name = graph_name

    def retrieve(self, room: str = None, entity_type: str = None, n_results: int = 10) -> str:
        """Retrieve drawers filtered by package (room) and/or entity type."""
        config = OneLensContextConfig()
        try:
            col = _get_collection(config.context_path(self.graph_name), create=False)
        except Exception:
            return "No context found."

        where = build_where_filter(wing=self.graph_name, room=room, entity_type=entity_type)

        kwargs = {"include": ["documents", "metadatas"], "limit": n_results}
        if where:
            kwargs["where"] = where

        try:
            results = col.get(**kwargs)
        except Exception as e:
            return f"Retrieval error: {e}"

        docs = results.get("documents", [])
        metas = results.get("metadatas", [])

        if not docs:
            label = f"room={room}" if room else "all"
            return f"No drawers found for {label}."

        lines = [f"## L2 — PACKAGE RECALL ({len(docs)} drawers)"]
        for doc, meta in zip(docs[:n_results], metas[:n_results]):
            entity_type_str = meta.get("type", "?")
            fqn = meta.get("fqn", "")
            snippet = doc.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."
            lines.append(f"  [{entity_type_str}] {snippet}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Layer 3 — Deep Semantic Search
# ---------------------------------------------------------------------------


class Layer3:
    """Full semantic search via ChromaDB."""

    def __init__(self, graph_name: str):
        self.graph_name = graph_name

    def search(self, query: str, room: str = None, entity_type: str = None, n_results: int = 5) -> str:
        """Semantic search, returns formatted text."""
        config = OneLensContextConfig()
        try:
            col = _get_collection(config.context_path(self.graph_name), create=False)
        except Exception:
            return "No context found."

        where = build_where_filter(wing=self.graph_name, room=room, entity_type=entity_type)

        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = col.query(**kwargs)
        except Exception as e:
            return f"Search error: {e}"

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        if not docs:
            return f'No results found for: "{query}"'

        lines = [f'## L3 — SEARCH RESULTS for "{query}"']
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
            similarity = round(max(0.0, 1 - dist), 3)
            entity_type_str = meta.get("type", "?")
            fqn = meta.get("fqn", "")
            room_name = meta.get("room", "?")

            snippet = doc.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:297] + "..."

            lines.append(f"  [{i}] {entity_type_str} | {room_name} (sim={similarity})")
            lines.append(f"      {snippet}")
            if fqn:
                lines.append(f"      fqn: {fqn}")

        return "\n".join(lines)

    def search_raw(self, query: str, room: str = None, entity_type: str = None, n_results: int = 5) -> list:
        """Return raw dicts for programmatic use."""
        config = OneLensContextConfig()
        try:
            col = _get_collection(config.context_path(self.graph_name), create=False)
        except Exception:
            return []

        where = build_where_filter(wing=self.graph_name, room=room, entity_type=entity_type)

        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = col.query(**kwargs)
        except Exception:
            return []

        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append({
                "text": doc,
                "fqn": meta.get("fqn", ""),
                "type": meta.get("type", ""),
                "wing": meta.get("wing", ""),
                "room": meta.get("room", ""),
                "importance": meta.get("importance", 0.0),
                "similarity": round(max(0.0, 1 - dist), 3),
            })
        return hits


# ---------------------------------------------------------------------------
# ContextStack — unified interface
# ---------------------------------------------------------------------------


class ContextStack:
    """
    The full 4-layer context stack for OneLens.

        stack = ContextStack("myproject", db=falkordb_backend)
        print(stack.wake_up())              # L0 + L1 (~900 tokens)
        print(stack.recall(room="com.example.payment"))  # L2
        print(stack.search("authentication logic"))      # L3
    """

    def __init__(self, graph_name: str, db=None, config: OneLensContextConfig = None):
        self.graph_name = graph_name
        self.config = config or OneLensContextConfig()

        self.l0 = Layer0(graph_name, db=db)
        self.l1 = Layer1(graph_name)
        self.l2 = Layer2(graph_name)
        self.l3 = Layer3(graph_name)

    def wake_up(self) -> str:
        """
        Generate wake-up text: L0 (project identity) + L1 (key code elements).
        Typically ~900 tokens. Inject into AI system prompt.
        """
        parts = [self.l0.render(), "", self.l1.generate()]
        return "\n".join(parts)

    def recall(self, room: str = None, entity_type: str = None, n_results: int = 10) -> str:
        """On-demand L2 retrieval filtered by package/type."""
        return self.l2.retrieve(room=room, entity_type=entity_type, n_results=n_results)

    def search(self, query: str, room: str = None, entity_type: str = None, n_results: int = 5) -> str:
        """Deep L3 semantic search."""
        return self.l3.search(query, room=room, entity_type=entity_type, n_results=n_results)

    def status(self) -> dict:
        """Status of the context stack."""
        config = self.config
        result = {
            "graph_name": self.graph_name,
            "context_path": config.context_path(self.graph_name),
        }
        try:
            col = _get_collection(config.context_path(self.graph_name), create=False)
            result["total_drawers"] = col.count()
        except Exception:
            result["total_drawers"] = 0
        return result
