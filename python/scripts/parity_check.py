#!/usr/bin/env python3
"""
Import parity gate — the regression net for the importer refactor (E5).

Builds a synthetic export exercising EVERY subsystem (core nodes, type-flow,
data-flow, enum dual-label, annotations, Spring, JPA, tests), imports it via
GraphLoader (full), then applies a delta via DeltaLoader, and asserts a fixed
set of invariants against the resulting FalkorDB-Lite graph.

Run BEFORE and AFTER any importer change. Output must be byte-identical.

    ~/.onelens/venv/bin/python python/scripts/parity_check.py

Exit 0 = all invariants hold. Non-zero = a divergence (prints the failing check).
The refactor MUST keep this green at every step.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from onelens.graph.db import create_backend
from onelens.importer.delta_loader import DeltaLoader
from onelens.importer.loader import GraphLoader

FULL = {
    "project": {"name": "parity"},
    "classes": [
        {"fqn": "com.x.UserService", "name": "UserService", "kind": "CLASS",
         "packageName": "com.x", "filePath": "a.java", "lineStart": 1, "lineEnd": 80},
        {"fqn": "com.x.User", "name": "User", "kind": "CLASS",
         "packageName": "com.x", "filePath": "u.java", "lineStart": 1, "lineEnd": 20},
        {"fqn": "com.x.UserRepo", "name": "UserRepo", "kind": "INTERFACE",
         "packageName": "com.x", "filePath": "r.java", "lineStart": 1, "lineEnd": 10},
        {"fqn": "com.x.Status", "name": "Status", "kind": "ENUM",
         "packageName": "com.x", "filePath": "s.java", "lineStart": 1, "lineEnd": 8},
        {"fqn": "com.x.UserServiceTest", "name": "UserServiceTest", "kind": "CLASS",
         "packageName": "com.x", "filePath": "t.java", "lineStart": 1, "lineEnd": 30},
    ],
    "methods": [
        {"fqn": "com.x.UserService#find(java.lang.String)", "name": "find",
         "classFqn": "com.x.UserService", "returnType": "com.x.User", "isConstructor": False,
         "filePath": "a.java", "lineStart": 5, "lineEnd": 20, "modifiers": ["public"],
         "throwsTypes": ["java.io.IOException"],
         "parameters": [{"name": "id", "type": "java.lang.String", "annotations": []}],
         "annotations": [{"fqn": "org.springframework.transaction.annotation.Transactional"}]},
        {"fqn": "com.x.UserServiceTest#testFind()", "name": "testFind",
         "classFqn": "com.x.UserServiceTest", "returnType": "void", "isConstructor": False,
         "filePath": "t.java", "lineStart": 5, "lineEnd": 12, "modifiers": ["public"],
         "throwsTypes": [], "parameters": [],
         "annotations": [{"fqn": "org.junit.jupiter.api.Test"}]},
    ],
    "fields": [
        {"fqn": "com.x.User#id", "name": "id", "classFqn": "com.x.User",
         "type": "java.lang.Long", "filePath": "u.java", "lineStart": 3},
        {"fqn": "com.x.UserService#repo", "name": "repo", "classFqn": "com.x.UserService",
         "type": "com.x.UserRepo", "filePath": "a.java", "lineStart": 3},
        {"fqn": "com.x.Status#ACTIVE", "name": "ACTIVE", "classFqn": "com.x.Status",
         "type": "com.x.Status", "filePath": "s.java", "lineStart": 2},
    ],
    "enumConstants": [
        {"fqn": "com.x.Status#ACTIVE", "name": "ACTIVE", "ordinal": 0, "enumFqn": "com.x.Status",
         "args": "[]", "argList": [], "argTypes": [], "filePath": "s.java", "lineStart": 2},
    ],
    "callGraph": [
        {"callerFqn": "com.x.UserServiceTest#testFind()",
         "calleeFqn": "com.x.UserService#find(java.lang.String)", "line": 7},
    ],
    "inheritance": [],
    "methodOverrides": [],
    "annotations": [
        {"targetFqn": "com.x.UserService#find(java.lang.String)", "targetKind": "METHOD",
         "annotationFqn": "org.springframework.web.bind.annotation.GetMapping",
         "attributes": "{}", "attrValues": {"value": "/users/{id}"}},
    ],
    "dataFlow": {
        "fieldAccesses": [
            {"accessorFqn": "com.x.UserService#find(java.lang.String)",
             "fieldFqn": "com.x.UserService#repo", "mode": "read", "line": 6},
        ],
        "instantiations": [
            {"methodFqn": "com.x.UserService#find(java.lang.String)",
             "classFqn": "java.util.ArrayList", "line": 8},
        ],
    },
    "spring": {
        "beans": [{"name": "userService", "classFqn": "com.x.UserService", "type": "com.x.UserService",
                   "scope": "singleton", "profile": "", "primary": True, "source": "annotation",
                   "activeProfiles": []}],
        "endpoints": [{"id": "GET:/users/{id}", "path": "/users/{id}", "httpMethod": "GET",
                       "controllerFqn": "com.x.UserService",
                       "handlerMethodFqn": "com.x.UserService#find(java.lang.String)"}],
        "injections": [], "autoConfigs": [],
    },
    "jpa": {
        "entities": [{"classFqn": "com.x.User", "tableName": "users", "schema": "public",
                      "columns": [{"fieldFqn": "com.x.User#id", "columnName": "id",
                                   "nullable": False, "unique": True}]}],
        "repositories": [{"classFqn": "com.x.UserRepo", "entityFqn": "com.x.User",
                          "derivedQueries": []}],
    },
    "tests": [{"methodFqn": "com.x.UserServiceTest#testFind()", "testClass": "com.x.UserServiceTest",
               "testKind": "unit", "testFramework": "junit5", "tags": [], "disabled": False,
               "activeProfiles": [], "usesMockito": False, "usesTestcontainers": False}],
    "mockBeans": [], "spyBeans": [],
}

# Delta: modify UserService (table rename users->app_users via JPA re-scan,
# find() stops instantiating ArrayList, adds a write to repo).
DELTA = {
    "project": {"name": "parity"},
    "deleted": {"classes": ["com.x.UserService"]},
    "upserted": {
        "classes": [{"fqn": "com.x.UserService", "name": "UserService", "kind": "CLASS",
                     "packageName": "com.x", "filePath": "a.java", "lineStart": 1, "lineEnd": 90}],
        "methods": [FULL["methods"][0]],
        "fields": [FULL["fields"][1]],
        "callGraph": [], "inheritance": [], "methodOverrides": [],
        "annotations": FULL["annotations"],
        "enumConstants": [],
        "dataFlow": {
            "fieldAccesses": [
                {"accessorFqn": "com.x.UserService#find(java.lang.String)",
                 "fieldFqn": "com.x.UserService#repo", "mode": "write", "line": 9}],
            "instantiations": [],
        },
    },
    "spring": FULL["spring"],
    "jpa": {"entities": [{"classFqn": "com.x.User", "tableName": "app_users", "schema": "public",
                          "columns": [{"fieldFqn": "com.x.User#id", "columnName": "id",
                                       "nullable": False, "unique": True}]}],
            "repositories": FULL["jpa"]["repositories"]},
    "tests": FULL["tests"], "mockBeans": [], "spyBeans": [],
}


def snapshot(db) -> dict:
    """Stable, order-independent fingerprint of the graph."""
    q = db.query
    out = {}
    for label in ("Class", "Method", "Field", "SpringBean", "Endpoint",
                  "JpaEntity", "JpaColumn", "JpaRepository", "EnumConstant", "TestCase"):
        out[f"node:{label}"] = q(f"MATCH (n:{label}) RETURN count(n) AS n")[0]["n"]
    for rel in ("CALLS", "HAS_METHOD", "HAS_FIELD", "RETURNS", "THROWS", "HAS_PARAMETER",
                "READS_FIELD", "WRITES_FIELD", "INSTANTIATES", "HAS_COLUMN", "REPOSITORY_FOR",
                "ANNOTATED_WITH", "HANDLES", "HAS_ENUM_CONSTANT", "TESTS"):
        out[f"edge:{rel}"] = q(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS n")[0]["n"]
    # Targeted property invariants.
    m = q("MATCH (m:Method {name:'find'}) RETURN m.visibility AS v, m.isTransactional AS t, "
          "m.paramCount AS p")
    out["find.visibility"] = m[0]["v"]; out["find.isTransactional"] = m[0]["t"]
    out["find.paramCount"] = m[0]["p"]
    out["User.labels"] = sorted(q("MATCH (c:Class {fqn:'com.x.User'}) RETURN labels(c) AS l")[0]["l"])
    out["ACTIVE.labels"] = sorted(q("MATCH (n {fqn:'com.x.Status#ACTIVE'}) RETURN labels(n) AS l")[0]["l"])
    tbl = q("MATCH (c:JpaEntity {fqn:'com.x.User'}) RETURN c.tableName AS t")
    out["User.tableName"] = tbl[0]["t"] if tbl else None
    out["attr_value"] = (q("MATCH (:Method {name:'find'})-[r:ANNOTATED_WITH]->"
                           "(:Annotation {name:'GetMapping'}) RETURN r.attr_value AS v") or [{"v": None}])[0]["v"]
    return out


def main() -> int:
    tmp = tempfile.mkdtemp()
    try:
        p = Path(tmp) / "parity-full.json"; p.write_text(json.dumps(FULL))
        db = create_backend("falkordblite", db_path=tmp, graph_name="parity")
        GraphLoader(db).load_full(p)
        full_snap = snapshot(db)

        dp = Path(tmp) / "parity-delta.json"; dp.write_text(json.dumps(DELTA))
        DeltaLoader(db).apply_delta(dp, graph_name="parity")
        delta_snap = snapshot(db)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Invariants (the contract the refactor must preserve).
    checks = [
        ("full: User dual-labeled", full_snap["User.labels"] == ["Class", "JpaEntity"]),
        ("full: ACTIVE dual-labeled", full_snap["ACTIVE.labels"] == ["EnumConstant", "Field"]),
        ("full: find transactional", full_snap["find.isTransactional"] is True),
        ("full: find public", full_snap["find.visibility"] == "public"),
        ("full: RETURNS present", full_snap["edge:RETURNS"] >= 1),
        ("full: THROWS present", full_snap["edge:THROWS"] >= 1),
        ("full: READS_FIELD present", full_snap["edge:READS_FIELD"] >= 1),
        ("full: INSTANTIATES present", full_snap["edge:INSTANTIATES"] >= 1),
        ("full: HAS_COLUMN present", full_snap["edge:HAS_COLUMN"] >= 1),
        ("full: TestCase labeled", full_snap["node:TestCase"] == 1),
        ("full: TESTS edge derived", full_snap["edge:TESTS"] >= 1),
        ("full: attr_value promoted", full_snap["attr_value"] == "/users/{id}"),
        ("full: table=users", full_snap["User.tableName"] == "users"),
        ("delta: User STILL dual-labeled (no demotion)", delta_snap["User.labels"] == ["Class", "JpaEntity"]),
        ("delta: table renamed app_users", delta_snap["User.tableName"] == "app_users"),
        ("delta: WRITES_FIELD now present", delta_snap["edge:WRITES_FIELD"] >= 1),
        ("delta: INSTANTIATES purged (was ArrayList)", delta_snap["edge:INSTANTIATES"] == 0),
        ("delta: TestCase still labeled", delta_snap["node:TestCase"] == 1),
        ("delta: find still transactional", delta_snap["find.isTransactional"] is True),
    ]
    print("=== FULL snapshot ==="); print(json.dumps(full_snap, indent=2, sort_keys=True))
    print("=== DELTA snapshot ==="); print(json.dumps(delta_snap, indent=2, sort_keys=True))
    failed = [name for name, ok in checks if not ok]
    print("\n=== CHECKS ===")
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if failed:
        print(f"\nPARITY FAILED: {len(failed)} check(s) — {failed}")
        return 1
    print(f"\nPARITY OK: {len(checks)} checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
