"""
FalkorDBLite backend — embedded, no Docker, no network port.

What it actually is:
    The `falkordblite` pip package bundles Redis + the FalkorDB module as shared
    objects (`falkordblite.libs/`). The Python wrapper is exposed as `redislite`
    (legacy name). On `FalkorDB(...)` construction, redislite spawns a local
    Redis process that listens on a **Unix socket** (no TCP port), with FalkorDB
    already loaded. Subsequent queries go through the socket — same API as
    cloud/Docker FalkorDB; same Cypher, FTS, vector index, UNWIND batching.

Why use this:
    Zero-Docker default for OSS users. `pip install onelens` → works. The
    subprocess is managed by redislite's psutil lifecycle; it shuts down
    cleanly when the Python parent exits.

Known limits:
    - Linux + macOS only (binaries bundled, no Windows build yet upstream).
    - No built-in browser UI (FalkorDB Docker ships :3001; Lite does not).
    - Single-process — the DB lives in the spawning Python interpreter. Multi-
      terminal concurrent access must go through onelens CLI (which itself is
      short-lived per command, so in practice this is fine).

Persistence:
    Each graph gets its own `<db_path>/<graph_name>.rdb` file. Separate RDBs
    per graph keep file sizes manageable (a large project's 10k classes → ~150 MB RDB)
    and let us delete one graph's data without wiping others.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from onelens.graph.db import GraphDB

logger = logging.getLogger(__name__)


class FalkorDBLiteBackend(GraphDB):
    """Embedded FalkorDB via bundled Redis subprocess. No Docker, no TCP port."""

    def __init__(
        self,
        db_path: str = "~/.onelens/graphs/default",
        graph_name: str = "onelens",
    ):
        # Correct import: the pip package is `falkordblite` but the Python
        # module name is `redislite`. We keep the backend class name
        # `FalkorDBLiteBackend` so call sites are stable.
        try:
            from redislite.falkordb_client import FalkorDB as _FalkorDBLite
        except ImportError as e:
            raise RuntimeError(
                "falkordblite not installed. Run `pip install onelens` "
                "(it's a base dep now) or `pip install falkordblite` manually. "
                f"Original: {e}"
            ) from e

        self.db_path = str(Path(db_path).expanduser())
        self.graph_name = graph_name
        Path(self.db_path).mkdir(parents=True, exist_ok=True)

        # Persistent RDB file — one per graph so `clear()` can drop one without
        # touching the others. Without `dbfilename`, redislite picks a random
        # temp name and we'd lose data between CLI invocations.
        rdb_filename = f"{graph_name}.rdb"
        self._db = _FalkorDBLite(
            dbfilename=os.path.join(self.db_path, rdb_filename),
        )
        self._graph = self._db.select_graph(graph_name)
        logger.info(
            "FalkorDBLite ready: graph=%s dbfile=%s/%s",
            graph_name, self.db_path, rdb_filename,
        )

    # --- GraphDB interface -------------------------------------------------

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        result = self._graph.query(cypher, params=params or {})
        rows: list[dict] = []
        if result.result_set:
            columns = [h[1] if isinstance(h, list) else h for h in result.header]
            for row in result.result_set:
                rows.append(dict(zip(columns, row)))
        return rows

    def execute(self, cypher: str, params: dict | None = None) -> None:
        self._graph.query(cypher, params=params or {})

    def clear(self) -> None:
        # Mirror FalkorDBBackend.clear: drop the whole graph key so FTS +
        # vector indexes go with it. If the graph was never created this
        # batch, DETACH DELETE is a safe no-op fallback.
        try:
            self._graph.delete()
        except Exception:
            self._graph.query("MATCH (n) DETACH DELETE n")
        # Re-bind so subsequent writes land in a fresh graph handle.
        self._graph = self._db.select_graph(self.graph_name)

    def close(self) -> None:
        # redislite manages subprocess lifecycle via psutil; shutting the
        # underlying Redis client also kills the child. No-op if already dead.
        try:
            if hasattr(self._db, "connection"):
                self._db.connection.close()
        except Exception:
            pass
