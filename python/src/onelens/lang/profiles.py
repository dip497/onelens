"""
Language profiles — per-language configuration that replaces the Java/Spring
constants previously hardcoded in pagerank.py, code_miner.py, and analysis.py.

Each `LanguageProfile` describes:
- identity syntax (how a member FQN separates container/member/params),
- entry-point markers (PageRank personalization seeds),
- trivial-member conventions (skipped from semantic embedding),
- importance boosts (annotation/decorator substrings → score).

Profiles are frozen dataclasses in a registry (not YAML) on purpose: no runtime
file I/O or extra dependency, and the CI mypy/ruff guard type-checks them.

Java is the default (`DEFAULT_LANG`); its profile reproduces the previous
hardcoded behavior exactly, so existing graphs import byte-identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_LANG = "java"

# An importance group: if ANY substring matches a node's annotations, add `score`
# ONCE. Modeling as groups (rather than flat substrings) preserves the original
# semantics where, e.g., a class with @Service AND @Controller is boosted once,
# but a method with @Transactional AND @Scheduled stacks both boosts.
ImportanceGroup = tuple[tuple[str, ...], float]


@dataclass(frozen=True)
class LanguageProfile:
    """Everything the brain needs to interpret one language's nodes."""

    lang: str

    # ── Identity syntax ──────────────────────────────────────────────────────
    # Member FQN shape: <container><member_sep><name><params_open>...<params_close>
    # Java:   com.example.Svc#create(java.lang.String)
    # C#:     Example.Svc.Create(System.String)   (member_sep="." — needs export hints)
    # Python: example.svc:create                   (member_sep=":")
    member_sep: str = "#"
    package_sep: str = "."
    params_open: str = "("
    params_close: str = ")"
    # Separator for nested/inner types within a class simple name, e.g. Java's
    # `Outer$Inner`. Empty string => the language has no such mangling. Used when
    # comparing a constructor's member name to the class's *innermost* simple name.
    inner_class_sep: str = ""
    # Constructor name, if the language uses a fixed one (Python "__init__",
    # C# ".ctor"). None => constructor is detected as "member name == class name"
    # (Java/Kotlin convention).
    constructor_name: str | None = None

    # ── Entry points (PageRank seeds) ────────────────────────────────────────
    # Annotation/decorator short-names that mark a method as an entry point.
    # REST endpoint handlers are seeded separately via the HANDLES edge.
    entry_point_annotations: frozenset[str] = frozenset()

    # ── Trivial members (skipped from semantic embedding) ────────────────────
    trivial_names: frozenset[str] = frozenset()
    # Prefixes that mark a getter/setter-style accessor. Matched only when the
    # char after the prefix is upper-case (camelCase/PascalCase accessor).
    trivial_prefixes: tuple[str, ...] = ()

    # ── Importance boosts ────────────────────────────────────────────────────
    importance_method_annotations: tuple[ImportanceGroup, ...] = ()
    importance_class_annotations: tuple[ImportanceGroup, ...] = ()


# ── Registry ─────────────────────────────────────────────────────────────────

JAVA = LanguageProfile(
    lang="java",
    member_sep="#",
    package_sep=".",
    inner_class_sep="$",  # Outer$Inner
    constructor_name=None,  # name == class name
    entry_point_annotations=frozenset(
        {"Scheduled", "PostConstruct", "EventListener", "KafkaListener"}
    ),
    trivial_names=frozenset({"toString", "hashCode", "equals", "clone", "finalize"}),
    trivial_prefixes=("get", "set", "is", "has", "can"),
    importance_method_annotations=(
        (("Transactional",), 0.15),
        (("Scheduled",), 0.10),
        (("Async",), 0.05),
    ),
    importance_class_annotations=(
        (("Service", "Controller", "Repository"), 0.10),
    ),
)

# Kotlin/Android — JVM, same FQN shape and Spring stereotypes apply; adds Android
# lifecycle entry points. Kotlin auto-generates accessors, so explicit getX/setX
# in source is rarer but still worth skipping when present.
KOTLIN = LanguageProfile(
    lang="kotlin",
    member_sep="#",
    package_sep=".",
    inner_class_sep="$",  # JVM-mangled nested classes
    constructor_name=None,
    entry_point_annotations=frozenset(
        {
            "Scheduled",
            "PostConstruct",
            "EventListener",
            "KafkaListener",
            # Android lifecycle / DI entry surfaces
            "AndroidEntryPoint",
            "HiltAndroidApp",
        }
    ),
    trivial_names=frozenset({"toString", "hashCode", "equals"}),
    trivial_prefixes=("get", "set", "is"),
    importance_method_annotations=(
        (("Transactional",), 0.15),
        (("Scheduled",), 0.10),
        (("Async",), 0.05),
    ),
    importance_class_annotations=(
        (("Service", "Controller", "Repository"), 0.10),
        (("Activity", "Fragment", "ViewModel"), 0.10),
    ),
)

PYTHON = LanguageProfile(
    lang="python",
    member_sep=":",  # module:function — '#' has no meaning in Python paths
    package_sep=".",
    constructor_name="__init__",
    entry_point_annotations=frozenset(
        {"task", "shared_task", "scheduled", "on_event", "app_command"}
    ),
    trivial_names=frozenset({"__str__", "__repr__", "__hash__", "__eq__"}),
    trivial_prefixes=(),  # no getX/setX convention; properties handled differently
    importance_method_annotations=(
        (("router", "route", "get", "post", "put", "delete", "patch"), 0.10),
    ),
    importance_class_annotations=(),
)

GO = LanguageProfile(
    lang="go",
    member_sep=".",  # pkg.Type.Method / pkg.Func
    package_sep="/",  # import paths use slashes
    constructor_name=None,  # Go has no constructors; New* convention handled by miner
    entry_point_annotations=frozenset(),  # Go has no annotations; markers via call sites
    trivial_names=frozenset({"String", "Error", "GoString"}),
    trivial_prefixes=("Get", "Set"),
    importance_method_annotations=(),
    importance_class_annotations=(),
)

CSHARP = LanguageProfile(
    lang="csharp",
    member_sep=".",  # Namespace.Type.Method — relies on export structure hints
    package_sep=".",
    constructor_name=".ctor",
    entry_point_annotations=frozenset(
        {"HttpGet", "HttpPost", "HttpPut", "HttpDelete", "ApiController", "EventSubscriber"}
    ),
    trivial_names=frozenset({"ToString", "GetHashCode", "Equals"}),
    trivial_prefixes=("Get", "Set"),
    importance_method_annotations=(
        (("HttpGet", "HttpPost", "HttpPut", "HttpDelete", "HttpPatch"), 0.10),
    ),
    importance_class_annotations=(
        (("Controller", "Service", "Repository"), 0.10),
    ),
)

VUE = LanguageProfile(
    lang="vue",
    member_sep="#",  # Component#method / composable functions
    package_sep="/",  # module paths
    constructor_name=None,
    entry_point_annotations=frozenset(),  # routes drive entry; see cross-stack linking
    trivial_names=frozenset(),
    trivial_prefixes=(),
    importance_method_annotations=(),
    importance_class_annotations=(),
)

_REGISTRY: dict[str, LanguageProfile] = {
    p.lang: p for p in (JAVA, KOTLIN, PYTHON, GO, CSHARP, VUE)
}


def get_profile(lang: str | None) -> LanguageProfile:
    """Return the profile for `lang`, falling back to the Java default.

    Unknown or missing langs resolve to Java so existing single-language Java
    graphs (which carry no `lang` field) behave exactly as before.
    """
    if not lang:
        return _REGISTRY[DEFAULT_LANG]
    return _REGISTRY.get(lang.lower(), _REGISTRY[DEFAULT_LANG])


def registered_langs() -> tuple[str, ...]:
    """All language identifiers with a profile."""
    return tuple(_REGISTRY.keys())


def all_entry_point_annotations() -> frozenset[str]:
    """Union of entry-point annotation names across every profile.

    PageRank runs over a whole graph that may mix languages. Querying the union
    is correct regardless of language mix and is a strict superset of Java's set,
    so a pure-Java graph yields identical results (the extra names simply never
    match any node).
    """
    out: set[str] = set()
    for p in _REGISTRY.values():
        out |= p.entry_point_annotations
    return frozenset(out)
