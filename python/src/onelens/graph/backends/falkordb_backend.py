"""FalkorDB backend — requires Redis/Docker server running."""

from onelens.graph.db import GraphDB


class FalkorDBBackend(GraphDB):
    """FalkorDB server backend (Redis-based, requires Docker or standalone server)."""

    def __init__(self, host: str = "localhost", port: int = 17532, graph_name: str = "onelens"):
        from falkordb import FalkorDB

        self._db = FalkorDB(host=host, port=port)
        self._graph = self._db.select_graph(graph_name)

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        result = self._graph.query(cypher, params=params or {})
        rows = []
        if result.result_set:
            # FalkorDB header format: [[type_id, 'column_name'], ...]
            columns = [h[1] if isinstance(h, list) else h for h in result.header]
            for row in result.result_set:
                rows.append(dict(zip(columns, row)))
        return rows

    def execute(self, cypher: str, params: dict | None = None) -> None:
        self._graph.query(cypher, params=params or {})

    def clear(self) -> None:
        # Delete the whole graph key, not just nodes — this also drops FTS/vector
        # indexes. Without this, evolving the FTS schema (e.g. adding a field)
        # fails because FalkorDB silently refuses to re-create an existing index.
        try:
            self._graph.delete()
        except Exception:
            # First-time runs: graph key doesn't exist yet. DETACH DELETE is a
            # safe no-op fallback.
            self._graph.query("MATCH (n) DETACH DELETE n")
        # Re-bind the graph handle so subsequent writes land in a fresh graph.
        self._graph = self._db.select_graph(self._graph.name)

    def close(self) -> None:
        pass
