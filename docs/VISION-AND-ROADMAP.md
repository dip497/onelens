# OneLens: Vision, Architecture, Roadmap

Captures decisions made in planning sessions through 2026-04. Living doc — update as reality shifts.

---

## 1. End Goal

**Build an open-source engineering context graph for a company — the AI nervous system for all dev artifacts.**

Not "code search tool". Not "bug tracker". Unified knowledge system where every engineering artifact lives together and any AI agent can query across all of it.

### Domains to eventually cover

| Domain | Source | Hall | Phase |
|--------|--------|------|-------|
| Code structure | IntelliJ PSI → FalkorDB | `hall_code` | 1 ✅ have |
| Code semantics | Same → ChromaDB | `hall_code` | 1 ✅ have |
| Git history | `git log`, diffs, blame | `hall_git` | 2 |
| Bugs | Jira/GitHub issues | `hall_bugs` | 2 |
| Improvements / features | Same trackers | `hall_improvements` | 2 |
| PR reviews | GitHub/GitLab API | `hall_pr_reviews` | 2 |
| Decisions / ADRs | `docs/adr/`, Confluence | `hall_decisions` | 3 |
| Incidents / post-mortems | PagerDuty, runbooks | `hall_incidents` | 3 |
| Observability | Prometheus, Grafana, Sentry | `hall_observability` | 3 |
| CI/CD | Jenkins, GHA logs | `hall_ci` | 3 |
| Slack / chat | Slack export | `hall_chat` | 4 |
| Design docs, wikis | Confluence, Notion | `hall_docs` | 4 |

### Positioning

- **Not** an Augment-clone. Not competing on general code retrieval (commodity space, 10+ open-source tools).
- **Target**: Open-source PlayerZero for companies that won't pay $30/user/month.
- **Moat**: Java PSI accuracy + Spring-aware graph + structural impact analysis + temporal KG — capabilities Augment (pure vector) can't match.

---

## 2. Competitive Landscape

| Tool | Status | Their play | Our counter |
|------|--------|-----------|-------------|
| **PlayerZero** | Commercial, enterprise | Full SDLC context (code + tickets + observability + sessions) | Open-source version of the same vision |
| **Augment Code** | Commercial | Custom embedder, quantized ANN, Context Lineage (git), MCP | Match via LLM-summarized diffs + Qwen3 embedder (85% parity) |
| **Sourcegraph Cody** | Commercial enterprise | Pre-indexed embeddings, OpenCtx external | Free + PSI-accurate for Java |
| **Cursor** | Commercial | Real-time index, Turbopuffer backend | IDE-integrated via plugin |
| **GitNexus / Axon / CodeGraphContext / Code Atlas / codemogger / git-mimir / hikma-engine / ctx / srclight** | Open-source | Code indexing crowd (8+ competitors) | Skip competing here — go multi-source |
| **MemPalace** | Open-source | Conversation memory (AI chat history) | Different problem; we borrow 30% of their ChromaDB plumbing |

**Crowded space = code-only indexing.** **Open space = multi-source SDLC (code + git + tickets + observability).** That's our wedge.

---

## 3. Core Architecture — 3-Store Stack

### Triple-store design (intentional, not accidental)

```
┌────────────────────────────────────────────────────────────┐
│ FalkorDB                                                    │
│   Structural graph: CALLS, EXTENDS, HANDLES, INJECTS,      │
│   HAS_METHOD, HAS_FIELD, OVERRIDES, ANNOTATED_WITH         │
│   Source: IntelliJ PSI (100% accurate type resolution)     │
│   Queries: impact, trace, inheritance, Spring wiring        │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ ChromaDB                                                    │
│   Vector embeddings + metadata drawers                      │
│   Model: Qwen3-Embedding-0.6B (bf16, max_seq=512,          │
│          torch.compile dynamic)                             │
│   Queries: semantic similarity, concept match               │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ SQLite KG (DORMANT — Tier 3)                                │
│   Temporal triples: (subject, predicate, object, timestamp)│
│   Source: git events, ticket state, PR reviews             │
│   Queries: "bugs touching X last 90d", causality chains    │
│   From MemPalace; inactive until miners land               │
└────────────────────────────────────────────────────────────┘
```

**All three feed `retrieve` via Reciprocal Rank Fusion.** FalkorDB FTS catches identifiers/acronyms; ChromaDB semantic catches concepts; KG catches temporal.

### Why keep all three

- FalkorDB alone: can't answer "find code about auth" (no identifier match)
- ChromaDB alone: can't answer "what breaks if I change X" (no exact call graph)
- Augment's bet (pure vector): loses structural precision
- **Our bet: combine all three — sum > parts**

### Storage footprint (reference: large Spring monorepo, ~75K methods)

- FalkorDB: ~100 MB graph
- ChromaDB: ~200 MB (49K drawers @ Qwen3 1024-dim)
- SQLite KG: 0 (dormant)
- **Total: 300 MB per project.** Negligible.

---

## 4. Retrieval Pipeline

### Current (Phase 1, shipping)

```
query → retrieve.py
   ├─ FalkorDB FTS (parallel) → top-50 by lexical
   └─ ChromaDB semantic (parallel) → top-50 by vector
       ↓
   RRF fusion (k=60) → top-N=50 fused
       ↓
   batch location lookup (filePath, lineStart, lineEnd)
       ↓
   snippet read from disk (project_root-relative)
       ↓
   cross-encoder rerank (mxbai-rerank-base-v1, 352 MB) → top-10
       ↓
   optional: 1-hop neighbors (callers/callees via --neighbors)
       ↓
   return structured hits (FQN + type + score + snippet + context)
```

### CLI

```bash
onelens retrieve "<natural query>" --graph <name> \
  [--rerank/--no-rerank]      # default on
  [--neighbors]               # 1-hop callers/callees
  [--n 10] [--fanout 50] [--rerank-pool 50]
  [--project-root <path>]     # or ONELENS_PROJECT_ROOT env
  [--json]                    # MCP-ready output
```

### Defaults (as of 2026-04)

- Hybrid: always on (core of `retrieve`)
- Rerank: **on** by default
- Snippets: on when `--project-root` set
- Neighbors: opt-in
- Model: Qwen3-Embedding-0.6B (embedder) + mxbai-rerank-base-v1 (reranker)

### Benchmarked numbers

- 49K drawers on RTX A2000 4GB
- Warm query: 200-500ms end-to-end
- Cold query: ~12s (model load — biggest UX pain, fixed by persistent server mode)
- Embedder VRAM: 1.2 GB
- Reranker VRAM: +350 MB
- Peak during query: ~1.6 GB on GPU

---

## 5. Key Decisions (locked)

### D1. Embedder: Qwen3-Embedding-0.6B

- Benchmarked winner in 4-way trial (vs MiniLM, CodeRankEmbed, Jina)
- +41.4% accuracy over MiniLM on code queries
- 1.2 GB bf16 fits 4 GB GPU with reranker
- **Knobs**: max_seq=512, batch=64, torch.compile(dynamic=True), `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- Fine-tune later (Tier 3). Don't switch model without re-running `trial_4way.py`.

### D2. Reranker: mxbai-rerank-base-v1

- Only code-aware reranker fitting 4GB alongside embedder
- 352 MB weights, standard arch (no `trust_remote_code` issues like Jina)
- Tried and rejected: Qwen3-Reranker-0.6B (1.1 GB, too tight), BGE-reranker-v2-m3 (2.1 GB, too big), Jina v2 (531 MB but broke with transformers 5.x)
- Quality: +10-15% top-1 precision vs no rerank

### D3. Hybrid search always on in `retrieve`

- Research confirms +15-20% recall over pure dense or pure FTS
- RRF k=60 (industry standard, Cormack 2009 paper)
- N=50 per source → fuse → rerank top-50 → top-10 (N>>K principle)

### D4. Resume-on-crash indexing

- `CodeMiner._get_existing_ids(prefix)` checks ChromaDB before mining
- Deterministic IDs: `method:{fqn}`, `class:{fqn}`, `endpoint:{METHOD:path}:{handler}`
- Rerun = skip already-indexed. No re-embedding wasted.
- Essential: full index takes 20 min; one OOM shouldn't restart from scratch.

### D5. Trivial method filter (~45% reduction)

- Skip getters/setters (get/set/is/has/can + body ≤3 lines)
- Skip toString/hashCode/equals/clone/finalize
- 74K methods → 37K after filter on the reference corpus

### D6. VRAM fragmentation fix

- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` set in embedder module-load (before torch imports)
- `torch.cuda.empty_cache()` every 10 encode calls
- Without these: OOM at ~23% of full index

### D7. Skip during Phase 1

- Quantized ANN (not needed until 1M+ drawers)
- Custom embedder training (Qwen3 at 85% is fine)
- Real-time streaming / BigTable infra (we're single-server)
- Per-user branch-aware indices (internal tool)
- Multi-language parsing (the reference corpus is Java)

### D8. Addressing scheme (planned, not yet built)

Standard slug format: `<org>/<repo>@<version>` (e.g. `my-org/my-repo@HEAD`).
Multi-repo via named groups.
ACL layer: inherit from source repo permissions.
Per-user personal halls: `hall_personal_<user>` alongside shared halls.
**Must land BEFORE Phase 2 miners to avoid hardcoded single-graph assumption.**

---

## 6. What We Borrow from MemPalace

### Active (30%)

| File | Purpose |
|------|---------|
| `backends/chroma.py` | ChromaDB adapter (heavily modified) |
| `palace.py` | Collection factory |
| `config.py` | Path resolution, sanitizers |
| `query_sanitizer.py` | Prompt injection defense in retrieve |

### Dormant (70%, keep for Phase 2+)

| File | Activates in | Purpose |
|------|--------------|---------|
| `knowledge_graph.py` | Tier 3 | Temporal triples from git/bugs/PRs |
| `palace_graph.py` | Tier 3+ | Cross-hall tunnels (regression clusters, hot spots) |
| `layers.py` | Tier 3 | L0-L3 agent wake-up context |
| `dedup.py` | Tier 4+ | Cross-source drawer dedup |

### Not borrowing

- AAAK compression dialect — overkill for current scale; consider Tier 4 when multi-hall
- MemPalace's `searcher.py` — we replaced with hybrid retrieve
- Diary / conversation mining — wrong problem domain for us

---

## 7. Roadmap

### Tier 1 — Next 2 weeks (ship current PR first, then this)

Closes ~60% of Augment quality gap.

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | **Persistent server mode** (FastAPI, keep models loaded) | 1 day | Kills 12s cold start → 200ms warm every query |
| 2 | **Context curation** (dedupe, merge ranges, summarize weak) | 1 day | Tighter LLM-ready output |
| 3 | **Method body export** from IntelliJ plugin + re-embed | 2 days | +15-20% accuracy |
| 4 | **Git miner** with Gemma2:2b diff summarization | 2 days | Match Augment Context Lineage |
| 5 | **Quantized int8 embeddings** | 1 day | 4× storage, 2× search speed |

### Tier 2 — Weeks 3-6

Closes remaining quality gap.

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 6 | AST-aware chunking for long methods | 3 days | +5-10% |
| 7 | HyDE query rewriting (Gemma2:2b → hypothetical answer → embed) | 1 day | +5-10% on vague queries |
| 8 | Plugin auto-reindex on file save → ChromaDB | 2 days | Real-time feel |
| 9 | MCP server proper (retrieve/impact/trace/git_search as tools) | 1 day | Agent plug-and-play |
| 10 | Rent bigger GPU (one-time indexing on 4090 ~$0.30/hr) | procurement | 10× indexing speed |

### Tier 3 — Months 2-3: **surpass Augment**

Multi-source + temporal — Augment can't do these.

| # | Item | Effort | Why it matters |
|---|------|--------|----------------|
| 11 | **Multi-hall**: bugs + PRs + decisions + incidents | 2 weeks | Beyond Augment's code+git only |
| 12 | **Knowledge graph activation** from git events + ticket state | 1 week | Temporal queries Augment lacks |
| 13 | **Addressing refactor** (org/repo@version, multi-repo groups, ACL) | 1 week | Foundation for team deployment |
| 14 | **Fine-tune Qwen3 on the reference corpus code pairs** (LoRA, 1 A100 hour) | 1 week | +10-15% domain accuracy |
| 15 | **Cross-encoder fine-tune** on domain | 2 days | Reranker edge |

### Tier 4 — Months 4+: Scale when forced

- Quantized ANN (HNSW tuning) — at 1M+ drawers
- Real-time streaming (queue + workers) — at 20+ concurrent devs
- Multi-tenant server, SSO, RBAC — when deploying company-wide
- Web UI for non-CLI users — when PMs / designers adopt
- Custom embedding model from scratch — when enterprise customers demand

---

## 8. What Makes Us Beat Augment (the moat)

| Capability | OneLens | Augment |
|------------|---------|---------|
| Java type resolution | **100% PSI** | ~90% tree-sitter |
| Spring / JPA / REST modeling | **Native graph** | Generic embedding |
| Call graph (impact, trace) | **Explicit CALLS edges** | Implicit via vectors |
| Endpoint blast radius | **Dedicated `impact`** | Inferred |
| Temporal queries (once KG live) | **Structural traversal** | Pure semantic — weak |
| Cost | **$0** | $30+/user/month |
| Privacy | **Fully local** | Google Cloud |
| Price transparency | **Free forever** | Credit system |

Where Augment beats us (accept, don't try to match):

- Scale (100M LOC codebases) — skip till forced
- Real-time keystroke-level updates — skip till forced
- Custom embedder quality edge — close later via fine-tuning
- Cloud infrastructure — only needed for team deployment
- Multi-language (14 langs via tree-sitter) — Java is enough for the reference corpus

---

## 9. Immediate Next Steps

**Ship order:**

1. **Commit current PR** (hybrid + rerank + snippets already working on branch `feature/context-graph-semantic-search`)
2. **Next PR: Tier 1 #1 persistent server mode** — biggest user-facing win, unblocks MCP
3. **PR after: Tier 1 #3 method bodies + #4 git miner** — biggest quality wins
4. **Tier 2 work as separate PRs** — addressing refactor before multi-source miners

**Don't do:**

- Don't rewrite embedder — Qwen3 is fine
- Don't add quantized ANN — premature
- Don't chase Augment feature-for-feature — play our game (structural + temporal + free)
- Don't index everything before architecture settled — do Tier 1 foundation first

---

## 10. Open Questions

- Rent GPU for one-time re-indexes with method bodies? (~$10 for a full reference-corpus index on 4090)
- Team HTTP deployment: host on dev-box with consumer GPU (24 GB 3090/4090) or cloud VM (T4 ~$300/mo)?
- Web UI scope — how much non-technical-user reach do we want in Phase 1?
- Fine-tuning corpus — do we have 10K+ (query, method) pairs for LoRA on Qwen3? If not, how to generate?
- When to activate knowledge_graph.py — sit with 2 weeks of git+bugs data first, then populate?

---

## References

- Augment engineering blogs: context engine, real-time index, quantized vector search, context lineage
- PlayerZero: how-playerzero-works docs
- MemPalace: github.com/MemPalace/mempalace (v3.3.0 released 2026-04)
- Qwen3 Embedding blog: qwenlm.github.io/blog/qwen3-embedding
- bm25s, Axon, CodeGraphContext, GitNexus — open-source code indexing alternatives
- Internal trial results: `python/trial_4way.py` (4-way model comparison)
- Internal lessons: `docs/LESSONS-LEARNED.md` (PSI, FalkorDB quirks, prior failures)
- Memory: `~/.claude/projects/-home-dipendra-sharma-projects-onelens/memory/` (Qwen3 knobs, OOM recovery, embedding choices)

---

_Last updated: 2026-04-14. Session-compacted context preserved here._
