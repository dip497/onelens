# Standalone extractors — proof that the graph is language-neutral

These tools demonstrate (and implement) the core thesis of
`docs/design/multi-language-architecture.md`: **extraction is per-language, but
the JSON contract + importer + graph are universal.** Each extractor parses one
language with that language's *native* parser and emits the same JSON the
IntelliJ plugin emits for Java. The existing `GraphLoader` imports it unchanged.

| Extractor | Backend | Status |
|-----------|---------|--------|
| (plugin) Java/Kotlin | IntelliJ PSI | shipped, 100% type-accurate (`source=PSI`) |
| `go/` | Go type checker: `golang.org/x/tools/go/packages` + `go/types` | **verified** on a 971-file agent: 0 type errors, 15,602 calls, every call to project code lands on a line naming its callee (`source=TYPES`) |
| `python_extractor.py` | stdlib `ast` + Jedi (follows imports, infers `obj.method()`) | **verified** on an 83-file agent: 3,505 project calls; `system_env()` callers 16/16 against grep (`source=LSP`) |
| `csharp/` | Roslyn semantic model; MSBuild (`dotnet msbuild -getItem`) gives each project's exact sources, defines and references | **verified** on the poller (4 projects, 0 compile errors, 3,646/3,646 project calls land on a line naming the callee, `ExecuteGetRequestR` call sites 39/39 against grep, 75 ASP.NET endpoints) and the agent's .NET Framework 4.0 code (7 projects, 4,191/4,191; 38 compile errors, all in Windows COM libraries) (`source=TYPES`) |

Why not IntelliJ PSI for these: `docs/DECISIONS.md` ADR-039.

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
# Go — every go.mod under <src_root>; list each platform the code builds for
cd tools/extractors/go && go build -o /tmp/go-extractor . && \
  /tmp/go-extractor <src_root> --name myproj --goos linux,windows,darwin > out.json
# (run `go mod download` in each module first; packages that fail to type-check are reported on stderr)

# Python — needs `pip install jedi`; source roots are found from the imports
python tools/extractors/python_extractor.py <src_root> --name myproj [--source-root src] > out.json

# C# — needs the .NET 8 SDK; every .csproj under <src_root> (SDK-style and old .NET Framework)
cd tools/extractors/csharp && dotnet build -c Release -o /tmp/cs-extractor && \
  dotnet /tmp/cs-extractor/CsharpExtractor.dll <src_root> --name myproj > out.json
# old projects: reference assemblies and packages.config libraries are fetched from nuget.org
# into ~/.onelens/csharp-cache (--offline skips the fetch); ONELENS_CSHARP_DIAGNOSTICS=1 prints compile errors

# A component in several languages (an agent in Go + Python + C#): one export per
# extractor, merged into one graph (same fqn twice → the first part wins)
python tools/extractors/merge_exports.py --name myproj out.json go.json py.json cs.json

onelens call-tool onelens_import --export-path out.json --graph myproj --backend falkordblite --clear
```

Go FQNs use full import paths (`github.com/acme/agent/internal/server.Client#Do(context.Context)`),
because two packages may share a name. Go has implicit interfaces: the extractor
writes `IMPLEMENTS` for every project type that satisfies a project interface,
and `OVERRIDES` from its methods, so impact analysis fans out from an interface
call exactly as it does for Java. A `(T, error)` result is recorded as returning `T`.

Python calls Jedi cannot infer (about 16% on the agent) are left out, never guessed.

C# FQNs are `Namespace.Outer.Inner#Method(int,System.Collections.Generic.List<Ns.T>)`,
with `ref `/`out `/`in ` kept in the signature so overloads stay apart. Constructors
are `#TypeName(...)`, static constructors `#.cctor()`, top-level statements
`Program#<Main>$(string[])`. A type name declared in two projects (every project's
`Program`) gets the assembly name in front (`mtPoller.Program`), so the two do not
merge. Calls include `new`, `base(...)`/`this(...)`, method groups (`+= OnClick`,
`Task.Run(Work)`) and properties whose accessors have a body (`get_X()`/`set_X(v)`).
Interface implementations and `override`s become `OVERRIDES`. `[HttpGet]`-style
controller actions become Endpoints, with `[Route]` and `[controller]` resolved,
so PageRank and impact work as they do for Spring. COM references (`WUApiLib`) and
libraries not on nuget.org cannot be loaded off Windows: calls into them stay
unresolved and show up as compile errors in the stderr summary.

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
