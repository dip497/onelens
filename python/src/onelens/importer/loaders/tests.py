"""TestLoader — owns both the full and delta test import paths.

Extracted from loader.py (_load_tests) and delta_loader.py (_replace_tests)
so the two paths cannot drift (the :TestCase dual-label demotion bug that
prompted this extraction).
"""

import logging

from onelens.importer.loaders.base import SubdocLoader

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 500


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


class TestLoader(SubdocLoader):
    json_key = "tests"

    def load_full(self, writer, progress, data: dict, wing: str) -> None:
        """
        Phase Q.code — tests as dual-label :Method:TestCase.

        Three things in order:
          1. Dual-label each test method by methodFqn and set its test-specific
             props (testKind, tags, disabled, …).
          2. Emit `(TestCase)-[:MOCKS]->(SpringBean)` / `-[:SPIES]->` edges from
             `@MockBean` / `@SpyBean` field bindings. Match SpringBean by
             classFqn (the target type).
          3. Derive `(TestCase)-[:TESTS]->(Method)` edges from direct CALLS
             where the target is NOT itself a TestCase. Depth-1 only — gets
             the production method the test directly invokes.

        If the export carries no tests, this is a no-op. Safe to call
        unconditionally.
        """
        tests = data.get("tests", []) or []
        mock_beans = data.get("mockBeans", []) or []
        spy_beans = data.get("spyBeans", []) or []

        if not tests and not mock_beans and not spy_beans:
            return

        if tests:
            # Stringify list props — FalkorDB stores them fine, but comma-joined
            # stays queryable via CONTAINS for skill-style patterns.
            prepped = []
            for t in tests:
                prepped.append({
                    "methodFqn": t.get("methodFqn", ""),
                    "testClass": t.get("testClass", ""),
                    "testKind": t.get("testKind", "unknown"),
                    "testFramework": t.get("testFramework", "unknown"),
                    "tags": ",".join(t.get("tags") or []),
                    "disabled": bool(t.get("disabled", False)),
                    "activeProfiles": ",".join(t.get("activeProfiles") or []),
                    "springBootApp": t.get("springBootApp") or "",
                    "usesMockito": bool(t.get("usesMockito", False)),
                    "usesTestcontainers": bool(t.get("usesTestcontainers", False)),
                    "displayName": t.get("displayName") or "",
                    "wing": wing,
                })
            writer.batch_add_label(
                progress, "Tests", prepped,
                base_label="Method", base_pk="fqn", pk_field="methodFqn",
                add_label="TestCase",
                props=["testClass", "testKind", "testFramework", "tags",
                       "disabled", "activeProfiles", "springBootApp",
                       "usesMockito", "usesTestcontainers", "displayName",
                       "wing"],
            )

        # MOCKS / SPIES: testClassFqn → beanClassFqn. Source is any method on
        # the test class that we labelled as :TestCase above; match by its
        # enclosing class. Easier: emit edge from the test CLASS → bean CLASS
        # via a lifted pattern — every TestCase on that class gets reach via
        # 1-hop pattern `(t:TestCase)<-[:HAS_METHOD]-(c:Class)-[:MOCKS]->(bean)`.
        # But skill ergonomics want `(t:TestCase)-[:MOCKS]->`. So lift:
        # emit `(testMethod)-[:MOCKS]->(bean)` for every test method in the class.
        # That blows up edges × methods. Pragmatic: emit on Class →
        # `MATCH (c:Class)-[:MOCKS]->(b:SpringBean)` — cheap, class-scoped.
        if mock_beans:
            mocks = [{"src": b["testClassFqn"], "dst": b["beanClassFqn"],
                      "field": b.get("fieldName", "")}
                     for b in mock_beans if b.get("testClassFqn") and b.get("beanClassFqn")]
            writer.batch_edges_with_props(
                progress, "MOCKS", mocks,
                "Class", "fqn", "SpringBean", "classFqn",
                ["field"],
            )

        if spy_beans:
            spies = [{"src": b["testClassFqn"], "dst": b["beanClassFqn"],
                      "field": b.get("fieldName", "")}
                     for b in spy_beans if b.get("testClassFqn") and b.get("beanClassFqn")]
            writer.batch_edges_with_props(
                progress, "SPIES", spies,
                "Class", "fqn", "SpringBean", "classFqn",
                ["field"],
            )

        # Derived :TESTS edge — single Cypher pass. Direct CALLS where target
        # isn't itself a test. Matches how users ask "what does this test
        # exercise" without forcing a transitive traversal at query time.
        if tests:
            try:
                writer.db.execute(
                    "MATCH (t:TestCase)-[:CALLS]->(m:Method) "
                    "WHERE NOT m:TestCase "
                    "MERGE (t)-[:TESTS]->(m)"
                )
                logger.info("Derived :TESTS edges from direct CALLS")
            except Exception as e:
                logger.warning("Derived :TESTS pass failed: %s", e)

    def apply_delta(self, writer, data: dict, wing: str) -> None:
        """Strip + re-apply :TestCase dual-label + MOCKS/SPIES/TESTS edges.

        Parity with loader.py::_load_tests. A modified test class DETACH-deletes
        and re-MERGEs as a plain :Method, losing :TestCase + every test edge;
        and _replace_spring wipes SpringBeans, destroying MOCKS/SPIES targets.
        Full strip + re-derive guarantees parity. Must run after Spring replace
        (MOCKS→SpringBean) and the CALLS upsert (TESTS derives from CALLS).
        """
        tests = data.get("tests", []) or []
        mock_beans = data.get("mockBeans", []) or []
        spy_beans = data.get("spyBeans", []) or []

        writer.db.execute("MATCH (m:TestCase) REMOVE m:TestCase")
        writer.db.execute("MATCH ()-[r:MOCKS|SPIES|TESTS]->() DELETE r")

        if tests:
            prepped = [{
                "methodFqn": t.get("methodFqn", ""), "testClass": t.get("testClass", ""),
                "testKind": t.get("testKind", "unknown"),
                "testFramework": t.get("testFramework", "unknown"),
                "tags": ",".join(t.get("tags") or []),
                "disabled": bool(t.get("disabled", False)),
                "activeProfiles": ",".join(t.get("activeProfiles") or []),
                "springBootApp": t.get("springBootApp") or "",
                "usesMockito": bool(t.get("usesMockito", False)),
                "usesTestcontainers": bool(t.get("usesTestcontainers", False)),
                "displayName": t.get("displayName") or "", "wing": wing,
            } for t in tests if t.get("methodFqn")]
            for batch in _chunks(prepped, _CHUNK_SIZE):
                writer.db.execute("""
                    UNWIND $batch AS item
                    MATCH (m:Method {fqn: item.methodFqn})
                    SET m:TestCase, m.testClass = item.testClass,
                        m.testKind = item.testKind, m.testFramework = item.testFramework,
                        m.tags = item.tags, m.disabled = item.disabled,
                        m.activeProfiles = item.activeProfiles,
                        m.springBootApp = item.springBootApp,
                        m.usesMockito = item.usesMockito,
                        m.usesTestcontainers = item.usesTestcontainers,
                        m.displayName = item.displayName, m.wing = item.wing
                """, {"batch": batch})

        for rel, bindings in (("MOCKS", mock_beans), ("SPIES", spy_beans)):
            items = [{"src": b["testClassFqn"], "dst": b["beanClassFqn"],
                      "field": b.get("fieldName", "")}
                     for b in bindings if b.get("testClassFqn") and b.get("beanClassFqn")]
            for batch in _chunks(items, _CHUNK_SIZE):
                writer.db.execute(
                    f"UNWIND $batch AS edge "
                    f"MATCH (c:Class {{fqn: edge.src}}), (b:SpringBean {{classFqn: edge.dst}}) "
                    f"MERGE (c)-[:{rel} {{field: edge.field}}]->(b)",
                    {"batch": batch}
                )

        if tests:
            try:
                writer.db.execute(
                    "MATCH (t:TestCase)-[:CALLS]->(m:Method) "
                    "WHERE NOT m:TestCase MERGE (t)-[:TESTS]->(m)"
                )
            except Exception as e:
                logger.warning("Delta derived :TESTS pass failed: %s", e)
        logger.info("Tests replaced: %d test methods (wing=%s)", len(tests), wing)
