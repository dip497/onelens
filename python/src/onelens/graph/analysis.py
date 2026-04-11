"""High-level impact analysis functions."""

from onelens.graph.db import GraphDB
from onelens.graph import queries


def get_blast_radius(db: GraphDB, file_path: str) -> list[dict]:
    """Get all code affected by changes to a file."""
    cypher, params = queries.blast_radius(file_path)
    return db.query(cypher, params)


def get_callers(db: GraphDB, method_fqn: str, depth: int = 2) -> list[dict]:
    """Get all callers of a method."""
    cypher, params = queries.find_callers(method_fqn, depth)
    return db.query(cypher, params)


def get_callees(db: GraphDB, method_fqn: str, depth: int = 2) -> list[dict]:
    """Get all callees of a method."""
    cypher, params = queries.find_callees(method_fqn, depth)
    return db.query(cypher, params)
