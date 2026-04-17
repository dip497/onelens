"""Graph schema definitions for the OneLens knowledge graph.

Uses Cypher CREATE INDEX syntax — compatible with FalkorDB, FalkorDBLite, Neo4j, Memgraph.
"""

# Node indexes — create indexes on primary lookup fields
NODE_SCHEMA = {
    "Class": "CREATE INDEX FOR (n:Class) ON (n.fqn)",
    "Method": "CREATE INDEX FOR (n:Method) ON (n.fqn)",
    "Field": "CREATE INDEX FOR (n:Field) ON (n.fqn)",
    "SpringBean": "CREATE INDEX FOR (n:SpringBean) ON (n.name)",
    "Endpoint": "CREATE INDEX FOR (n:Endpoint) ON (n.id)",
    "Module": "CREATE INDEX FOR (n:Module) ON (n.name)",
    "Annotation": "CREATE INDEX FOR (n:Annotation) ON (n.fqn)",
}

# Full-text search indexes — FalkorDB CALL procedure syntax.
#
# Field weights (verified from docs.falkordb.com/cypher/indexing/fulltext-index):
# { field: 'x', weight: W } boosts W in the TF-IDF score for matches in that field.
# For code search, the method/class name is the most discriminative signal — weight
# it 10× over the body. Javadoc is a middle ground (docstring usually summarizes
# intent more tightly than body). Body stays at default 1.0 — it catches the long
# tail of in-body terms ("BCrypt", "shutdown hook") the name misses.
FULLTEXT_SCHEMA = {
    "Class_name": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'Class', {field: 'name', weight: 10.0})"
    ),
    "Method_name": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'Method',"
        " {field: 'name', weight: 10.0},"
        " {field: 'javadoc', weight: 3.0},"
        " {field: 'body', weight: 1.0})"
    ),
    "Endpoint_path": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'Endpoint', {field: 'path', weight: 5.0})"
    ),
}

# Relationship types — no DDL needed for FalkorDB/Neo4j (edges are schemaless)
# These are documented here for reference and used by the loader
REL_SCHEMA = {
    # Code structure
    "CALLS": "// Method -[:CALLS]-> Method (line, file_path)",
    "EXTENDS": "// Class -[:EXTENDS]-> Class",
    "IMPLEMENTS": "// Class -[:IMPLEMENTS]-> Class",
    "HAS_METHOD": "// Class -[:HAS_METHOD]-> Method",
    "HAS_FIELD": "// Class -[:HAS_FIELD]-> Field",
    "OVERRIDES": "// Method -[:OVERRIDES]-> Method",
    # Annotations
    "ANNOTATED_WITH": "// Class|Method -[:ANNOTATED_WITH]-> Annotation (params)",
    # Spring
    "INJECTS": "// SpringBean -[:INJECTS]-> SpringBean (field_name, injection_type)",
    "HANDLES": "// Method -[:HANDLES]-> Endpoint",
    # Modules
    "MODULE_DEPENDS": "// Module -[:MODULE_DEPENDS]-> Module (scope)",
}
