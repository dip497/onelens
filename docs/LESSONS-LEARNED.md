# Lessons Learned

What was tried, what failed, and what to avoid. Read this before making changes.

## Architecture Decisions

### Why IntelliJ PSI, not tree-sitter
- **Tried**: Tree-sitter Java parser (custom Python implementation). Got 550K call edges but ~50% were ambiguous (multiple classes with same method name, no type resolution).
- **Problem**: `service.getName()` — tree-sitter doesn't know which class `service` is. Picks the first match. Wrong 50% of the time.
- **Solution**: IntelliJ's PSI engine does full type resolution. `PsiMethodCallExpression.resolveMethod()` gives the exact target. 100% accurate.
- **Lesson**: Don't try to build a type resolver in Python. Java's generics, overloads, and polymorphism make it nearly impossible without a real compiler.

### Why not scip-java or JavaParser
- **scip-java**: Requires a successful Maven build of the project. Many large projects have build issues (missing dependencies, proprietary repos). Also, scip-java is a Sourcegraph tool — extra dependency.
- **JavaParser**: No type resolution. Same problem as tree-sitter — can parse AST but can't resolve method calls to their targets.
- **Eclipse JDT**: Could work headlessly but requires 500MB+ of JARs and complex initialization. IntelliJ is already running with the project indexed.
- **Lesson**: If IntelliJ is already open with the project, use its index. Don't rebuild what it already computed.

### Why FalkorDB, not KuzuDB
- **KuzuDB was chosen first**: Embedded, no Docker, Cypher support. Seemed ideal.
- **Problem**: KuzuDB was archived by its maintainers in 2026. They pivoted to a new project.
- **FalkorDB wins**: Docker-based but gives a visual browser (localhost:3001). Active project. Same Cypher syntax.
- **Lesson**: Check if a project is actively maintained before building on it.

### Why plugin writes JSON, not directly to graph DB
- **Tried**: Having the plugin call Python CLI to import directly. Failed because IntelliJ's process doesn't have the same PATH as the user's shell.
- **Alternative considered**: Embedding FalkorDB Java client in the plugin. But that locks you to one graph DB.
- **Solution**: Plugin writes JSON → Python imports. Decoupled, backend-swappable.
- **Lesson**: Keep the plugin as a pure exporter. Let Python handle the graph DB complexity.

## Technical Pitfalls

### IntelliJ ReadAction freezes
- **Problem**: Wrapping 10K class iterations in a single `ReadAction.compute{}` freezes the IDE for 3-4 minutes.
- **Fix**: Process each class in its own `ReadAction.run{}` with `ProgressManager.checkCanceled()` between them. IDE stays responsive.
- **Rule**: Never hold a ReadAction for more than a few milliseconds. Break into per-class or per-file chunks.

### IntelliJ PATH differs from shell
- **Problem**: `ProcessBuilder("uv", "venv", ...)` fails inside IntelliJ because `~/.local/bin` isn't in IntelliJ's PATH.
- **Fix**: `PythonEnvManager.kt` searches common absolute paths (`~/.local/bin/uv`, `/usr/local/bin/python3`, etc.) instead of relying on `which`.
- **Rule**: Never assume tools are on PATH when running from IntelliJ. Use absolute path lookup.

### PsiClass.methods includes inherited methods
- **Problem**: `psiClass.methods` returns ALL methods including inherited ones from parent classes. Their `textOffset` is from the parent's file, causing `IndexOutOfBoundsException` when used with the child's document.
- **Fix**: Filter with `method.containingClass != psiClass` to skip inherited methods. They'll be collected when processing the parent class.
- **Rule**: Always check `containingClass` when iterating PSI methods/fields.

### findDeepestSuperMethods vs findSuperMethods
- **Problem**: `findDeepestSuperMethods()` only returns the ROOT of the override chain. If you have Interface → Abstract → Concrete, it returns only Interface, skipping Abstract.
- **Fix**: Use `findSuperMethods(false)` which returns IMMEDIATE parents. The full chain builds naturally when processing each class.
- **Rule**: Use `findSuperMethods()` for override edges, not `findDeepestSuperMethods()`.

### FalkorDB header format
- **Problem**: `result.header` returns `[[1, 'column_name'], ...]` not `['column_name', ...]`. Caused `TypeError: unhashable type: 'list'` when building dicts.
- **Fix**: Extract column name: `columns = [h[1] if isinstance(h, list) else h for h in result.header]`
- **Rule**: Always check the actual format of query results. Don't assume.

### FalkorDB variable-length paths
- **Problem**: `MATCH (a)-[:EXTENDS*1..3]->(b)` throws `Type mismatch: expected Path or Null but was List` in FalkorDB.
- **Fix**: Use explicit multi-hop: `MATCH (a)-[:EXTENDS]->(b)-[:EXTENDS]->(c)` or multiple queries.
- **Rule**: Avoid `*` in FalkorDB relationship patterns. Use explicit hops.

### UNWIND batching vs individual queries
- **Problem**: 800K individual MERGE queries took hours. Network roundtrip per query is the bottleneck.
- **Fix**: `UNWIND $batch AS item CREATE (n:Label {pk: item.pk}) SET ...` processes 1000 items per query. 30 seconds total.
- **Rule**: Always use UNWIND for bulk operations. Batch size: 1000 for nodes, 500 for edges.

### UTF-8 byte offsets in tree-sitter (historical)
- **Problem**: Tree-sitter returns byte offsets, but Python strings are character-indexed. Files with non-ASCII characters (e.g., → arrow) had shifted offsets.
- **Fix**: `content.encode('utf-8')[start:end].decode('utf-8')`
- **Note**: No longer relevant since we moved to IntelliJ PSI, but important if tree-sitter is used elsewhere.

### External library call targets need stub nodes
- **Problem**: Call edges like `YourMethod → jersey.Client#target()` existed in the export JSON, but the library method had no node in the graph. FalkorDB's MATCH silently skipped them — 216K out of 605K CALLS edges were lost.
- **Fix**: During Python import, scan all callee FQNs not in project methods. Create stub Class/Method nodes with `external: true`. Now all 605K edges connect.
- **Gotcha**: Some "missing" callees are actually project classes with implicit default constructors that PSI doesn't export. These should be `external: false`, not `true`. Split by checking if the class FQN exists in the project class set.
- **Rule**: After import, verify `MATCH ()-[r:CALLS]->() RETURN count(r)` matches the export's `callEdgeCount`. If not, stubs are missing.

### Don't try to index transitive library dependencies in the graph
- **Tried**: User asked "blast radius of upgrading Jersey?" — graph showed zero usage. But Jira SDK uses Jersey internally, and the project overrides the Jersey version in pom.xml.
- **Problem**: The graph only sees your code → library calls. It can't see library → library dependencies (Jira → Jersey).
- **Lesson**: This is a dependency management problem, not a code graph problem. Use `mvn dependency:tree` for transitive deps. Don't bolt dependency resolution onto the graph — Maven/Gradle already solve it. Stay focused: OneLens = code intelligence, not dependency management.

## What NOT to do

1. **Don't query 57K methods one-by-one over HTTP/MCP**. We tried calling JetBrains MCP plugin's `ide_call_hierarchy` for each method. It crashed after hours. The MCP plugin is designed for interactive use, not bulk export.

2. **Don't delete all CALLS edges before rebuilding them**. The old Phase 2 MCP enhancer did `DELETE ALL CALLS` then rebuilt via MCP. When MCP crashed mid-way, all edges were lost. Always add/update incrementally, never delete-all-first.

3. **Don't try to run IntelliJ PSI APIs outside IntelliJ**. They only work inside the JVM process. You can't "copy the code" to Python. The plugin IS the bridge.

4. **Don't use `psiClass.interfaces`** for "directly implemented interfaces". It returns ALL interfaces including inherited ones. Use `psiClass.implementsListTypes` and resolve each.

5. **Don't rely on `ChangeListManager` alone for delta detection**. It only shows uncommitted changes. Use `git diff` for committed changes since last export, plus ChangeListManager for uncommitted ones.

6. **Don't use snake_case property names in Cypher queries**. The JSON export uses camelCase (`classFqn`, `filePath`, `httpMethod`, `lineStart`). FalkorDB stores properties exactly as imported. `m.class_fqn` returns null — use `m.classFqn`.

7. **Don't use variable-length paths in FalkorDB queries** (e.g., `[:CALLS*1..3]`). It throws `Type mismatch: expected Path or Null but was List`. Use explicit multi-hop with UNION instead.

8. **Don't use f-string interpolation in Cypher queries**. Use parameterized queries (`$param`) to prevent Cypher injection. Class names with quotes will break f-string queries.

9. **Don't forget external stubs in delta imports**. Full import creates stub nodes for library methods. Delta import must also create stubs for any new external call targets, otherwise CALLS edges silently fail.

10. **Don't append to file→class mapping in delta state**. When a file is re-exported, clear its old mapping first, then rebuild from the fresh collection. Otherwise stale FQNs accumulate and cause wrong deletions.

11. **Inner class constructors**: `com.example.Outer$Inner` has constructor named `Inner`, not `Outer$Inner`. Split on `$` to get the simple name when checking `is_constructor`.

## Retrieval & MCP migration lessons (2026-04)

12. **Two code paths MUST write the same ChromaDB metadata schema**. We had `_mine_methods` writing `{wing, room, hall, importance, filed_at, fqn, type}` and `_method_metadata` (delta upsert) writing `{graph, class, file, line, fqn, type}`. After any delta upsert, those drawers lost `wing` — and the semantic searcher filters on `wing=<graph_name>`. Silent drift: upserted drawers disappear from all scoped queries. **Always align schemas across full and delta paths, including when introducing new helpers.**

13. **Don't cascade-delete by metadata key you never wrote**. First attempt at `delete_methods_of_classes` used `where={"class": {"$in": ...}}` but no drawer actually had a `class` metadata field. Silent no-op — removed classes accumulated dead method drawers until the next full `--context` import. **Cascade by ID prefix instead** (`method:<classFqn>#*`): works across any historical metadata schema.

14. **`--clear` on a delta wipes the graph**. When we unified plugin dispatch to one `onelens import_graph` call, we kept `--clear` unconditional. Every delta auto-sync started wiping the graph and re-importing just the delta (a tiny subset). Production graph would shrink with every file save. Pass `--clear` only on full imports.

15. **CLI command rename across layers breaks the whole plugin**. The FastMCP migration renamed `onelens import` → `onelens import-graph`. The plugin still shelled out to `"import"`. Every sync failed with "command not found" that surfaced only in `idea.log`. Lesson: **any CLI rename needs a plugin integration test in CI** (we added `CodeMiner` API-surface guard + Kotlin compile gate to catch this class of bug).

16. **`BranchChangeListener` is not a stable IntelliJ public API**. We tried to wire a git branch-change listener via `com.intellij.dvcs.branch.BranchChangeListener` — unresolved at compile time. The class path varies by bundle and IntelliJ version. The VFS `BulkFileListener` already catches the file changes that `git checkout` / pull / rebase produce in the working tree, so the branch listener was redundant. Revert; don't chase unstable hooks.

17. **FastMCP client is ~4s of eager imports**. Every `onelens <cmd>` invocation pays this even after module load — the library is not optimized for CLI usage. The daemon mode helps for warm semantic queries but doesn't save the per-call Python startup tax. If we ever need sub-second CLI latency, the path is a stdio-only MCP runner, not optimizing FastMCP.

18. **Embedding score threshold = 0.02 (mxbai cross-encoder) is the gibberish floor**. Below that, the reranker is effectively random. Empty result = real no-match. Above 0.7 = strong hit; 0.03-0.7 is the honest "some relevance" band. Don't retry failed retrievals with synonym expansion — it was already gibberish.

19. **PageRank boost must multiply already-matched hits, not feed RRF as a third source**. First attempt: add top-100 PR-scored methods as an RRF source. Broke every concept query because semantically irrelevant but topologically central methods (e.g., `Logger.info`, `String.equals`) leaked into results. Fix: multiplicative boost on hits that already matched FTS/semantic (`score *= 1 + 0.3 * normalized_pr`). Bounded, can't promote irrelevant.

20. **Don't cache `mine(path)` across delta calls**. Full `CodeMiner.mine` expects a full export JSON with all indexes built. Delta data is a subset — calling `mine(path)` on a delta file re-reads it as a full export and produces wrong results. Route delta context through `apply_delta(context=True)` → `mine_upserts`, not through `mine`.

21. **Client names creep into code via examples**. Internal class prefixes and customer-specific paths ended up in docstrings, comments, and one README example. Before any OSS push: `grep -rIn "<client-name>"` across `**/*.{py,kt,md,yaml,toml}` with every identifier that ever appeared in a benchmark fixture. Benchmark YAMLs also had real graph names — gitignored for the same reason.

22. **MCP is optional, not universal**. Claude Code + OpenCode have bash tools; the skill + `onelens <cmd>` shell invocation is enough. MCP only helps editors that can't shell reliably (Cursor Agent / Codex / Windsurf). Don't bundle an MCP install path into the plugin if the plugin's target user is a Claude Code user — it's 40s of model-load overhead and two extra config files they'll never use.

23. **Plugin skill install via JAR resource, not repo copy**. The plugin bundles `skills/onelens/SKILL.md` into its jar via Gradle `processResources` (`from("${project.rootDir.parent}/skills")`). `InstallSkillAction.loadBundledSkill()` reads it via classpath `/skills/onelens/SKILL.md`. Users don't need the repo checked out — one action copies the skill to `~/.claude/skills/`. Verify with `unzip -p plugin.zip inner.jar | unzip -l - | grep SKILL`.

24. **Review caught two silent bugs after imports-resolve test passed**. Always have an independent reviewer (human or agent) re-read the diff. "Imports resolve + benchmark passes" is necessary, not sufficient — metadata schema drift and `class`-key cascade bugs both passed initial checks. Cost of skipping a real review was zero measurable; finding them 30 minutes later cost only the time to fix.
