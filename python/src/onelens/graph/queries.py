"""Pre-built Cypher queries for impact analysis."""


def find_callers(method_fqn: str, depth: int = 2) -> str:
    """Find all methods that call the given method (transitive)."""
    return f"""
        MATCH (target:Method {{fqn: '{method_fqn}'}})
        MATCH (caller:Method)-[:CALLS*1..{depth}]->(target)
        RETURN DISTINCT caller.fqn AS caller, caller.class_fqn AS class_name, caller.file_path AS file
    """


def find_callees(method_fqn: str, depth: int = 2) -> str:
    """Find all methods called by the given method (transitive)."""
    return f"""
        MATCH (source:Method {{fqn: '{method_fqn}'}})
        MATCH (source)-[:CALLS*1..{depth}]->(callee:Method)
        RETURN DISTINCT callee.fqn AS callee, callee.class_fqn AS class_name, callee.file_path AS file
    """


def blast_radius(file_path: str) -> str:
    """Find all code affected by changes to a file."""
    return f"""
        MATCH (m:Method) WHERE m.file_path = '{file_path}'
        MATCH (caller:Method)-[:CALLS*1..3]->(m)
        RETURN DISTINCT caller.fqn AS affected_method, caller.class_fqn AS class_name, caller.file_path AS file
        ORDER BY file
    """


def endpoint_trace(path: str) -> str:
    """Trace HTTP endpoint → controller → service → repository."""
    return f"""
        MATCH (e:Endpoint) WHERE e.path CONTAINS '{path}'
        MATCH (handler:Method)-[:HANDLES]->(e)
        MATCH (handler)-[:CALLS*1..3]->(downstream:Method)
        RETURN e.path AS endpoint, e.http_method AS method,
               handler.fqn AS handler, downstream.fqn AS downstream_method
    """
