"""FalkorDBLite backend — embedded, no Docker, no ports."""

from pathlib import Path
from onelens.graph.db import GraphDB


class FalkorDBLiteBackend(GraphDB):
    """Embedded FalkorDB using falkordblite (subprocess-based, zero infrastructure)."""

    def __init__(self, db_path: str = "~/.onelens/graphs/default", graph_name: str = "onelens"):
        from falkordblite import FalkorDB as FalkorDBLite

        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
        self._db = FalkorDBLite(self.db_path)
        self._graph = self._db.select_graph(graph_name)

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        result = self._graph.query(cypher, params=params or {})
        rows = []
        if result.result_set:
            columns = result.header
            for row in result.result_set:
                rows.append(dict(zip(columns, row)))
        return rows

    def execute(self, cypher: str, params: dict | None = None) -> None:
        self._graph.query(cypher, params=params or {})

    def clear(self) -> None:
        self._graph.query("MATCH (n) DETACH DELETE n")

    def close(self) -> None:
        pass  # FalkorDBLite handles cleanup on GC
