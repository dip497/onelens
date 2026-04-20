"""
SQL miner (Phase C6).

Walks configured paths for `.sql` files, parses with sqlglot (Postgres dialect,
IGNORE error level so unparseable vendor extensions don't kill the batch),
and emits structured file + statement dicts the loader turns into
`:SqlQuery` / `:Migration` / `:SqlStatement` nodes.

Two kinds:
  - migration → Flyway files (`V<version>__<desc>.sql`, `R__<desc>.sql`)
  - query     → Everything else matched by `sql.queries` globs

Per-statement extraction: each `.sql` file can hold multiple statements
separated by `;`. Each becomes a `SqlStatement` with its own `sql` body,
`opKind` (SELECT / CREATE_TABLE / ALTER_TABLE / DROP_TABLE / UPDATE / INSERT /
DELETE), and a list of referenced table names. Table names are lower-cased
for case-insensitive JpaEntity.tableName matching on the loader side.

Body size cap: 200 KB per file (and per statement). Protects against truly
pathological generated files; a large project's largest legit file is <40 KB.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

try:
    import sqlglot
    from sqlglot import exp
except Exception:  # pragma: no cover - sqlglot is a declared dep
    sqlglot = None
    exp = None

logger = logging.getLogger(__name__)

# sqlglot logs WARN-level messages for every statement it can't parse
# ("contains unsupported syntax. Falling back to parsing as a 'Command'.")
# and "Failed to annotate badly formed binary expression". These are not
# failures — the miner already keeps those statements as `opKind:OTHER`.
# The user-visible noise adds nothing, so we pin the sqlglot logger to
# ERROR-only. One-time setup on module import.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

MAX_BODY = 200 * 1024  # 200 KB per file / per statement

# Flyway filename: `V<version>__<description>.sql` (versioned) or
# `R__<description>.sql` (repeatable). Version separators: `.`, `_`.
_FLYWAY_RE = re.compile(
    r'^(?P<prefix>[VR])(?P<version>[\d_.]*)__(?P<description>.+?)\.sql$',
    re.IGNORECASE,
)


@dataclass
class StatementOut:
    index: int
    sql: str
    opKind: str                # SELECT | CREATE_TABLE | ALTER_TABLE | DROP_TABLE | UPDATE | INSERT | DELETE | OTHER
    # Default-empty lists so every construction path stays valid without
    # caller having to remember to pass them (was a regression after adding
    # columnRefs — StatementOut from a branch that didn't pass it crashed).
    tableNames: list[str] = field(default_factory=list)
    # (tableName, columnName) pairs, both lower-cased. Resolved via sqlglot's
    # scope builder so `r.priorityId` → `('request', 'priorityid')`. Unqualified
    # columns in single-FROM statements are attributed to that one table; in
    # multi-table joins we drop unqualified refs rather than guess wrong.
    columnRefs: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class FileOut:
    path: str                  # workspace-relative
    absPath: str               # absolute — useful for diagnostics
    filename: str
    kind: str                  # "migration" | "query"
    body: str                  # truncated if > MAX_BODY
    version: Optional[str]     # migrations only (e.g. "1.2.3")
    description: Optional[str] # migrations only
    dbKind: Optional[str]      # migrations only, inferred from path segment: "master" | "tenants" | None
    statements: list[StatementOut]


def mine(
    roots: list[Path],
    migration_dirs: list[Path],
    query_globs: list[str],
) -> list[FileOut]:
    """
    Discover + parse all in-scope SQL files. Returns a flat list of FileOut.
    Caller (loader) transforms to graph nodes/edges.
    """
    if sqlglot is None:
        logger.warning("sqlglot not importable — SQL indexing skipped")
        return []

    out: list[FileOut] = []

    # Migrations.
    for mdir in migration_dirs:
        for sql_path in _walk_sql(mdir):
            f = _mine_file(sql_path, roots, kind="migration")
            if f is not None:
                out.append(f)

    # Custom queries. Globs are resolved against each root.
    seen: set[Path] = set()
    for root in roots:
        for glob in query_globs:
            for sql_path in root.glob(glob):
                if not sql_path.is_file() or sql_path.suffix.lower() != ".sql":
                    continue
                rp = sql_path.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                f = _mine_file(sql_path, roots, kind="query")
                if f is not None:
                    out.append(f)

    return out


# ── per-file parse ─────────────────────────────────────────────────────

def _mine_file(path: Path, roots: list[Path], kind: str) -> Optional[FileOut]:
    try:
        body = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        logger.debug("SQL miner: read failed for %s: %s", path, e)
        return None

    if len(body) > MAX_BODY:
        body = body[:MAX_BODY] + f"\n\n-- [onelens] truncated, original was {len(body)} bytes --"

    rel = _relative_to_roots(path, roots)

    # Parse into statements. sqlglot.parse returns list of Expressions (one per
    # statement separated by `;`). Unparseable statements come back as None —
    # we keep them as :SqlStatement with opKind=OTHER and sql=raw text so the
    # user still sees them in the graph.
    statements = _parse_statements(body)

    version: Optional[str] = None
    description: Optional[str] = None
    if kind == "migration":
        m = _FLYWAY_RE.match(path.name)
        if m:
            v = (m.group("version") or "").replace("_", ".")
            # Flyway supports `R__` (repeatable, no version) alongside `V`.
            version = v if v else None
            description = m.group("description").replace("_", " ")

    # Multi-tenant hint: `db/migration/master/V1__foo.sql` → dbKind=master.
    db_kind = _infer_db_kind(path) if kind == "migration" else None

    filename = path.name

    return FileOut(
        path=rel,
        absPath=str(path.resolve()),
        filename=filename,
        kind=kind,
        body=body,
        version=version,
        description=description,
        dbKind=db_kind,
        statements=statements,
    )


def _parse_statements(body: str) -> list[StatementOut]:
    """
    Split + parse a SQL file. We don't naively split on `;` — that breaks on
    literals. Let sqlglot do it via `parse` (plural) with error_level=IGNORE.
    Falls back to naive split only if sqlglot crashes entirely (rare).
    """
    out: list[StatementOut] = []
    try:
        trees = sqlglot.parse(body, dialect="postgres", error_level=sqlglot.ErrorLevel.IGNORE)
    except Exception as e:
        logger.debug("sqlglot.parse crashed: %s — fallback to raw split", e)
        return _fallback_split(body)

    for i, tree in enumerate(trees):
        if tree is None:
            # sqlglot couldn't understand this chunk (custom PG extension, for
            # ex.) but parse didn't raise. Keep it as opaque text so the user
            # still sees it in the graph.
            out.append(
                StatementOut(
                    index=i,
                    sql="-- [onelens] statement couldn't be parsed, raw text omitted --",
                    opKind="OTHER",
                    tableNames=[],
                    columnRefs=[],
                )
            )
            continue

        sql = tree.sql(dialect="postgres")
        if len(sql) > MAX_BODY:
            sql = sql[:MAX_BODY] + "\n-- [onelens] truncated --"

        op_kind = _classify(tree)
        tables = _extract_tables(tree)
        columns = _extract_columns(tree)
        out.append(StatementOut(
            index=i, sql=sql, opKind=op_kind,
            tableNames=tables, columnRefs=columns,
        ))

    return out


def _fallback_split(body: str) -> list[StatementOut]:
    """Used only when sqlglot crashes on the whole file. Rough but deterministic."""
    out: list[StatementOut] = []
    chunks = [c.strip() for c in body.split(";") if c.strip()]
    for i, chunk in enumerate(chunks):
        out.append(StatementOut(
            index=i, sql=chunk, opKind="OTHER", tableNames=[], columnRefs=[],
        ))
    return out


def _extract_columns(tree) -> list[tuple[str, str]]:
    """
    Return `[(tableName, columnName)]` pairs, both lower-cased.

    Resolution:
      1. Qualified refs (`r.createdTime`) — resolve alias via sqlglot's scope
         builder. Subqueries get their own scope, walked recursively.
      2. Unqualified refs (`createdTime`) — attribute to the single FROM table
         if the scope has exactly one source. Drop otherwise (ambiguous).

    DDL (CREATE/ALTER TABLE) columns aren't included here — those are emitted
    separately via the CREATES_TABLE / ALTERS_TABLE edges (column-level DDL
    tracking is a larger schema-evolution feature deferred to C6.1).
    """
    # Import here so the module still imports when sqlglot is missing.
    try:
        from sqlglot.optimizer.scope import build_scope
    except Exception:
        return []

    out: dict[tuple[str, str], None] = {}

    def _process_scope(scope):
        if scope is None:
            return
        # Map alias → (Table).name for THIS scope level.
        alias_to_table: dict[str, str] = {}
        single_source_name: Optional[str] = None
        src_table_count = 0
        for alias, source in (scope.sources or {}).items():
            if isinstance(source, exp.Table):
                alias_to_table[alias] = source.name.lower()
                if src_table_count == 0:
                    single_source_name = source.name.lower()
                src_table_count += 1
        if src_table_count != 1:
            single_source_name = None

        # Every column node inside this scope's expression
        for col in scope.expression.find_all(exp.Column):
            # Skip columns that belong to a subscope — each subscope handles its own.
            # (build_scope yields them too; filter by scope containment.)
            # The cheap way: check col.parent chain for a nested SELECT.
            if _column_in_subscope(col, scope):
                continue

            name = (col.name or "").strip().lower()
            if not name:
                continue
            alias = col.table
            if alias:
                tbl = alias_to_table.get(alias)
                if tbl:
                    out[(tbl, name)] = None
                continue
            # Unqualified — only bind when there's exactly one source.
            if single_source_name:
                out[(single_source_name, name)] = None

    try:
        root_scope = build_scope(tree)
    except Exception:
        return []
    if root_scope is None:
        return []
    _process_scope(root_scope)
    # Walk nested scopes (subqueries, CTEs).
    try:
        for sub in root_scope.subscopes:
            _process_scope(sub)
    except Exception:
        pass

    return list(out.keys())


def _column_in_subscope(col, scope) -> bool:
    """True if this column belongs to a nested SELECT/subquery inside `scope`."""
    node = col.parent
    # Scope.expression is the SELECT/Union at this level.
    stop = scope.expression
    while node is not None:
        if node is stop:
            return False
        if isinstance(node, exp.Select) or isinstance(node, exp.Subquery):
            # Nested SELECT that isn't the stop node — different scope.
            return True
        node = node.parent
    return False


def _classify(tree) -> str:
    """Map a parsed expression to our opKind vocabulary."""
    if isinstance(tree, exp.Select):
        return "SELECT"
    if isinstance(tree, exp.Insert):
        return "INSERT"
    if isinstance(tree, exp.Update):
        return "UPDATE"
    if isinstance(tree, exp.Delete):
        return "DELETE"
    if isinstance(tree, exp.Create):
        kind = (tree.args.get("kind") or "").upper()
        if kind in ("TABLE", "EXTERNAL TABLE"):
            return "CREATE_TABLE"
        if kind == "INDEX":
            return "CREATE_INDEX"
        if kind in ("VIEW", "MATERIALIZED VIEW"):
            return "CREATE_VIEW"
        if kind == "SCHEMA":
            return "CREATE_SCHEMA"
        return f"CREATE_{kind}".rstrip("_") if kind else "CREATE"
    if isinstance(tree, exp.Alter):
        return "ALTER_TABLE"
    if isinstance(tree, exp.Drop):
        kind = (tree.args.get("kind") or "").upper()
        return f"DROP_{kind}".rstrip("_") if kind else "DROP"
    # sqlglot >=25 renamed TRUNCATE to Command with kind="TRUNCATE" on some
    # versions; guard with getattr so we survive both.
    truncate_cls = getattr(exp, "Truncate", None) or getattr(exp, "TruncateTable", None)
    if truncate_cls is not None and isinstance(tree, truncate_cls):
        return "TRUNCATE"
    # Fall-through for everything else (COPY, COMMENT ON, etc.)
    return "OTHER"


def _extract_tables(tree) -> list[str]:
    """
    Return distinct table names (lower-cased) referenced by the statement.
    For CREATE/ALTER/DROP, targets the resource itself. For SELECT/UPDATE/
    DELETE/INSERT, every `exp.Table` in the subtree. De-duped preserving
    first-seen order.
    """
    seen: dict[str, None] = {}

    def _push(name: str | None):
        if not name:
            return
        key = name.lower()
        if key not in seen:
            seen[key] = None

    # CREATE TABLE / ALTER TABLE / DROP TABLE — the operand lives on `this`.
    if isinstance(tree, (exp.Create, exp.Alter, exp.Drop)):
        target = tree.this
        if isinstance(target, exp.Table):
            _push(target.name)
        elif isinstance(target, exp.Schema):
            inner = target.this
            if isinstance(inner, exp.Table):
                _push(inner.name)

    # Any SELECT/INSERT/UPDATE/DELETE — scan every Table node below.
    for t in tree.find_all(exp.Table):
        _push(t.name)

    return list(seen.keys())


# ── path helpers ───────────────────────────────────────────────────────

def _walk_sql(directory: Path) -> Iterable[Path]:
    for p in directory.rglob("*.sql"):
        if p.is_file():
            yield p


def _relative_to_roots(path: Path, roots: list[Path]) -> str:
    p = path.resolve()
    for r in roots:
        try:
            return str(p.relative_to(r.resolve()))
        except ValueError:
            continue
    return str(p)


def _infer_db_kind(path: Path) -> Optional[str]:
    """Look for `/master/` or `/tenants/` segment in the path."""
    parts = [s.lower() for s in path.parts]
    if "master" in parts:
        return "master"
    if "tenants" in parts or "tenant" in parts:
        return "tenants"
    return None
