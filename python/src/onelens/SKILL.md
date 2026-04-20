---
name: "mcp_server-cli"
description: "CLI for the mcp_server MCP server. Call tools, list resources, and get prompts."
---

# mcp_server CLI

## Tool Commands

### onelens_status

Session wake-up. First tool to call in every session.

Returns capabilities + node counts so the skill's decision tree knows
which subsequent tools to invoke (semantic retrieve vs FTS search,
SQL-surface queries vs code-only, …). Works on any graph — code
graphs, Vue3 graphs, and the palace memory graph alike.

```bash
uv run --with fastmcp python cli_generated.py call-tool onelens_status --graph <value> --backend <value> --db-path <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |

### onelens_query

Run raw Cypher against any graph. Returns up to `limit` rows.

Use this for impact analysis, trace, entry-point enumeration, schema
introspection — the skill docs have ready-made patterns for each of
those. Works on code graphs and the palace memory graph uniformly.

```bash
uv run --with fastmcp python cli_generated.py call-tool onelens_query --cypher <value> --graph <value> --backend <value> --db-path <value> --limit <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--cypher` | string | yes |  |
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |
| `--limit` | integer | no |  |

### onelens_search

Name-based search across graph nodes (FTS, supports `User*`, `%auth%`).

`node_type`: one of "class", "method", "endpoint", "drawer", or "" for any.
For conceptual / natural-language questions, use `onelens_retrieve`
instead — that one reads actual code content.

```bash
uv run --with fastmcp python cli_generated.py call-tool onelens_search --term <value> --node-type <value> --graph <value> --backend <value> --db-path <value> --n-results <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--term` | string | yes |  |
| `--node-type` | string | no |  |
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |
| `--n-results` | integer | no |  |

### onelens_retrieve

Hybrid FTS + semantic retrieval with source code snippets.

Gated by `onelens_status.capabilities.has_semantic` — if false, fall back
to `onelens_search`. Returns top-K ranked hits with actual source code,
not just FQNs, so an LLM can read the methods directly.

```bash
uv run --with fastmcp python cli_generated.py call-tool onelens_retrieve --query <value> --graph <value> --n-results <value> --fanout <value> --include-snippets --include-neighbors --rerank --rerank-pool <value> --project-root <value> --backend <value> --db-path <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--query` | string | yes |  |
| `--graph` | string | no |  |
| `--n-results` | integer | no |  |
| `--fanout` | integer | no |  |
| `--include-snippets` | boolean | no |  |
| `--include-neighbors` | boolean | no |  |
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
uv run --with fastmcp python cli_generated.py call-tool onelens_import --export-path <value> --graph <value> --backend <value> --db-path <value> --clear --context
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--export-path` | string | yes |  |
| `--graph` | string | no |  |
| `--backend` | string | no |  |
| `--db-path` | string | no |  |
| `--clear` | boolean | no |  |
| `--context` | boolean | no |  |

### onelens_delta_import

Apply a delta export explicitly (bypasses the auto-detect in onelens_import).

```bash
uv run --with fastmcp python cli_generated.py call-tool onelens_delta_import --delta-path <value> --graph <value> --backend <value> --db-path <value> --context
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
uv run --with fastmcp python cli_generated.py call-tool onelens_add_drawer --wing <value> --room <value> --content <value> --source-file <value> --added-by <value> --hall <value> --kind <value> --importance <value> --fqn <value> --force
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
uv run --with fastmcp python cli_generated.py call-tool onelens_delete_drawer --drawer-id <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--drawer-id` | string | yes |  |

### onelens_check_duplicate

Semantic dedup check before `onelens_add_drawer`. Returns hits ≥ threshold.

```bash
uv run --with fastmcp python cli_generated.py call-tool onelens_check_duplicate --content <value> --threshold <value> --wing <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--content` | string | yes |  |
| `--threshold` | number | no |  |
| `--wing` | string | no | JSON string |

### onelens_kg_add

Add a temporal fact triple. Dedupes by hash(s|p|o|valid_from).

```bash
uv run --with fastmcp python cli_generated.py call-tool onelens_kg_add --subject <value> --predicate <value> --object <value> --valid-from <value> --confidence <value> --source-closet <value> --ended <value> --wing <value>
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
uv run --with fastmcp python cli_generated.py call-tool onelens_kg_invalidate --fact-id <value> --ended-at <value> --reason <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--fact-id` | string | yes |  |
| `--ended-at` | string | no | JSON string |
| `--reason` | string | no |  |

### onelens_kg_timeline

Time-bucketed view of facts touching an entity — see how knowledge evolved.

```bash
uv run --with fastmcp python cli_generated.py call-tool onelens_kg_timeline --entity <value> --predicate <value> --since <value> --until <value>
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
uv run --with fastmcp python cli_generated.py call-tool onelens_find_tunnels --wing-a <value> --wing-b <value> --threshold <value> --n-results <value>
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
uv run --with fastmcp python cli_generated.py call-tool onelens_diary_write --wing <value> --content <value> --author <value> --date <value>
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
uv run --with fastmcp python cli_generated.py call-tool onelens_diary_read --wing <value> --since <value> --until <value> --limit <value>
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
uv run --with fastmcp python cli_generated.py call-tool onelens_snapshot_publish --graph <value> --tag <value> --repo <value> --include-embeddings --sign --backend <value>
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
uv run --with fastmcp python cli_generated.py call-tool onelens_snapshots_list --graph <value> --repo <value>
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
uv run --with fastmcp python cli_generated.py call-tool onelens_snapshots_pull --graph <value> --tag <value> --repo <value> --verify
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
uv run --with fastmcp python cli_generated.py call-tool onelens_snapshot_promote --graph <value> --tag <value>
```

| Flag | Type | Required | Description |
|------|------|----------|-------------|
| `--graph` | string | yes |  |
| `--tag` | string | yes |  |

## Utility Commands

```bash
uv run --with fastmcp python cli_generated.py list-tools
uv run --with fastmcp python cli_generated.py list-resources
uv run --with fastmcp python cli_generated.py read-resource <uri>
uv run --with fastmcp python cli_generated.py list-prompts
uv run --with fastmcp python cli_generated.py get-prompt <name> [key=value ...]
```
