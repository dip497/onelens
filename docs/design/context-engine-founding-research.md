# Context Engine — Founding Research (2026-06-12)

Synthesis of 5 parallel web-research passes: competitors, agent-context evidence,
canonical-store patterns, scale/performance, OSS GTM. Feeds the v2 founding
architecture doc. All claims cite sources gathered 2026-06-12.

## 1. Leaders per dimension

| Dimension | Leader | Number / fact | What we adopt |
|---|---|---|---|
| Incremental index freshness | Meta Glean | O(fanout) per commit, stacked immutable fact DBs, minutes-fresh on a multi-billion-LOC monorepo | Stacked immutable snapshot layers; never destructive-update an index |
| Client-side delta sync | Cursor | Merkle tree of AST chunks, ~90% fewer re-embeds; breaks at ~400k files / 64GB+ RAM | Content-hash gating (we have deterministic FQN IDs already); their ceiling = our opportunity |
| Cloud FTS | GitHub Blackbird | 200M repos, 15.5B blobs, dynamic n-grams, Kafka delta | Dynamic gram idea only; not our scale problem |
| Self-hosted FTS | Sourcegraph Zoekt | Shard early-exit, sub-second; RAM blows up at 10k+ repos | Per-repo shards, importance-presorted |
| Embedded graph DB | Kuzu | 5.5–15.8x faster queries, ~18x faster ingest vs Neo4j; pip-installable, no Docker, openCypher | **Candidate to replace FalkorDB as default** (keep FalkorDB as server-mode option — it has FTS+vector hybrid) |
| Local vector at 1M+ | LanceDB | Memory-mapped columnar, millions of vectors w/o full-RAM; ChromaDB rated "prototyping only" at 1M+ | **Migrate ChromaDB → LanceDB past ~500k drawers**; IDs portable |
| Structural code accuracy | Sourcegraph SCIP / us (PSI) | SCIP = compiler-accurate, OSS indexers, community-owned protocol (scip-code.org) | SCIP ingestion = our breadth tier; PSI stays depth tier |
| Live LSP tools for agents | Serena MCP | 25k stars in ~15 months, MIT, LSP-accurate, **no persistent graph, no SDLC, no semantic layer** | Proves MCP form factor demand; their gaps = our feature list |
| SDLC fusion | Unblocked | Code+Slack+Jira+docs, MCP-native, claims 48% fewer agent tokens; **code treated as text, zero structural accuracy** | Their fusion UX; we add the compiler-accurate spine they lack |
| Agent memory | Zep/Graphiti, mem0, Hindsight | Graphiti bi-temporal KG (arXiv 2501.13956); Hindsight 94.6% LongMemEval vs mem0 49% | Bi-temporal edges (valid_at/invalid_at per commit); episodic layer phase-later |
| Market validation | Glean $200M ARR; PlayerZero $20M A; Unblocked funded | Category proven | Bottom-up OSS lane is open — all leaders are closed cloud |

## 2. Validated market gaps (nobody covers)

1. **Compiler-accurate + multi-language + local-first + persistent graph, simultaneously.**
   Serena: accurate but no graph. Sourcegraph: accurate graph but server-heavy, not local.
   New OSS MCP entrants (codescope, code-nexus, localnest, ckg): all tree-sitter (F1 ~0.66–0.95 on callers vs compiler truth).
   Spring/JVM depth: zero tools besides us handle injection, AOP, enum-as-config.
2. **SDLC-wide fusion WITH structural code accuracy.** Unblocked fuses but code=text. Sourcegraph accurate but no SDLC. Provenance chain (ticket → commit → bean chain → Slack decision) = uncovered.
3. **Compiler-accurate impact analysis as an MCP/API tool.** Nuanced archived (pivoted, repo dead 2026-03). Sourcegraph has SCIP but no impact API. Our `onelens impact` is the only existing instance.

## 3. Evidence: when indexes beat agentic grep

- Augment (top of SWE-bench Verified): grep+persistence sufficient **on SWE-bench** — small, well-known OSS repos in model training data. Explicitly NOT generalizable to large private codebases, conceptual queries, unstructured content. (jxnl.co writeup)
- Agentless (arXiv 2407.01489): structured repo tree + **skeletons** + hybrid retrieval beat pure agentic AND pure vector. Pre-built structural representation wins.
- Anthropic context engineering (Sep 2025): "context rot" — right tokens, not more tokens. Curate/compress/isolate.
- Indexes win when: >100k LOC private repo, conceptual queries, cross-file type flow, callers-of enumeration, token-budget-constrained.
- **Eval harnesses to adopt: CodeRAG-Bench (repo-level split), RepoBench-R (cross-file retrieval recall), SWE-bench Verified (end-to-end with/without our MCP context).** Beating the Agentless baseline = the credibility result to publish.

## 4. Canonical store — design verdict

One-sentence principle (from Glean): keep raw import blobs as the immutable append-only log; all structural/semantic data = typed facts with bi-temporal edges keyed to commit SHAs; graph DB + vector DB = regenerable views.

- **Identity**: Kythe VName 5-tuple `{corpus, root, path, language, signature}` → hash to stable 128-bit ID. Our FQNs already fit `signature`.
- **Snapshot record**: `{snapshot_id, corpus, commit_sha, created_at, payload(blob), parent_id}` — delta chain; views rebuildable from chain.
- **Edges**: `{src, dst, kind, valid_at(commit), invalid_at(commit|null), created_at, expired_at, attributes}` → "graph as of commit X", "what changed between X and Y".
- **Workspace registry**: manifest (`workspaces.yaml`), lazy graph load on first query, LRU eviction (max ~3 in memory). No OSS standard exists — we get to set it.
- Steal: Glean fact idempotency + stacked DBs; SCIP wire format for breadth-tier ingestion; Graphiti bi-temporal; skip Glean's Angle/Datalog engine (Cypher suffices).

## 5. Scale numbers that constrain design

- Embedding 1M methods: GPU ~2.4h; CPU INT8 ~8–12h; API ~$3–6k (non-viable). → INT8-quantize default embedder; content-hash gating makes per-commit re-embed ~1% = minutes.
- Cursor dies at ~400k files; our pitch must include "designed O(changes) from day 1".
- Kuzu handles 100K nodes/2.5M edges in <0.13s queries embedded; FalkorDB needs server. Graph at 10M+ edges on laptop: Kuzu is the safe bet.
- ChromaDB ceiling ~500k vectors (RAM-resident HNSW); LanceDB memory-mapped past millions.

## 6. Wedge verdict (GTM research)

**Wedge: impact-before-the-agent-acts.** "Before the agent writes a line, it knows what the change breaks."
- Daily-loop (every PR), unlike onboarding (episodic — Sourcetrail's fatal flaw, discontinued 2021).
- Continue.dev pivoted their whole product to PR checks = revealed demand.
- Gergely Orosz's top complaint ("AI useless on large legacy codebases") — impact analysis is the fix.
- 90-sec demo: same prompt with/without MCP impact tool; without = agent edits 1 file, with = agent edits all 4 affected files. Contrast visible.
- Distribution: MCP registries, awesome-MCP lists, HN Show, Claude Code skill ecosystem (Serena/Repomix path).

**Open-core split**: free/Apache-2.0 = all core (import, graph, MCP impact/trace/search/retrieve, CLI, local everything). Paid = team graph sync, PR-gate GitHub Action (blocking checks), SSO/RBAC, audit, hosted. Never gate accuracy or local retrieval. No BSL on core.

**Failure patterns to avoid**: Sourcetrail (episodic use, no daily loop); Bloop (cloud indexing = enterprise security objection + no habit); Roo Code (embedding indexer that dies at 65k files, archived 2026-05). Must live inside every agent invocation.

## 7. Critical what-ifs

| What if | Likelihood | Response |
|---|---|---|
| Frontier models + agentic grep get good enough; indexes unnecessary | Medium on small repos; LOW on enterprise brownfield (evidence §3) | Our eval harness must publish the with/without delta on LARGE private-style repos, not SWE-bench toys |
| Anthropic/Cursor ship native deep indexing | Medium-high eventually | Be the local-first, compiler-accurate, SDLC-wide layer they can't justify building; MCP keeps us host-agnostic |
| Sourcegraph community closes gap via SCIP | They have parts; no impact API, no local-first, no fusion | Ship SCIP ingestion ourselves — their indexers become OUR breadth tier |
| FalkorDB/Chroma fall over at 10M+ scale | Real (numbers §5) | Kuzu + LanceDB embedded defaults; store-as-views means swap is cheap |
| Episodic memory bet doesn't pay | Cross-session coding evidence is thin (only Reflexion within-session +11pp) | Keep episodic phase-later; don't found on it |
| Solo dev vs $20M-funded competitors | Certain | Their business model (closed cloud) can't follow into local-first OSS; speed + narrowness is the play |
| Tree-sitter MCP entrants commoditize "code graph" | Already happening (6 new entrants 2025-26) | Compete on accuracy (publish F1 vs compiler truth like codescope does) + Spring depth + SDLC fusion, never on "has a graph" |

## 8. Architecture deltas vs current OneLens (decision input)

1. Canonical store layer (snapshot chain + bi-temporal facts) — NEW, becomes the core asset.
2. Kuzu embedded as default graph backend; FalkorDB demoted to server-mode option. (Validate with our parity gate first.)
3. LanceDB as vector default at scale; ChromaDB ok below ~500k.
4. VName-style identity wrapping existing FQNs (corpus + language fields added).
5. SCIP ingestion converter = breadth tier (10+ languages headless, free indexers).
6. Headless PSI ApplicationStarter = depth tier without IDE open.
7. Eval harness on CodeRAG-Bench/RepoBench-R + SWE-bench ablation = the published proof.
8. Wedge product surface: MCP `impact` + `context_pack` tools, auto-invoked pre-edit.
