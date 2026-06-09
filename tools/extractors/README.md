# Standalone extractors — proof that the graph is language-neutral

These tools demonstrate (and implement) the core thesis of
`docs/design/multi-language-architecture.md`: **extraction is per-language, but
the JSON contract + importer + graph are universal.** Each extractor parses one
language with that language's *native* parser and emits the same JSON the
IntelliJ plugin emits for Java. The existing `GraphLoader` imports it unchanged.

| Extractor | Backend | Status |
|-----------|---------|--------|
| (plugin) Java/Kotlin | IntelliJ PSI | shipped, 100% type-accurate (`source=PSI`) |
| `python_ast_extractor.py` | Python `ast` (stdlib) | **runs + verified** — imported OneLens's own 104 classes / 370 methods / 312 calls; `GraphDB` subclasses + PageRank correct (`source=AST`) |
| `go/main.go` | Go `go/ast` (stdlib) | reference impl — structural; full call-resolution needs `go/types` (`source=AST`→`TYPES`) |

## The universal core contract

A minimal export is just these top-level keys (every framework block —
`spring`, `jpa`, `vue3`, `tests` — is `if`-gated in the loader, so omitting them
no-ops cleanly):

```jsonc
{
  "version": "1.0", "exportType": "full",
  "project": { "name": "<graph>" },
  "classes":  [ { "fqn", "name", "kind", "packageName", "superClass",
                  "filePath", "lineStart", "lineEnd", "enclosingClass", "source" } ],
  "methods":  [ { "fqn", "name", "classFqn", "returnType",
                  "parameters": [ { "name", "type", "annotations" } ],
                  "modifiers", "throwsTypes", "isConstructor",
                  "filePath", "lineStart", "lineEnd", "annotations", "source" } ],
  "fields":   [ { "fqn", "name", "classFqn", "type", "filePath", "lineStart", "source" } ],
  "callGraph":   [ { "callerFqn", "calleeFqn", "line" } ],
  "inheritance": [ { "childFqn", "parentFqn", "relationType": "EXTENDS|IMPLEMENTS" } ],
  "methodOverrides": [ { "methodFqn", "overridesFqn" } ],
  "adapters": [ "<language>-<backend>" ]
}
```

FQN convention (uniform across languages): `pkg.Type` for a class,
`pkg.Type#member` for a field, `pkg.Type#method(paramType,paramType)` for a
method. The `source` tag (`PSI` | `TYPES` | `LSP` | `AST` | `TREE_SITTER`)
records extraction confidence so retrieval can rank by accuracy.

## Run

```bash
# Python (fully working)
python tools/extractors/python_ast_extractor.py <src_root> --name myproj > out.json
onelens import-graph out.json --graph myproj --backend falkordblite

# Go (reference)
cd tools/extractors/go && go run main.go <src_root> --name myproj > out.json
```

## Adding a new language — the recipe

1. Pick a backend by accuracy tier (see the design doc): native PSI (IDE) →
   LSP (standalone, type-resolved) → tree-sitter (structural floor).
2. Walk the source; emit the universal core above. Resolve calls/inheritance to
   FQNs where the backend allows (that's what separates `AST` from `TYPES`).
3. Stamp every node `source`. Import — no loader change for the universal core.
4. Framework concepts (Django models, FastAPI routes, React components) are a
   *separate* overlay: emit them under a new top-level key and add a
   `SubdocLoader` on the importer side (see design doc §2). The universal core
   never changes.

The Python extractor here is the worked example end-to-end; the Go one shows the
same contract for a second, statically-typed language.
