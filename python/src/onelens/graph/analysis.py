"""High-level impact analysis functions."""

from onelens.graph.db import GraphDB
from onelens.graph import queries


def get_blast_radius(db: GraphDB, file_path: str) -> list[dict]:
    """Get all code affected by changes to a file."""
    cypher, params = queries.blast_radius(file_path)
    return db.query(cypher, params)


def get_callers(db: GraphDB, method_fqn: str, depth: int = 2) -> list[dict]:
    """Get all callers of a method."""
    cypher, params = queries.find_callers(method_fqn, depth)
    return db.query(cypher, params)


def get_callees(db: GraphDB, method_fqn: str, depth: int = 2) -> list[dict]:
    """Get all callees of a method."""
    cypher, params = queries.find_callees(method_fqn, depth)
    return db.query(cypher, params)


def search_code(db: GraphDB, term: str, node_type: str = "") -> list[dict]:
    """Full-text search across the knowledge graph.

    Runs separate queries per node type and merges results,
    because FalkorDB may not support UNION with CALL...YIELD.

    Without including Vue / JS labels the hybrid retrieval FTS source
    returns empty on a frontend-only graph — RRF collapses to a single-
    source ranking whose top score is `1/(60+0) ≈ 0.0167`. That matches
    the exact score floor we observed on the Vue 3 dogfood (all hits
    clustered at 0.016-0.017). Per-type failures are swallowed so the
    list stays a superset — missing FTS indexes on a JVM-only graph
    don't short-circuit the JVM path.
    """
    results = []
    types_to_search = [node_type] if node_type else [
        # JVM (Spring Boot)
        "class", "method", "endpoint",
        # Vue 3 + JS business-logic layer
        "component", "composable", "store", "route", "apicall",
        "jsmodule", "jsfunction",
    ]

    for nt in types_to_search:
        cypher, params = queries.search(term, nt)
        try:
            results.extend(db.query(cypher, params))
        except Exception:
            pass  # FTS index may not exist for this type yet
    return results


def get_entry_points(db: GraphDB) -> list[dict]:
    """List all entry points in the codebase."""
    cypher, params = queries.list_entry_points()
    return db.query(cypher, params)


def _is_trivial_accessor(method_name: str, fqn: str) -> bool:
    """Check if method is a simple getter/setter (0-1 params, name starts with get/set/is)."""
    if not (method_name.startswith("get") or method_name.startswith("set") or method_name.startswith("is")):
        return False
    # Count params from FQN: Class#method(P1,P2) — count commas inside parens
    if "#" in fqn and "(" in fqn:
        params_str = fqn.split("(", 1)[1].rstrip(")")
        param_count = 0 if not params_str else params_str.count(",") + 1
        return param_count <= 1
    return True


def _compact_trace(results: list[dict], include_external: bool = False) -> list[dict]:
    """Deduplicate, filter externals and trivial accessors, and compact trace results."""
    seen = set()
    out = []
    for r in sorted(results, key=lambda x: (x.get("depth", 0), x.get("className", ""))):
        fqn = r.get("fqn", "")
        depth = r.get("depth", 0)
        key = (fqn, depth)
        if key in seen:
            continue
        seen.add(key)

        # Skip external library methods unless requested
        if not include_external and r.get("external") is True:
            continue

        # Skip trivial getters/setters at depth 2+ (reduce noise)
        method_name = r.get("method", "")
        if depth >= 2 and _is_trivial_accessor(method_name, fqn):
            continue

        # Compact: short class name, short param types, just filename
        class_fqn = r.get("className", "")
        short_class = class_fqn.rsplit(".", 1)[-1] if "." in class_fqn else class_fqn

        method_name = r.get("method", "")
        # Shorten param types: com.example.Foo → Foo
        if "(" in fqn and "#" in fqn:
            raw_sig = fqn.split("#", 1)[1]
            name_part = raw_sig.split("(")[0]
            params_part = raw_sig.split("(", 1)[1].rstrip(")")
            short_params = ",".join(p.rsplit(".", 1)[-1] for p in params_part.split(",") if p)
            method_name = f"{name_part}({short_params})"

        file_path = r.get("file", "")
        short_file = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

        line = r.get("line", 0) or 0
        endpoint = r.get("endpoint", "")
        loc = f"{short_file}:{line}" if line else short_file

        entry = {
            "depth": depth,
            "class": short_class,
            "method": method_name,
            "location": loc,
            "fqn": fqn,
        }
        if endpoint:
            entry["endpoint"] = endpoint
        out.append(entry)
    return out


def get_flow_trace(db: GraphDB, method_fqn: str, depth: int = 5,
                   include_external: bool = False) -> list[dict]:
    """Trace execution flow from a method through call chain."""
    cypher, params = queries.trace_flow(method_fqn, depth)
    results = db.query(cypher, params)
    return _compact_trace(results, include_external)


def get_endpoint_flow(db: GraphDB, path: str, http_method: str = "", depth: int = 5,
                      include_external: bool = False) -> list[dict]:
    """Trace execution flow from a REST endpoint."""
    cypher, params = queries.trace_endpoint_flow(path, http_method, depth)
    results = db.query(cypher, params)
    return _compact_trace(results, include_external)


def get_reverse_trace(db: GraphDB, method_fqn: str, depth: int = 5,
                      include_external: bool = False) -> list[dict]:
    """Reverse trace: from a method, trace UP to find callers and their endpoints."""
    cypher, params = queries.reverse_trace(method_fqn, depth)
    results = db.query(cypher, params)
    return _compact_trace(results, include_external)


def _expand_with_overrides(db: GraphDB, fqns: set[str]) -> set[str]:
    """Given a set of method FQNs, return FQNs UNION the interface/abstract methods
    they override (and transitively — override chains can be multi-level).

    This is the key fix for polymorphic dispatch blind spots. When controller code
    does `interfaceBean.method()`, PSI records the CALLS edge to the interface
    method, not the impl. Walking UPWARDS from an impl misses every polymorphic
    caller unless we also consider callers of the parent method. This helper
    returns the closure of `fqns` under OVERRIDES.

    Handles the two common Java/Spring patterns that break naive static call graphs:
    1. **Interface-typed injection**: `@Autowired UserService x; x.create(...)` —
       the CALLS edge lands on `UserService#create`, the impl has 0 CALLS-in.
    2. **Template method**: base class calls `this.convertToDomain()` which
       resolves to subclass override at runtime. Edge records the base method.
    """
    if not fqns:
        return fqns
    rows = db.query(
        """
        UNWIND $fqns AS fqn
        MATCH (m:Method {fqn: fqn})-[:OVERRIDES*1..5]->(parent:Method)
        RETURN DISTINCT parent.fqn AS parent_fqn
        """,
        {"fqns": list(fqns)},
    )
    parents = {r["parent_fqn"] for r in rows if r.get("parent_fqn")}
    return fqns | parents


def _direct_callers(db: GraphDB, fqns: set[str]) -> list[dict]:
    """All methods that directly :CALLS any FQN in `fqns`. One round-trip."""
    if not fqns:
        return []
    rows = db.query(
        """
        UNWIND $fqns AS fqn
        MATCH (caller:Method)-[:CALLS]->(target:Method {fqn: fqn})
        RETURN DISTINCT caller.fqn AS caller_fqn, caller.classFqn AS className,
                        caller.name AS method, caller.filePath AS file,
                        caller.lineStart AS line
        """,
        {"fqns": list(fqns)},
    )
    return rows


def _handlers_among(db: GraphDB, fqns: set[str]) -> list[dict]:
    """Which of `fqns` are REST endpoint handlers? One round-trip."""
    if not fqns:
        return []
    return db.query(
        """
        UNWIND $fqns AS fqn
        MATCH (m:Method {fqn: fqn})-[:HANDLES]->(e:Endpoint)
        RETURN m.fqn AS fqn, m.classFqn AS className, m.name AS handler,
               m.filePath AS file, m.lineStart AS line,
               e.httpMethod + ' ' + e.path AS endpoint
        """,
        {"fqns": list(fqns)},
    )


# A type counts as "generic base" — and therefore useless for narrowing
# polymorphic callers — once more than this many classes implement or extend
# it. Below this, an interface-with-few-impls unambiguously points to the
# specific beans we care about. Empirically: a domain-specific service
# interface has 1-3 impls; an abstract framework base has 100+. The gap is
# large enough that any threshold in [5, 30] gives the same partition.
_GENERIC_BASE_SUBCLASS_THRESHOLD = 10


def _compatible_bean_types(db: GraphDB, target_class_fqn: str) -> set[str]:
    """Return the specific types that a field holding our target impl's bean
    could be declared as. Excludes generic bases (types implemented/extended
    by more than `_GENERIC_BASE_SUBCLASS_THRESHOLD` classes), since filtering
    controllers by "has-a-field-of-type-AbstractBaseService" retains every
    Spring service in the codebase.

    Two small queries (not one join) because FalkorDB times out on
    variable-length paths cross-joined with an OPTIONAL MATCH. Separating
    them runs in single-digit milliseconds.

    Rationale: the whole purpose of this set is to post-filter over-approximated
    polymorphic call chains. If we keep generic bases in the filter, the filter
    is a no-op; if we only keep specific interfaces/impls, the filter correctly
    identifies which controllers actually inject a bean that could dispatch
    through our target impl.
    """
    ancestors = db.query(
        """
        MATCH (impl:Class {fqn: $fqn})-[:IMPLEMENTS|EXTENDS*0..5]->(t:Class)
        RETURN DISTINCT t.fqn AS fqn
        """,
        {"fqn": target_class_fqn},
    )
    ancestor_fqns = [a["fqn"] for a in ancestors if a.get("fqn")]
    if not ancestor_fqns:
        return {target_class_fqn}

    counts = db.query(
        """
        UNWIND $fqns AS anc
        MATCH (sub:Class)-[:IMPLEMENTS|EXTENDS]->(parent:Class {fqn: anc})
        RETURN anc AS fqn, count(DISTINCT sub) AS n
        """,
        {"fqns": ancestor_fqns},
    )
    sub_count = {c["fqn"]: c["n"] for c in counts}

    compatible: set[str] = {target_class_fqn}
    for fqn in ancestor_fqns:
        if fqn == target_class_fqn:
            continue
        if sub_count.get(fqn, 0) <= _GENERIC_BASE_SUBCLASS_THRESHOLD:
            compatible.add(fqn)
    return compatible


def _classes_with_compatible_field(
    db: GraphDB, candidate_class_fqns: set[str], compatible_types: set[str]
) -> set[str]:
    """Filter `candidate_class_fqns` to those that directly or transitively
    (via EXTENDS) have a field whose declared type is in `compatible_types`.

    This is the type-aware narrowing that turns CHA's "176 polymorphic maybes"
    into "36 controllers that actually inject our target's bean type". Spring
    `@Autowired`/constructor injection isn't tracked via INJECTS edges (plugin
    gap), but `Field.type` is — that's enough.

    Implementation note: naive `UNWIND candidates × EXTENDS*0..4 × HAS_FIELD`
    creates a Cartesian blowup that times out on FalkorDB. We invert:
    1. Find all classes (owners) that directly HAS_FIELD a compatible type.
    2. Expand each owner to its subclasses (they inherit the field).
    3. Intersect with the candidate set.

    Two cheap queries (< 50 ms total for 49K-drawer graph) vs the naive join
    that times out at 30 s.
    """
    if not candidate_class_fqns or not compatible_types:
        return set()

    # Step 1: classes that directly declare a field of a compatible type.
    owners = db.query(
        """
        MATCH (owner:Class)-[:HAS_FIELD]->(f:Field)
        WHERE f.type IN $types
        RETURN DISTINCT owner.fqn AS fqn
        """,
        {"types": list(compatible_types)},
    )
    owner_fqns = [o["fqn"] for o in owners if o.get("fqn")]
    if not owner_fqns:
        return set()

    # Step 2: descendants that inherit the field. `EXTENDS*0..4` includes the
    # owner itself (depth 0) so we don't need a separate UNION with owners.
    desc = db.query(
        """
        UNWIND $fqns AS o
        MATCH (d:Class)-[:EXTENDS*0..4]->(parent:Class {fqn: o})
        RETURN DISTINCT d.fqn AS fqn
        """,
        {"fqns": owner_fqns},
    )
    reachable = {d["fqn"] for d in desc if d.get("fqn")}

    # Step 3: intersect with candidate handlers.
    return candidate_class_fqns & reachable


def get_impacted_endpoints(
    db: GraphDB,
    method_fqn: str,
    depth: int = 5,
    polymorphic: bool = True,
    bean_type_filter: bool = True,
) -> list[dict]:
    """Find all REST endpoints that eventually call this method.

    Walks CALLS edges upward via BFS. When `polymorphic=True` (default),
    each frontier is expanded through OVERRIDES before finding CALLS
    predecessors — this handles interface-typed injection and template-method
    dispatch that static call graphs otherwise miss.

    **Bean-type filter (default on):** polymorphic hits are cross-checked
    against the declared field types of each handler's class. A controller
    that calls `AbstractService#create` polymorphically can only reach
    `UserServiceImpl#setPassword` at runtime if the controller injects a
    `UserService` (or `UserServiceImpl`) bean somewhere in its class or its
    `EXTENDS` chain. Controllers without such a field are filtered out. This
    collapses CHA's over-approximation (hundreds of potential endpoints) down
    to the handful of endpoints that can actually reach the target at runtime.

    Every hit is labeled with whether its chain required polymorphic expansion:
      - `precise`: every hop used a direct CALLS edge (no OVERRIDES needed)
      - `polymorphic`: chain needed OVERRIDES + had a compatible field type

    Args:
        method_fqn: The target method whose signature/semantics you're changing.
        depth: Max hops to walk upward (capped at 8).
        polymorphic: Whether to follow OVERRIDES edges for polymorphic dispatch.
        bean_type_filter: Whether to post-filter polymorphic hits by controller
            field types. Leave on unless you want CHA's full over-approximation.
    """
    depth = max(1, min(depth, 8))
    frontier: set[str] = {method_fqn}
    # Track whether each method was reached via a purely-CALLS chain or
    # whether its chain passed through at least one OVERRIDES expansion.
    precision: dict[str, str] = {method_fqn: "precise"}
    visited: set[str] = {method_fqn}
    found: dict[str, dict] = {}   # endpoint string -> row (first hop wins)

    for hop in range(1, depth + 1):
        if polymorphic:
            expanded = _expand_with_overrides(db, frontier)
            # Any freshly-added ancestor via OVERRIDES taints this path as polymorphic.
            for added in expanded - frontier:
                precision[added] = "polymorphic"
        else:
            expanded = frontier

        rows = _direct_callers(db, expanded)
        caller_fqns = {r["caller_fqn"] for r in rows if r.get("caller_fqn")}
        caller_fqns -= visited
        if not caller_fqns:
            break
        visited |= caller_fqns

        # Precision tag: we don't track which specific predecessor each caller
        # came from, so mark polymorphic if OVERRIDES expansion happened at this
        # hop. "precise" once assigned sticks — a caller reached via a precise
        # chain at hop N shouldn't get downgraded if hop N+1 is polymorphic.
        had_expansion = polymorphic and (expanded != frontier)
        new_label = "polymorphic" if had_expansion else "precise"
        for cfqn in caller_fqns:
            if precision.get(cfqn) != "precise":
                precision[cfqn] = new_label

        handlers = _handlers_among(db, caller_fqns)
        for h in handlers:
            ep = h.get("endpoint", "")
            if ep and ep not in found:
                ctrl = h.get("className", "")
                short_ctrl = ctrl.rsplit(".", 1)[-1] if "." in ctrl else ctrl
                file_path = h.get("file", "") or ""
                short_file = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
                line = h.get("line", 0) or 0
                loc = f"{short_file}:{line}" if line else short_file
                found[ep] = {
                    "endpoint": ep,
                    "controller": short_ctrl,
                    "handler": h.get("handler", ""),
                    "location": loc,
                    "hops": hop,
                    "precision": precision.get(h["fqn"], "polymorphic"),
                    "_handler_class_fqn": ctrl,   # stripped before return
                }

        frontier = caller_fqns

    # Bean-type narrowing: filter polymorphic hits to controllers that actually
    # inject a bean compatible with the concrete type that holds the target
    # method. Two runtime-dispatch patterns force us to derive compatible types
    # from both sources:
    #
    # 1. **Target is a service impl** (e.g. UserServiceImpl#before_updatePartial,
    #    a template-method hook): direct callers sit in the framework base or
    #    may be empty (PSI resolved the call to an abstract parent, not the
    #    impl). If we only derive compatible from direct callers, compatible is
    #    empty → filter skipped → every polymorphic hit retained (the
    #    over-approximation case).
    #    Fix: seed compatible from the target's *own class* ancestors. A
    #    controller can only dispatch polymorphically to UserServiceImpl via
    #    a field declared as UserService (or UserServiceImpl).
    #
    # 2. **Target is an entity method** (e.g. User#setPassword): the target's
    #    own class is the entity — controllers don't inject entities. Runtime
    #    polymorphism happens at the service classes that call the target.
    #    Direct callers' ancestors give the right compatible types here.
    #
    # Taking the UNION handles both. Narrow sets from either source win when
    # intersected against actual injected field types.
    if polymorphic and bean_type_filter:
        poly_hits = [v for v in found.values() if v.get("precision") == "polymorphic"]
        if poly_hits:
            compatible: set[str] = set()

            # Source 1: target's own class ancestors. Always runs — covers the
            # template-method case where direct_callers is empty.
            target_class_fqn = method_fqn.split("#", 1)[0] if "#" in method_fqn else ""
            if target_class_fqn:
                compatible |= _compatible_bean_types(db, target_class_fqn)

            # Source 2: direct callers' classes and their ancestors. Covers the
            # entity-method case where target's class doesn't appear in fields.
            direct_caller_rows = _direct_callers(db, {method_fqn})
            caller_classes = {
                r["className"] for r in direct_caller_rows if r.get("className")
            }
            for cc in caller_classes:
                compatible |= _compatible_bean_types(db, cc)

            if compatible:
                handler_class_fqns = {
                    v["_handler_class_fqn"]
                    for v in poly_hits
                    if v.get("_handler_class_fqn")
                }
                kept_classes = _classes_with_compatible_field(db, handler_class_fqns, compatible)
                for ep, v in list(found.items()):
                    if v.get("precision") == "polymorphic" and v.get("_handler_class_fqn") not in kept_classes:
                        del found[ep]

    # Strip internal bookkeeping field before returning.
    for v in found.values():
        v.pop("_handler_class_fqn", None)

    # Sort: precise first, then by hop, then alphabetically by endpoint.
    return sorted(
        found.values(),
        key=lambda x: (x.get("precision") != "precise", x["hops"], x["endpoint"]),
    )
