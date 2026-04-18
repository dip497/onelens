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
    # EnumConstant — primary lookup by owning enum FQN for cascade-delete
    # on delta imports (`MATCH (e:EnumConstant {enumFqn: $fqn})`) plus a
    # direct `fqn` index for per-constant lookups. argList is an array
    # property; FalkorDB supports `IN` over arrays natively, no FTS needed.
    "EnumConstant_fqn": "CREATE INDEX FOR (n:EnumConstant) ON (n.fqn)",
    "EnumConstant_enumFqn": "CREATE INDEX FOR (n:EnumConstant) ON (n.enumFqn)",
    # Vue 3 — frontend nodes sharing the same graph wing with the Java backend
    # so cross-stack queries work in a single Cypher call. See bridge_http.py
    # for the `HITS` edge that links Vue ApiCall to Spring Endpoint.
    "Component": "CREATE INDEX FOR (n:Component) ON (n.filePath)",
    "Composable": "CREATE INDEX FOR (n:Composable) ON (n.fqn)",
    "Store": "CREATE INDEX FOR (n:Store) ON (n.id)",
    "Route": "CREATE INDEX FOR (n:Route) ON (n.name)",
    "ApiCall": "CREATE INDEX FOR (n:ApiCall) ON (n.fqn)",
    # Phase B2 — JS business-logic layer (plain helpers / modules).
    "JsModule": "CREATE INDEX FOR (n:JsModule) ON (n.filePath)",
    "JsFunction": "CREATE INDEX FOR (n:JsFunction) ON (n.fqn)",
    # IMPORTS_FN bridge matches `(fn:JsFunction {name, filePath})` per import
    # binding; a composite RANGE index keeps that lookup O(log N) per row.
    # Without it, tens-of-thousands of rows degrade to full JsFunction scans.
    "JsFunction_name_file": "CREATE INDEX FOR (n:JsFunction) ON (n.name, n.filePath)",
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
    # Vue 3 — name weighted highest for component queries like "TicketView"; path
    # and body caught via medium/low weights.
    "Component_name": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'Component',"
        " {field: 'name', weight: 10.0},"
        " {field: 'filePath', weight: 5.0},"
        " {field: 'body', weight: 1.0})"
    ),
    "Composable_name": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'Composable',"
        " {field: 'name', weight: 10.0},"
        " {field: 'body', weight: 1.0})"
    ),
    "Store_name": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'Store',"
        " {field: 'name', weight: 10.0},"
        " {field: 'id', weight: 8.0},"
        " {field: 'body', weight: 1.0})"
    ),
    "Route_name": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'Route',"
        " {field: 'name', weight: 10.0},"
        " {field: 'path', weight: 8.0})"
    ),
    "ApiCall_path": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'ApiCall',"
        " {field: 'path', weight: 8.0},"
        " {field: 'method', weight: 5.0})"
    ),
    "JsFunction_name": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'JsFunction',"
        " {field: 'name', weight: 10.0},"
        " {field: 'filePath', weight: 3.0},"
        " {field: 'body', weight: 1.0})"
    ),
    "JsModule_path": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'JsModule', {field: 'filePath', weight: 10.0})"
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
    "ANNOTATED_WITH": "// Class|Method|Field -[:ANNOTATED_WITH {attributes}]-> Annotation",
    # EnumConstant structural edge — Class -[:HAS_ENUM_CONSTANT]-> EnumConstant.
    # Edge has no properties; the constant node carries ordinal / args / argList.
    "HAS_ENUM_CONSTANT": "// Class -[:HAS_ENUM_CONSTANT]-> EnumConstant",
    # Spring
    "INJECTS": "// SpringBean -[:INJECTS]-> SpringBean (field_name, injection_type)",
    "HANDLES": "// Method -[:HANDLES]-> Endpoint",
    # Modules
    "MODULE_DEPENDS": "// Module -[:MODULE_DEPENDS]-> Module (scope)",
}
