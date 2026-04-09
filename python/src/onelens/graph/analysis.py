"""High-level impact analysis functions."""

from onelens.graph.db import GraphDB
from onelens.graph import queries


def get_blast_radius(db: GraphDB, file_path: str) -> list[dict]:
    """Get all code affected by changes to a file."""
    return db.query(queries.blast_radius(file_path))


def get_callers(db: GraphDB, method_fqn: str, depth: int = 2) -> list[dict]:
    """Get all callers of a method."""
    return db.query(queries.find_callers(method_fqn, depth))


def get_callees(db: GraphDB, method_fqn: str, depth: int = 2) -> list[dict]:
    """Get all callees of a method."""
    return db.query(queries.find_callees(method_fqn, depth))
