# Hybrid retrieval — `onelens_retrieve`

Returns top-K ranked hits for conceptual / natural-language questions, each
with the actual source code so an LLM can read methods directly — not just
FQNs.

**Gate: only call when `onelens_status.capabilities.has_semantic = true`.**
Otherwise fall back to `onelens_search` (FTS on names).

## When to use retrieve vs search vs query

| Question shape | Tool |
|---|---|
| "class named User*" / "where is method `authenticate`" | `onelens_search` |
| "who calls `foo()`", "impact of renaming X", "trace this endpoint" | `onelens_query` + patterns in `queries-code.md` |
| "how does authentication work", "show me the password-hashing logic", "where's the rate limiter implemented" | `onelens_retrieve` ✅ |
| "find every query touching table `Request`" | `onelens_query` + `queries-sql.md` |

Rule of thumb: **retrieve when the user asks for *concept*, not *name*.**

## How it works under the hood (agent doesn't need to, but useful when debugging)

1. **Router** — if the query looks like an exact class name / FQN
   fragment, short-circuits to a direct FTS → no semantic roundtrip.
2. **RRF** (reciprocal rank fusion) — merges FTS ranks + ChromaDB semantic
   ranks.
3. **Kind boost** — methods get a mild boost over classes for code questions.
4. **PageRank boost** — multiplicative on already-matched hits (structural
   centrality matters only once the hit is relevant).
5. **Cross-encoder rerank** — top-K from the fusion re-scored by
   mxbai-rerank-base.
6. **Threshold filter** — cross-encoder score < 0.02 dropped as "gibberish".

## Usage

```bash
onelens call-tool onelens_retrieve \
  --query "how does the password reset flow work" \
  --graph <name>
```

## Parameters worth knowing

| Param | Default | Bump when |
|---|---|---|
| `n_results` | 10 | user wants more hits or you're summarising a broad area |
| `fanout` | 50 | always leave at default; only bump if zero hits |
| `include_snippets` | true | turn off for pure FQN lists |
| `include_neighbors` | false | enable when you want 1-hop `:CALLS` context alongside each hit |
| `rerank` | true | keep on — mxbai is what makes this beat plain FTS |
| `rerank_pool` | 100 | lower to 50 for faster responses in interactive sessions |
| `project_root` | env `ONELENS_PROJECT_ROOT` | must be set for snippets to resolve absolute file paths |

## Result shape

```json
{
  "fqn": "com.example.auth.PasswordService#hash(java.lang.String)",
  "type": "Method",
  "score": 0.78,
  "rerank_score": 2.41,
  "file_path": "src/main/java/com/example/auth/PasswordService.java",
  "line_start": 42, "line_end": 58,
  "snippet": "public String hash(String raw) { ... }",
  "context_text": "...",
  "rank_fts": 3, "rank_semantic": 1,
  "callers": ["...#resetPassword", "...#login"],
  "callees": []
}
```

Use `file_path:line_start-line_end` as evidence pointers in answers.

## Fallback pattern

```
status = onelens_status(graph)
if status.capabilities.has_semantic:
    hits = onelens_retrieve(query=$q, graph)
else:
    # FTS on likely-name tokens
    for token in tokenize($q):
        onelens_search(term=token, graph)
```

## Empty result = genuine no-match

If `onelens_retrieve` returns `[]`, the cross-encoder filtered everything
below threshold 0.02 — meaning nothing in the semantic index is remotely
close to the query. Don't keep rewording; tell the user the concept isn't
in the indexed code and fall back to `onelens_search` for name tokens.
