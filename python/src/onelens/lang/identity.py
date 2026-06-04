"""
identity.py — the single home for node-identity interpretation.

Previously, container/member/param parsing was scattered as `fqn.split("#")` /
`split("(")` across loader.py, delta_loader.py, analysis.py, and code_miner.py —
each one a buried Java assumption. This module centralizes it.

Resolution order for every accessor:
1. **Structured field** carried in the export node (`container`, `simpleName`,
   `isConstructor`, `displayName`). New extractors emit these so the brain never
   parses syntax. This is the target state.
2. **Syntax fallback** driven by the language profile's separators. Exactly
   reproduces the old Java behavior when a node is a bare Java FQN with no hints.

All functions accept either a node dict or a raw FQN string.
"""

from __future__ import annotations

from onelens.lang.profiles import LanguageProfile, get_profile


def _resolve(node_or_fqn: dict | str, lang: str | None) -> tuple[str, LanguageProfile, dict | None]:
    """Normalize input to (fqn, profile, node-or-None)."""
    if isinstance(node_or_fqn, dict):
        node = node_or_fqn
        fqn = node.get("fqn", "") or node.get("id", "")
        profile = get_profile(lang or node.get("lang"))
        return fqn, profile, node
    return node_or_fqn, get_profile(lang), None


def container_fqn(node_or_fqn: dict | str, lang: str | None = None) -> str:
    """The owning container's FQN (class/module). Java: text before '#'."""
    fqn, profile, node = _resolve(node_or_fqn, lang)
    if node is not None and node.get("container"):
        return node["container"]
    sep = profile.member_sep
    return fqn.split(sep, 1)[0] if sep and sep in fqn else fqn


def simple_name(node_or_fqn: dict | str, lang: str | None = None) -> str:
    """Bare member name with no container or params. Java: between '#' and '('."""
    fqn, profile, node = _resolve(node_or_fqn, lang)
    if node is not None and node.get("simpleName"):
        return node["simpleName"]
    sep, popen = profile.member_sep, profile.params_open
    if sep and sep in fqn:
        after = fqn.split(sep, 1)[1]
        return after.split(popen, 1)[0] if popen in after else after
    # No member separator — a class/free-function FQN: last package component.
    return fqn.split(profile.package_sep)[-1].split(popen, 1)[0]


def short_class(node_or_fqn: dict | str, lang: str | None = None) -> str:
    """Short name of the owning class (last package component of the container)."""
    _, profile, _ = _resolve(node_or_fqn, lang)
    container = container_fqn(node_or_fqn, lang)
    return container.split(profile.package_sep)[-1]


def innermost_class(node_or_fqn: dict | str, lang: str | None = None) -> str:
    """Class simple name reduced to its innermost nested type.

    Java mangles nested classes as `Outer$Inner`; a constructor's member name is
    `Inner`, so constructor detection must compare against the innermost segment.
    For languages without inner-class mangling this equals `short_class`.
    """
    _, profile, _ = _resolve(node_or_fqn, lang)
    simple = short_class(node_or_fqn, lang)
    sep = profile.inner_class_sep
    if sep and sep in simple:
        return simple.split(sep)[-1]
    return simple


def short_params(node_or_fqn: dict | str, lang: str | None = None) -> str:
    """Shortened parameter list, e.g. '(String, int)'. Empty if no param list."""
    fqn, profile, node = _resolve(node_or_fqn, lang)
    popen, pclose, psep = profile.params_open, profile.params_close, profile.package_sep
    if popen not in fqn:
        return ""
    params = fqn.split(popen, 1)[1].rstrip(pclose)
    if not params:
        return "()"
    short = ", ".join(p.split(psep)[-1] for p in params.split(","))
    return f"({short})"


def is_constructor(
    node_or_fqn: dict | str,
    class_simple: str | None = None,
    lang: str | None = None,
) -> bool:
    """Whether the member is a constructor.

    Prefers an explicit `isConstructor` flag; otherwise uses the profile:
    a fixed `constructor_name` (Python `__init__`, C# `.ctor`) or the
    Java/Kotlin convention (member name == class simple name).
    """
    fqn, profile, node = _resolve(node_or_fqn, lang)
    if node is not None and "isConstructor" in node:
        return bool(node["isConstructor"])
    name = simple_name(node_or_fqn, lang)
    if profile.constructor_name is not None:
        return name == profile.constructor_name
    cls = class_simple if class_simple is not None else innermost_class(node_or_fqn, lang)
    return bool(name) and name == cls


def is_trivial_member(name: str, body_lines: int, lang: str | None = None) -> bool:
    """Whether a member is a trivial accessor/Object-method (skip from embedding).

    Mirrors the old Java heuristic but reads the language profile: exact-name
    matches (toString/__str__/...) always skip; prefix accessors (getX/setX)
    skip only for short bodies and camelCase/PascalCase shape.
    """
    profile = get_profile(lang)
    if not name:
        return False
    if name in profile.trivial_names:
        return True
    if body_lines <= 3:
        for prefix in profile.trivial_prefixes:
            if (
                name.startswith(prefix)
                and len(name) > len(prefix)
                and name[len(prefix)].isupper()
            ):
                return True
    return False
