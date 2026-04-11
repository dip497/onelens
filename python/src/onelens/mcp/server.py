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
        cypher, params = queries.find_callers(method_fqn, depth)
        return db.query(cypher, params)

    @mcp.tool()
    def find_callees(method_fqn: str, depth: int = 2) -> list:
        """Find all methods called by the given method (transitive)."""
        cypher, params = queries.find_callees(method_fqn, depth)
        return db.query(cypher, params)

    @mcp.tool()
    def blast_radius(file_path: str) -> list:
        """Find all code affected by changes to a file."""
        cypher, params = queries.blast_radius(file_path)
        return db.query(cypher, params)

    @mcp.tool()
    def find_class(name: str) -> list:
        """Search for classes by name pattern."""
        cypher, params = queries.find_class(name)
        return db.query(cypher, params)

    @mcp.tool()
    def endpoint_trace(path: str) -> list:
        """Trace HTTP endpoint through controller -> service -> repository."""
        cypher, params = queries.endpoint_trace(path)
        return db.query(cypher, params)

    @mcp.tool()
    def unused_code() -> list:
        """List methods that are never called."""
        cypher, params = queries.unused_methods()
        return db.query(cypher, params)

    return mcp
