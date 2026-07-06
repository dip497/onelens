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
    # Component and Store merge on `fqn` ("<filePath>::<name>") — the unique
    # declaration identity. Component retains a `filePath` index for the
    # DISPATCHES edge (route.componentRef is a path, not an fqn).
    "Component_fqn": "CREATE INDEX FOR (n:Component) ON (n.fqn)",
    "Component_filePath": "CREATE INDEX FOR (n:Component) ON (n.filePath)",
    "Composable": "CREATE INDEX FOR (n:Composable) ON (n.fqn)",
    "Store_fqn": "CREATE INDEX FOR (n:Store) ON (n.fqn)",
    "Route": "CREATE INDEX FOR (n:Route) ON (n.name)",
    "ApiCall": "CREATE INDEX FOR (n:ApiCall) ON (n.fqn)",
    # Phase B2 — JS business-logic layer (plain helpers / modules).
    "JsModule": "CREATE INDEX FOR (n:JsModule) ON (n.filePath)",
    "JsFunction": "CREATE INDEX FOR (n:JsFunction) ON (n.fqn)",
    # IMPORTS_FN bridge matches `(fn:JsFunction {name, filePath})` per import
    # binding; a composite RANGE index keeps that lookup O(log N) per row.
    # Without it, tens-of-thousands of rows degrade to full JsFunction scans.
    "JsFunction_name_file": "CREATE INDEX FOR (n:JsFunction) ON (n.name, n.filePath)",
    # Next.js (P2) — App Router route tree + React components. PK RANGE index
    # per label so the loader's label-indexed edge MATCHes hit the index
    # (6000x full-scan penalty otherwise). Route already carries a `name`
    # index for the Vue path; the Next path keys on `urlPath`, so both coexist.
    "Route_urlPath": "CREATE INDEX FOR (n:Route) ON (n.urlPath)",
    "Page": "CREATE INDEX FOR (n:Page) ON (n.fqn)",
    "Layout": "CREATE INDEX FOR (n:Layout) ON (n.fqn)",
    "SpecialFile": "CREATE INDEX FOR (n:SpecialFile) ON (n.fqn)",
    "ReactComponent": "CREATE INDEX FOR (n:ReactComponent) ON (n.fqn)",
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
    # Next.js (P2) — ReactComponent mirrors the Vue Component weighting
    # (name 10x / filePath 5x / body 1x); Page indexes fqn + body.
    "ReactComponent_name": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'ReactComponent',"
        " {field: 'name', weight: 10.0},"
        " {field: 'filePath', weight: 5.0},"
        " {field: 'body', weight: 1.0})"
    ),
    "Page_fqn": (
        "CALL db.idx.fulltext.createNodeIndex("
        "'Page',"
        " {field: 'fqn', weight: 10.0},"
        " {field: 'body', weight: 1.0})"
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
    # Next.js (P2) — App Router route tree + RSC render graph
    "HAS_PAGE": "// Route -[:HAS_PAGE]-> Page",
    "HAS_LAYOUT": "// Route -[:HAS_LAYOUT]-> Layout",
    "BOUNDARY_OF": "// SpecialFile -[:BOUNDARY_OF]-> Route (loading/error/not-found/...)",
    "CHILD_OF": "// Route -[:CHILD_OF]-> Route (nearest ancestor route)",
    "RENDERS": "// Page|Layout|ReactComponent -[:RENDERS]-> ReactComponent",
}
