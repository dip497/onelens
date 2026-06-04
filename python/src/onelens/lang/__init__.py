"""
onelens.lang — language-agnostic foundation for multi-language support.

OneLens began Java/Spring-only: FQN syntax (`pkg.Class#method(Type)`), entry-point
annotations (`@Scheduled`), trivial-method conventions (`getX`/`setX`), and
importance heuristics (`@Service`) were all hardcoded across the importer, miner,
and analysis layers. This package extracts those assumptions into per-language
**profiles** so a new language (Kotlin, Go, Python, C#, Vue) is configuration,
not a rewrite.

Two pieces:
- `profiles` — one `LanguageProfile` per language; `get_profile(lang)` / registry.
- `identity` — the single home for node-identity parsing (container, simple name,
  constructor detection, param shortening). Prefers structured fields carried in
  the export JSON; falls back to syntax parsing driven by the language profile.

Java is the default everywhere, so existing graphs behave identically.
"""

from onelens.lang.profiles import (
    DEFAULT_LANG,
    LanguageProfile,
    all_entry_point_annotations,
    get_profile,
    registered_langs,
)

__all__ = [
    "DEFAULT_LANG",
    "LanguageProfile",
    "all_entry_point_annotations",
    "get_profile",
    "registered_langs",
]
