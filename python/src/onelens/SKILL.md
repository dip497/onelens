---
name: "mcp_server-cli"
description: "CLI for the mcp_server MCP server. Call tools, list resources, and get prompts."
---

# mcp_server CLI

## Tool Commands

### onelens_init

One-command setup: create the graph, import an export (if provided),
and verify the installation.

If [export_path] is provided, imports the JSON (full or delta — auto-detected)
into the specified graph. If not provided, just creates an empty graph and
returns status.

This is the fastest path from "just installed" to "querying my codebase":
```
onelens call-tool onelens_init \
  --export-path /tmp/exports/myproject-full.json \
  --graph myproject
```

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_init --graph <value> --backend <value> --export-path <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--export-path` | string | no | JSON string |

### onelens_status

Session wake-up. First tool to call in every session.

Returns capabilities + node counts so the skill's decision tree knows
which subsequent tools to invoke (semantic retrieve vs FTS search,
SQL-surface queries vs code-only, …). Works on any graph — code
graphs, Vue3 graphs, and the palace memory graph alike.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_status --graph <value> --backend <value> --db-path <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |

### onelens_query

Run raw Cypher queries against the code knowledge graph for graph traversal.

Use this for: impact analysis ("what breaks if I change X?"), execution
traces ("trace /api/users"), dependency chains ("who injects AuthService?"),
dead code detection, cross-stack queries (Vue to Spring via HITS edges),
entry-point enumeration, and any question about relationships between nodes.

## Graph schema — nodes

Java/Spring: Class {fqn, name, kind, filePath, superClass, packageName},
Method {fqn, name, classFqn, returnType, body, visibility, isStatic, isConstructor, external},
Field {fqn, name, type}, Endpoint {path, httpMethod}, SpringBean {name, classFqn, scope},
Module {name}, Package {name}, Annotation {fqn, name}

Vue 3: Component {fqn, name, filePath, props, emits, isTest},
Store {fqn, name, id, state, getters, actions, isTest},
Composable {fqn, name, body}, Route {name, path, fullPath},
ApiCall {method, path, callerFqn}, JsFunction {fqn, name, filePath, body},
JsModule {filePath, name}

## Graph schema — edges

CALLS (Method→Method), HAS_METHOD (Class→Method), HAS_FIELD (Class→Field),
EXTENDS (Class→Class), IMPLEMENTS (Class→Class), OVERRIDES (Method→Method),
HANDLES (Class→Endpoint), INJECTS (Class→SpringBean),
ANNOTATED_WITH (Class/Method→Annotation), READS_FIELD (Method→Field),
WRITES_FIELD (Method→Field), INSTANTIATES (Method→Class),
USES_STORE (Component→Store), USES_COMPOSABLE (Component→Composable),
CALLS_API (Component→ApiCall), DISPATCHES (Route→Component),
IMPORTS (JsModule→JsModule/JsFunction),
HITS (ApiCall→Endpoint — cross-stack: Vue API call matches Spring endpoint)

## FalkorDB Cypher rules

- No `=~` regex. Use CONTAINS, STARTS WITH, ENDS WITH.
- No variable-length paths (`[:CALLS*1..3]`). Use explicit hops.
- Properties are camelCase: fqn, filePath, classFqn, returnType.
- Always include LIMIT. Filter `WHERE n.external IS NULL` for project code only.

## Common patterns

Impact: `MATCH (caller:Method)-[:CALLS]->(t:Method) WHERE t.classFqn CONTAINS 'UserService' RETURN caller.fqn`
Trace: `MATCH (e:Endpoint {path:'/api/users'})<-[:HANDLES]-(c) MATCH (c)-[:HAS_METHOD]->(m)-[:CALLS]->(callee) RETURN callee.name`
Cross-stack: `MATCH (comp:Component)-[:CALLS_API]->(a:ApiCall)-[:HITS]->(e:Endpoint) RETURN comp.name, e.path`
Dead code: `MATCH (m:Method) WHERE m.external IS NULL AND NOT ()-[:CALLS]->(m) RETURN m.fqn`

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_query --cypher <value> --graph <value> --backend <value> --db-path <value> --limit <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--cypher` | string | yes |  |
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |
| `--limit` | integer | no |  |

### onelens_search

Search the code knowledge graph using RediSearch full-text syntax.

Searches across ALL node types (Java classes/methods/endpoints, Vue
components/stores/composables/routes, JS functions/modules) when node_type
is empty, or filters to one type when specified.

## Search syntax (RediSearch)

- Prefix: `auth*` (matches authenticate, authorize, authentication)
- Fuzzy: `%passwor%` (matches password, passwd, passw0rd)
- Union: `login|signin|authenticate` (any term)
- Phrase: `"password encryption"` (exact contiguous)
- Intersection: `password encryption` (both terms, any field)
- Wildcard: `*` (match all — use with node_type to list everything)

## node_type values

Empty string "" = search all types. Otherwise:
Java/Spring: "class", "method", "endpoint", "springbean", "field"
Vue 3: "component", "store", "composable", "route", "apicall", "jsfunction", "jsmodule"

## Scoring

Results ranked by BM25: name (10x) > javadoc/path/id (3-8x) > body (1x).

## Return format

Each result: {type, fqn, name, file} — compact, no full bodies.
Use Read tool on file to see source code.

## Examples

onelens_search("UserService", node_type="class") — find specific class
onelens_search("auth*") — all auth-related methods
onelens_search("password encryption") — methods mentioning both words
onelens_search("ticket*", node_type="component") — Vue components for tickets
onelens_search("*", node_type="store") — list all Pinia stores

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_search --query <value> --graph <value> --node-type <value> --n-results <value> --backend <value> --db-path <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--query` | string | yes |  |
| `--graph` | string | no |  |
| `--node-type` | string | no |  |
| `--n-results` | integer | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |

### onelens_retrieve

**Primary tool for natural-language search over the code graph.**
Hybrid FTS + semantic embedding + optional cross-encoder rerank.

Returns a **compact** ranked list — enough to navigate, not full bodies.
The agent then uses the built-in `Read` tool on `file_path` at the
returned line range to see the actual code. Keeps responses small
(each hit ≈ 30-50 tokens) so many candidates fit in a single call.

## Use this when

- You don't know exact file locations yet.
- The question is conceptual: *"how does X work"*, *"where is Y handled"*,
  *"which class does Z"*, *"what logs SLA breaches"*.
- You want cross-cutting code that spans multiple layers (REST → service
  → repository).

## Use something else when

- Exact name / FQN / pattern search → `onelens_search` (cheaper FTS).
- Call-graph, impact, polymorphism, inheritance → `onelens_query` (Cypher).
- Reading one specific method by FQN → `onelens_query`, then `Read` on the
  returned file_path.

## Query tips

- 5-15 tokens. One action verb + one domain term minimum.
- Describe *what the code does*, not keywords alone.
- **Good:** `"REST endpoint that creates a ticket"`,
  `"JPA query that joins users and roles"`,
  `"how remote deployment gets cancelled"`.
- **Bad:** `"ticket"` (too short), `"Foo class"` (use `onelens_search`),
  a full paragraph (signal gets diluted).

## Gated on has_semantic

Check `onelens_status.capabilities.has_semantic` first. If false, the
collection isn't embedded yet — fall back to `onelens_search` until a
sync with `context=true` has run.

## Result shape (compact)

Each hit returns:
- `fqn`: fully-qualified name
- `file_path`, `line_start`, `line_end`: navigable location
- `snippet`: first ~5 lines of the method body (enough to disambiguate)
- `score`: RRF score from FTS + semantic fusion
- `rerank_score`: cross-encoder score (0-1) when `rerank=true`
- `rank_fts`, `rank_semantic`: original per-signal ranks
- `type`: `method` | `class` | `endpoint`

**Full method bodies are NOT returned.** Use the built-in `Read` tool
with `file_path` + line range when you need the code. This keeps the
per-call token footprint small (~250 tokens for 8 hits vs ~3000 with
bodies).

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_retrieve --query <value> --graph <value> --n-results <value> --fanout <value> --rerank --rerank-pool <value> --project-root <value> --backend <value> --db-path <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--query` | string | yes |  |
| `--graph` | string | no |  |
| `--n-results` | integer | no |  |
| `--fanout` | integer | no |  |
| `--rerank` | boolean | no |  |
| `--rerank-pool` | integer | no |  |
| `--project-root` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |

### onelens_import

Import an export JSON (auto-detects full vs delta).

`context=True` also runs the ChromaDB semantic mining pass so
`onelens_retrieve` works afterwards.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_import --export-path <value> --graph <value> --backend <value> --db-path <value> --clear --context
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--export-path` | string | yes |  |
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |
| `--clear` | boolean | no |  |
| `--context` | boolean | no |  |

### onelens_reindex_semantic

Rebuild ChromaDB embeddings for an already-imported graph.

Skips the graph import step entirely. Use when:
  - `Clean Up → Reset semantic` wiped ChromaDB and you don't want to
    pay the full graph re-import cost (~5 min on big repos).
  - You swapped the embedder (Jina ↔ OpenAI) and need to re-embed in
    the new vector space; the graph itself is unchanged.

Finds the newest `<graph>-full-*.json` in `~/.onelens/exports/` and
replays `CodeMiner.mine()` against it. Requires `[context]` extras.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_reindex_semantic --graph <value> --backend <value> --db-path <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |

### onelens_delta_import

Apply a delta export explicitly (bypasses the auto-detect in onelens_import).

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_delta_import --delta-path <value> --graph <value> --backend <value> --db-path <value> --context
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--delta-path` | string | yes |  |
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |
| `--context` | boolean | no |  |

### onelens_add_drawer

Store content in a wing/room drawer. Runs embedding + dedups unless force=True.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_add_drawer --wing <value> --room <value> --content <value> --source-file <value> --added-by <value> --hall <value> --kind <value> --importance <value> --fqn <value> --force
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--wing` | string | yes |  |
| `--room` | string | yes |  |
| `--content` | string | yes |  |
| `--source-file` | string | no | JSON string |
| `--added-by` | string | no |  |
| `--hall` | string | no |  |
| `--kind` | string | no |  |
| `--importance` | number | no |  |
| `--fqn` | string | no | JSON string |
| `--force` | boolean | no |  |

### onelens_delete_drawer

Delete one drawer by id.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_delete_drawer --drawer-id <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--drawer-id` | string | yes |  |

### onelens_check_duplicate

Semantic dedup check before `onelens_add_drawer`. Returns hits ≥ threshold.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_check_duplicate --content <value> --threshold <value> --wing <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--content` | string | yes |  |
| `--threshold` | number | no |  |
| `--wing` | string | no | JSON string |

### onelens_kg_add

Add a temporal fact triple. Dedupes by hash(s|p|o|valid_from).

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_kg_add --subject <value> --predicate <value> --object <value> --valid-from <value> --confidence <value> --source-closet <value> --ended <value> --wing <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--subject` | string | yes |  |
| `--predicate` | string | yes |  |
| `--object` | string | yes |  |
| `--valid-from` | string | no | JSON string |
| `--confidence` | number | no |  |
| `--source-closet` | string | no | JSON string |
| `--ended` | string | no | JSON string |
| `--wing` | string | no |  |

### onelens_kg_invalidate

Close an existing fact by id (temporal retraction; history preserved).

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_kg_invalidate --fact-id <value> --ended-at <value> --reason <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--fact-id` | string | yes |  |
| `--ended-at` | string | no | JSON string |
| `--reason` | string | no |  |

### onelens_kg_timeline

Time-bucketed view of facts touching an entity — see how knowledge evolved.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_kg_timeline --entity <value> --predicate <value> --since <value> --until <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--entity` | string | yes |  |
| `--predicate` | string | no | JSON string |
| `--since` | string | no | JSON string |
| `--until` | string | no | JSON string |

### onelens_find_tunnels

Cross-wing semantic similarity — concepts shared across repos / subsystems.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_find_tunnels --wing-a <value> --wing-b <value> --threshold <value> --n-results <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--wing-a` | string | yes |  |
| `--wing-b` | string | yes |  |
| `--threshold` | number | no |  |
| `--n-results` | integer | no |  |

### onelens_diary_write

Append a diary entry for `wing`. WAL-backed — crash-safe.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_diary_write --wing <value> --content <value> --author <value> --date <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--wing` | string | yes |  |
| `--content` | string | yes |  |
| `--author` | string | no |  |
| `--date` | string | no | JSON string |

### onelens_diary_read

Read diary entries for a wing, optionally time-ranged.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_diary_read --wing <value> --since <value> --until <value> --limit <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--wing` | string | yes |  |
| `--since` | string | no | JSON string |
| `--until` | string | no | JSON string |
| `--limit` | integer | no |  |

### onelens_snapshot_publish

Bundle `<graph>` as `<graph>@<tag>` snapshot.

Writes an immutable tarball with bundle-internal `manifest.json`,
SHA256 checksum, and (when cosign is on PATH) a Sigstore signature.
`backend='github'` uploads to GitHub Release `<tag>` on `<repo>` and
maintains a `snapshots.json` index on the pinned `onelens-index` tag.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_snapshot_publish --graph <value> --tag <value> --repo <value> --include-embeddings --sign --backend <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | yes |  |
| `--tag` | string | yes |  |
| `--repo` | string | no | JSON string |
| `--include-embeddings` | boolean | no |  |
| `--sign` | boolean | no |  |
| `--backend` | string | no |  |

### onelens_snapshots_list

List release snapshots available for `<graph>` in GitHub `<repo>`.

Reads the `snapshots.json` asset on the pinned `onelens-index` tag —
one HTTPS GET, no pagination. Returns an empty list when the repo has
never published a snapshot.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_snapshots_list --graph <value> --repo <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | yes |  |
| `--repo` | string | yes |  |

### onelens_snapshots_pull

Download, verify, and install a release snapshot as `<graph>@<tag>`.

Authoritative SHA256 comes from the `snapshots.json` index, falling
back to the `.sha256` sidecar. Optionally cosign-verifies when the
`.sig` asset is present. Restored graph appears in subsequent
`onelens_status` calls under `--graph <graph>@<tag>`.

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_snapshots_pull --graph <value> --tag <value> --repo <value> --verify
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | yes |  |
| `--tag` | string | yes |  |
| `--repo` | string | yes |  |
| `--verify` | boolean | no |  |

### onelens_snapshot_promote

Seed the live graph from an installed `<graph>@<tag>` snapshot.

Copies the snapshot rdb + context dir into the live-graph slot,
renames the internal FalkorDB Lite graph key back to `<graph>`, and
writes `~/.onelens/graphs/<graph>/.onelens-baseline` so the next
delta sync uses the snapshot's commit SHA as the diff base
(avoiding a full reindex when onboarding from a release snapshot).

Marker is one-shot — DeltaTracker consumes and deletes it on the
next sync. Prerequisite: the snapshot is installed (via
`onelens_snapshots_pull --repo local`).

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb call-tool onelens_snapshot_promote --graph <value> --tag <value> --commit-sha <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | yes |  |
| `--tag` | string | yes |  |
| `--commit-sha` | string | no | JSON string |

## Utility Commands

```bash
uv run --with fastmcp python tmp.NWKRDSkQOb list-tools
uv run --with fastmcp python tmp.NWKRDSkQOb list-resources
uv run --with fastmcp python tmp.NWKRDSkQOb read-resource <uri>
uv run --with fastmcp python tmp.NWKRDSkQOb list-prompts
uv run --with fastmcp python tmp.NWKRDSkQOb get-prompt <name> [key=value ...]
```
