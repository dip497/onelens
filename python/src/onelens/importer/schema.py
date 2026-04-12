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

# Full-text search indexes — FalkorDB CALL procedure syntax
FULLTEXT_SCHEMA = {
    "Class_name": "CALL db.idx.fulltext.createNodeIndex('Class', 'name')",
    "Method_name": "CALL db.idx.fulltext.createNodeIndex('Method', 'name')",
    "Endpoint_path": "CALL db.idx.fulltext.createNodeIndex('Endpoint', 'path')",
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
