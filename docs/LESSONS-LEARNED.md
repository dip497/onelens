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
