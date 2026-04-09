"""MCP server exposing OneLens knowledge graph to AI tools."""

from fastmcp import FastMCP
from onelens.graph.db import GraphDB
from onelens.graph import queries


def create_server(db: GraphDB) -> FastMCP:
    mcp = FastMCP("onelens")

    @mcp.tool()
    def query_graph(cypher: str) -> list:
        """Execute a Cypher query against the code knowledge graph."""
        return db.query(cypher)

    @mcp.tool()
    def find_callers(method_fqn: str, depth: int = 2) -> list:
        """Find all methods that call the given method (transitive)."""
        return db.query(queries.find_callers(method_fqn, depth))

    @mcp.tool()
    def find_callees(method_fqn: str, depth: int = 2) -> list:
        """Find all methods called by the given method (transitive)."""
        return db.query(queries.find_callees(method_fqn, depth))

    @mcp.tool()
    def blast_radius(file_path: str) -> list:
        """Find all code affected by changes to a file."""
        return db.query(queries.blast_radius(file_path))

    @mcp.tool()
    def find_class(name: str) -> list:
        """Search for classes by name pattern."""
        return db.query(f"MATCH (c:Class) WHERE c.name CONTAINS '{name}' RETURN c.fqn, c.kind, c.file_path LIMIT 20")

    @mcp.tool()
    def endpoint_trace(path: str) -> list:
        """Trace HTTP endpoint through controller -> service -> repository."""
        return db.query(queries.endpoint_trace(path))

    @mcp.tool()
    def unused_code() -> list:
        """List methods that are never called."""
        return db.query("MATCH (m:Method) WHERE NOT EXISTS { MATCH ()-[:CALLS]->(m) } AND m.name <> '<init>' RETURN m.fqn, m.class_fqn, m.file_path LIMIT 50")

    return mcp
