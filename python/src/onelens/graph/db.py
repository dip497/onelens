"""Abstract graph database interface for OneLens knowledge graph.

All backends must implement the GraphDB protocol.
Queries use Cypher — compatible with FalkorDB, FalkorDBLite, Neo4j, Memgraph.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from rich.console import Console
from rich.table import Table

# Node types used across all backends. Includes both JVM (Java / Kotlin /
# Spring Boot) and Vue 3 labels so `onelens stats` and related tooling show
# per-label counts for whichever adapter wrote the graph.
NODE_TYPES = [
    # JVM
    "Class", "Method", "Field", "SpringBean", "Endpoint", "Module", "Annotation",
    "EnumConstant",
    # Vue 3
    "Component", "Composable", "Store", "Route", "ApiCall",
    # Phase B2 — JS business-logic layer
    "JsModule", "JsFunction",
]


class GraphDB(ABC):
    """Abstract interface for graph database backends.

    All backends speak Cypher, so queries/schema are portable.
    Only connection setup and bulk loading differ per backend.
    """

    @abstractmethod
    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Execute a Cypher query and return results as list of dicts."""
        ...

    @abstractmethod
    def execute(self, cypher: str, params: dict | None = None) -> None:
        """Execute a Cypher statement (no return value)."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Delete all nodes and edges."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        ...

    def create_schema(self, node_ddls: dict[str, str], rel_ddls: dict[str, str]) -> None:
        """Create node and relationship tables/indexes. Default: execute each DDL."""
        for ddl in node_ddls.values():
            self.execute(ddl)
        for ddl in rel_ddls.values():
            self.execute(ddl)

    def print_stats(self) -> None:
        """Print node and edge counts."""
        console = Console()
        table = Table(title="Graph Statistics")
        table.add_column("Type", style="cyan")
        table.add_column("Count", style="green", justify="right")

        for nt in NODE_TYPES:
            try:
                result = self.query(f"MATCH (n:{nt}) RETURN count(n) AS cnt")
                count = result[0]["cnt"] if result else 0
                table.add_row(nt, str(count))
            except Exception:
                pass

        console.print(table)


def create_backend(backend: str = "falkordblite", **kwargs) -> GraphDB:
    """Factory function to create a graph DB backend.

    Args:
        backend: One of "falkordblite", "falkordb", "neo4j"
        **kwargs: Backend-specific arguments (db_path, host, port, etc.)

    Returns:
        A GraphDB instance.
    """
    if backend == "falkordblite":
        from onelens.graph.backends.falkordb_lite import FalkorDBLiteBackend
        return FalkorDBLiteBackend(**kwargs)
    elif backend == "falkordb":
        from onelens.graph.backends.falkordb_backend import FalkorDBBackend
        return FalkorDBBackend(**kwargs)
    elif backend == "neo4j":
        from onelens.graph.backends.neo4j_backend import Neo4jBackend
        return Neo4jBackend(**kwargs)
    else:
        raise ValueError(f"Unknown backend: {backend}. Choose: falkordblite, falkordb, neo4j")
