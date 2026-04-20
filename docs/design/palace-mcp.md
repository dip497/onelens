# Palace MCP — OneLens in MemPalace clothing

Status: plan · 2026-04-18

Parallel MCP server mimicking MemPalace's 19-tool surface, backed by OneLens's FalkorDB + ChromaDB + Qwen3 stack. Existing `mcp_server.py` untouched.

---

## 1. Taxonomy mapping (MemPalace → OneLens)

| MemPalace | OneLens meaning |
|---|---|
| Palace | whole multi-wing KB (all graphs + all Chroma collections) |
| Wing | **source scope**: repo (code), Jira project, doc folder, `agent:<name>` for diaries |
| Room | **domain slug** within wing — code: Java package; ticket: project/component; doc: top folder; diary: `diary-<topic>` |
| Hall | **semantic class**: `hall_code`, `hall_signature`, `hall_doc`, `hall_event`, `hall_fact` (replaces current fixed constant) |
| Drawer | Chroma doc (already aligned — id `method:<fqn>` etc.) |
| Tunnel | computed: same `room` in ≥2 wings |
| Triple | new: `(:Entity)-[:ASSERTS {predicate, validFrom, validTo, confidence, wing}]->(:Entity)` in same FalkorDB graph |
| Literal object | `:Entity {kind:'literal', name:<value>}` — uniform node shape |

Canonical Chroma metadata: `{wing, room, hall, fqn, type, importance, filed_at, kind, source_file, added_by}`.

---

## 2. Storage decisions (ADRs)

- **ADR-P1**: Palace KG lives in FalkorDB, not SQLite. One engine, Cypher for cross-links between facts and code nodes by shared `fqn`. Diverges from MemPalace's SQLite — justified: we already run FalkorDB.
- **ADR-P2**: `Entity.name` shares namespace with code `fqn`. No duplication; `kg_query("com.ex.Foo#bar")` pulls both hand-authored facts and structural edges.
- **ADR-P3**: `hall` becomes a taxonomy (5 values). `CodeMiner` emits split halls per drawer type. Existing full re-mine picks it up; delta path must match. LESSONS-LEARNED addendum required.
- **ADR-P4**: Tunnels computed at query time from Chroma metadata group-by. Not stored. Cost fine up to ~50 wings.
- **ADR-P5**: Temporal validity only on `ASSERTS` edges. Code edges recompute each import — not temporal.
- **ADR-P6**: Diary wings prefixed `agent:`; excluded from default `list_wings` / global search unless `include_agents=True`.
- **ADR-P7**: AAAK deferred to phase 2. `get_aaak_spec` returns placeholder in v1.

---

## 3. File layout

```
python/src/onelens/palace/
├── __init__.py
├── server.py        # FastMCP app; 19 @mcp.tool definitions; entrypoint main()
├── store.py         # GraphDB + Chroma facade; per-wing resolver
├── taxonomy.py      # resolve_room(source_kind, payload), hall classifier
├── schemas.py       # Pydantic: DrawerRef, Triple, WingSummary, TaxonomyNode, Tunnel, PathHit
├── drawers.py       # add/delete/search/check_duplicate
├── kg.py            # kg_add/query/invalidate/timeline/stats — Cypher templates
├── tunnels.py       # find_tunnels, graph_stats
├── navigation.py    # traverse (generic Cypher BFS)
├── diary.py         # diary_read/write wrappers
├── aaak.py          # spec constant (phase 2 adds compress/decompress)
└── protocol.py      # wake-up protocol string

python/tests/palace/
├── test_taxonomy.py
├── test_kg.py
├── test_tunnels.py
├── test_duplicate.py
└── test_smoke.py    # 19-tool round trip vs live FalkorDB

skills/onelens/PALACE.md   # tool cheat sheet + when-to-use

pyproject.toml
  [project.scripts]
  onelens-palace = "onelens.palace.server:main"
```

Reuse (no re-impl): `onelens.graph.db.get_db`, `onelens.context.embedder.Embedder`, `onelens.context.searcher.ChromaSearcher`, `onelens.context.retrieval.hybrid_retrieve`, `onelens.context.reranker.Reranker`.

---

## 4. Tool surface — full spec

All tools async-safe, idempotent where possible, return Pydantic models (JSON-serialised). Signatures use Python types; MCP marshals.

### 4.1 Read / status

#### `palace_status() -> StatusReport`
Return `{total_drawers, wings:{w:count}, rooms:{r:count}, entities, open_triples, closed_triples, palace_path, protocol, taxonomy_spec_version, aaak_enabled}`.
- drawers: `chroma.count()` over all collections.
- entities/triples: `MATCH (e:Entity) ...` / `MATCH ()-[a:ASSERTS]->() ...` aggregated across wings (FALKORDB `GRAPH.LIST` → per-graph Cypher).
- `protocol`: string from `palace/protocol.py` — wake-up rules verbatim (structure mirrored from MemPalace).
- `taxonomy_spec_version`: `"v1"` (bumped when halls/rooms contract changes).

#### `palace_list_wings(include_agents=False, since=None) -> list[WingSummary]`
`WingSummary = {wing, drawer_count, entity_count, room_count, last_touched}`.
- Enumerate via FalkorDB `GRAPH.LIST` + Chroma distinct `wing` metadata. Union.
- Filter out `agent:*` unless `include_agents`.

#### `palace_list_rooms(wing=None) -> list[RoomSummary]`
`RoomSummary = {wing, room, drawer_count, halls:{h:count}, last_filed_at}`.
- Chroma group-by (`wing`,`room`); hall breakdown from metadata.

#### `palace_get_taxonomy() -> TaxonomyTree`
`TaxonomyTree = {wings: [{wing, rooms: [{room, halls: [{hall, count}]}]}]}` — fully materialised tree.

#### `palace_search(query, limit=5, wing=None, room=None, hall=None, kind=None, rerank=True) -> list[DrawerRef]`
Thin wrapper on `hybrid_retrieve`:
- Build Chroma `where` from filters (`{$and: [{wing:{$eq:...}}, ...]}`).
- Pipe through existing RRF + cross-encoder rerank when `rerank=True` and conceptual query; else short-circuit to FTS (router reused).
- Response includes `snippet` (first 240 chars of drawer body) + `score`.

#### `palace_check_duplicate(content, threshold=0.9, wing=None, hall=None) -> DuplicateReport`
- `Embedder.embed_text(content)` → Chroma `query(n=5, where={wing,hall})` → cosine.
- `{is_dup: max_score >= threshold, matches: [{drawer_id, score, snippet}]}`.
- Threshold tunable via env `ONELENS_PALACE_DEDUP_COSINE`.

#### `palace_get_aaak_spec() -> AaakSpec`
v1: `{"version":"unset","note":"AAAK deferred; OneLens stores verbatim Chroma drawers. Read metadata.filed_at/importance for recency/weight."}`.

### 4.2 Drawer writes

#### `palace_add_drawer(wing, room, content, hall="hall_fact", kind="note", source_file=None, added_by="mcp", importance=1, force=False) -> DrawerWriteResult`
- Validate hall ∈ {hall_code, hall_signature, hall_doc, hall_event, hall_fact}.
- If not `force`: run `palace_check_duplicate(content, 0.95, wing, hall)`; abort with `{skipped:true, matches:[...]}` when dup.
- Deterministic id: `note:{wing}:{sha1(content)[:12]}` (non-`note` halls already have id conventions from code-miner; user-authored notes go under `note:`).
- Chroma `add(ids=[id], documents=[content], embeddings=[emb], metadatas=[{...canonical...}])`.
- Also write FalkorDB: `MERGE (e:Entity {name: fqn_or_slug})` so KG can reference it.
- Emit `filed_at = utcnow().isoformat()`.

#### `palace_delete_drawer(drawer_id) -> DeleteResult`
- `chroma.delete(ids=[drawer_id])` + `MATCH (n) WHERE n.drawerId=$id DETACH DELETE n`.
- Idempotent; returns `{deleted: int}`.

### 4.3 Temporal knowledge graph

#### `palace_kg_add(subject, predicate, object, valid_from=None, ended=None, confidence=1.0, source_closet=None, wing="global") -> TripleRef`
Cypher:
```cypher
MERGE (s:Entity {name:$s}) ON CREATE SET s.firstSeen=$now, s.kind='entity'
MERGE (o:Entity {name:$o}) ON CREATE SET o.firstSeen=$now, o.kind=$oKind
WITH s,o
CREATE (s)-[a:ASSERTS {
  predicate:$p, validFrom:coalesce($vf,$now), validTo:$vt,
  confidence:$c, sourceCloset:$src, wing:$wing, tripleId:$tid
}]->(o)
RETURN a.tripleId AS tripleId, a.validFrom AS vf, a.validTo AS vt
```
- `$tid = sha1(f"{s}|{p}|{o}|{vf}")[:16]`.
- `oKind`: `'literal'` if object is numeric/bool/quoted-string pattern, else `'entity'`.

#### `palace_kg_query(entity, as_of=None, direction="both", predicate=None, depth=1) -> list[TripleHit]`
- Outbound + inbound branches with temporal filter (`$asOf IS NULL OR (validFrom ≤ $asOf AND (validTo IS NULL OR validTo ≥ $asOf))`).
- `depth > 1`: variable-length — FalkorDB quirk: no `*1..n` on typed temporal filter; workaround: wrap in `apoc`-style procedure or iterate in Python for depth 2/3. See LESSONS-LEARNED.
- Bonus: if `entity` matches a `Class`/`Method` `fqn`, append structural-triple projections (`(m)-[CALLS]->(n)` → `(m, "calls", n)`) so KG answers cover code too. Marked `source='structural'` in result.

#### `palace_kg_invalidate(subject, predicate, object, ended=None) -> InvalidateResult`
```cypher
MATCH (s:Entity {name:$s})-[a:ASSERTS {predicate:$p}]->(o:Entity {name:$o})
WHERE a.validTo IS NULL
SET a.validTo = coalesce($ended,$now)
RETURN count(a) AS n
```

#### `palace_kg_timeline(entity=None, since=None, until=None, limit=100) -> list[TimelineEvent]`
Merges:
- KG triples: `validFrom` / `validTo` → events `asserted` / `ended`.
- (Phase 2 hook) `Commit.timestamp`, (Phase 3) `Incident.occurredAt` — sources auto-detected via label existence.
- Sort desc, slice `limit`.

#### `palace_kg_stats() -> KgStats`
`{entities, triples_total, open_triples, closed_triples, predicates:{p:count}, per_wing:{w:{entities,triples}}, literal_entities, top_subjects:[...]}`.

### 4.4 Navigation

#### `palace_traverse(start, max_hops=2, wing=None, edge_kinds=None, node_kinds=None, limit=50) -> list[PathHit]`
- Resolve `start`: try Entity.name → Class.fqn → Method.fqn → room slug.
- Cypher generic BFS: `MATCH p=(s)-[*1..$h]-(n) WHERE ... RETURN p LIMIT $lim`.
- `edge_kinds` filter via `ALL(r IN relationships(p) WHERE type(r) IN $kinds)`.
- Return each path as `{nodes:[{label,name,wing}], edges:[{type,props}]}`.

#### `palace_find_tunnels(wing_a=None, wing_b=None, min_shared=1) -> list[Tunnel]`
- Pure Chroma: `collection.get(include=['metadatas'], where={...})` → group `(room, wing)`.
- Tunnel when `|wings| ≥ 2` (respecting filters).
- `{room, wings:[...], shared_drawer_count, sample_fqns:[...]}`.

#### `palace_graph_stats() -> GraphStats`
- `total_rooms`, `tunnel_rooms`, `total_edges` (all labels summed), `rooms_per_wing`, `top_tunnels` (sorted by `shared_drawer_count`).

### 4.5 Agent diary

#### `palace_diary_write(agent_name, entry, topic="general", importance=1) -> DrawerWriteResult`
Delegates to `add_drawer(wing=f"agent:{agent_name}", room=f"diary-{topic}", hall="hall_event", kind="diary", content=entry, importance=importance, force=True)`.
Dedup off by default — diaries are append-only.

#### `palace_diary_read(agent_name, last_n=10, topic=None, since=None) -> list[DiaryEntry]`
- Chroma `get(where={wing:f"agent:{agent_name}", hall:"hall_event", room:(diary-{topic}|starts_with diary-)})`.
- Sort by `filed_at` desc, slice `last_n`.
- `DiaryEntry = {ts, topic, entry, importance}`.

---

## 5. Wake-up protocol (`palace/protocol.py`)

Returned in `palace_status.protocol`, mirrors MemPalace's wording, OneLens-specific:

```
IMPORTANT — OneLens Palace Protocol:
1. ON WAKE-UP: call palace_status to load wings + halls + protocol + taxonomy version.
2. BEFORE RESPONDING about any code symbol, ticket, incident, or fact: call palace_search
   or palace_kg_query FIRST. Never guess. Verify structural claims with impact/trace.
3. IF UNSURE about a fact (FQN, owner, current status): say "let me check" and query.
4. AFTER EACH SESSION: call palace_diary_write to record what happened, what changed,
   what needs revisit.
5. WHEN FACTS CHANGE: palace_kg_invalidate the old fact, palace_kg_add the new one.
   Code-structural changes handled by plugin delta sync — don't hand-author those.
```

---

## 6. Hall migration (ADR-P3 detail)

Current: `hall` fixed constant across code drawers. Move to:

| Drawer kind | Hall |
|---|---|
| method body | `hall_code` |
| method signature only | `hall_signature` |
| class/method javadoc | `hall_doc` |
| endpoint summary | `hall_signature` |
| diary entry | `hall_event` |
| user note / KG-derived | `hall_fact` |

Change sites: `miners/code_miner.py` `mine` + `mine_upserts`, same for `context_import` path. Guard with metadata schema version bump (`schema_version: "2"`) — tools filter gracefully when mixed (v1 = hall_code implied).

LESSONS-LEARNED addendum: "Hall taxonomy split — any new mining path must match else palace_list_rooms + palace_search (hall filter) under-count silently."

---

## 7. Implementation phases (~6 working days)

| Phase | Deliverable | Day |
|---|---|---|
| P0 — scaffold | `palace/` package, `server.py` with 19 stub tools raising `NotImplementedError`, entrypoint wired, console script | 0.5 |
| P1 — reads | status, list_wings, list_rooms, get_taxonomy, search, find_tunnels, graph_stats, get_aaak_spec | 1.0 |
| P2 — drawer writes | add_drawer, delete_drawer, check_duplicate (+ dedup env knob) | 1.0 |
| P3 — KG | Entity/ASSERTS schema + index; kg_add, kg_query, kg_invalidate, kg_timeline, kg_stats | 1.5 |
| P4 — traverse | generic Cypher BFS with filters | 0.5 |
| P5 — diary | diary_write/read | 0.3 |
| P6 — hall migration | CodeMiner split + schema_version bump + LESSONS entry | 0.7 |
| P7 — protocol + skill + tests | `protocol.py`, `PALACE.md`, 5 test files, smoke harness | 0.5 |

CI addition: `pytest python/tests/palace -q` in `.github/workflows/ci.yml`.

---

## 8. Shape of a tool call (reference)

```python
# server.py (excerpt)
@mcp.tool
def palace_kg_add(
    subject: str,
    predicate: str,
    object: str,
    valid_from: str | None = None,
    ended: str | None = None,
    confidence: float = 1.0,
    source_closet: str | None = None,
    wing: str = "global",
) -> TripleRef:
    """Assert a temporal fact. Returns tripleId. Use kg_invalidate to close."""
    return kg.add(subject, predicate, object, valid_from, ended,
                  confidence, source_closet, wing)
```

---

## 9. Risks + open questions

1. **FalkorDB variable-length with predicate filter** — may force Python-side depth unrolling for `traverse` beyond hop 2. Confirm in P4.
2. **Chroma single-collection vs per-wing** — current design reuses single collection; at >200k drawers with 50+ wings, per-wing sharding may be needed. Flag, don't solve in v1.
3. **Literal entity namespace collision** — `:Entity {kind:'literal', name:'prod'}` collides across facts. Accept: MemPalace has same tradeoff.
4. **AAAK** — revisit when context budget for index (`list_wings/rooms/taxonomy`) grows past 5k tokens per wake-up.
5. **Dual-MCP onboarding** — two servers confuse users. Mitigation: `PALACE.md` explicitly maps "structural → existing MCP; cross-source/fact → palace". Phase 8 (later) may merge into a single MCP with namespaced tools.

---

## 10. Tracker updates (same turn as first commit)

- `docs/PROGRESS.md` → new row "Palace MCP — 🟡 design merged"
- `CHANGELOG.md` → `[Unreleased] / Added / Palace MCP scaffolding`
- `docs/DECISIONS.md` → ADR-P1…P7 entries
- `docs/LESSONS-LEARNED.md` → hall-split drift warning (once P6 lands)
