"""
Flyway auto-detection (Phase C6).

Walks every workspace root for `src/main/resources/application*.properties` and
`application*.yml` / `application*.yaml`, extracts `spring.flyway.locations`, and
resolves each `classpath:<x>` reference to concrete glob patterns under
`src/main/resources/<x>/V*__*.sql`.

Falls back to the Flyway default (`classpath:db/migration`) if the project has
`org.flywaydb:flyway-core` declared in any pom.xml but no explicit location.

Output is a list of absolute-path globs. Caller does the filesystem walk.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

_PROP_LOCATION = re.compile(
    r'^\s*spring\.flyway\.locations\s*=\s*(.+?)\s*$',
    re.MULTILINE,
)
_YAML_FLYWAY_LOCATIONS = re.compile(
    r'flyway\s*:\s*(?:[^\n]*\n)+?(?:\s{2,}locations\s*:\s*(\S.*))',
    re.IGNORECASE,
)

DEFAULT_FLYWAY_LOCATION = "classpath:db/migration"


def detect_flyway_locations(roots: list[Path]) -> list[str]:
    """
    Scan every root for `application*.{properties,yml,yaml}` and return unique
    `classpath:…` location values. Adds the Flyway default if the dep is
    present in any pom.xml but no location was declared.
    """
    locations: set[str] = set()
    flyway_dep_present = False

    for root in roots:
        # Check pom for Flyway dep (cheap fingerprint — full XML parse not needed).
        for pom in _walk(root, "pom.xml", max_depth=4):
            try:
                text = pom.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "flyway-core" in text or "flywaydb" in text:
                flyway_dep_present = True
                break
        # Find application config files. `src/main/resources/` is the Spring
        # convention; we don't hardcode it — any `application*.{properties,yml}`
        # gets scanned so non-standard layouts still work.
        for cfg in _walk_configs(root):
            locations.update(_read_config(cfg))

    if flyway_dep_present and not locations:
        locations.add(DEFAULT_FLYWAY_LOCATION)

    return sorted(locations)


def resolve_classpath_globs(
    locations: Iterable[str],
    roots: list[Path],
) -> list[tuple[str, Path]]:
    """
    Turn each `classpath:X/Y` into concrete glob patterns under every root's
    `src/main/resources/X/Y/` directory, matching `V*__*.sql`.

    Returns list of (glob_pattern_for_log, directory_to_scan). Caller walks
    `directory_to_scan` for files matching `V*__*.sql` and `R__*.sql` (repeatable).
    """
    out: list[tuple[str, Path]] = []
    for loc in locations:
        if not loc.startswith("classpath:"):
            # Filesystem-style absolute location. Uncommon but legal.
            p = Path(loc)
            if p.is_absolute() and p.is_dir():
                out.append((loc, p))
            continue
        sub = loc[len("classpath:"):].strip()
        for root in roots:
            candidate = root / "src" / "main" / "resources" / sub
            if candidate.is_dir():
                out.append((loc, candidate))
            # Multi-module projects: `classpath:X` resolves per module. Walk
            # every `*/src/main/resources/X/` under the root too so the master
            # + tenant sub-module split in a reference project picks up both.
            for nested in root.glob(f"*/src/main/resources/{sub}"):
                if nested.is_dir():
                    out.append((loc, nested))
            for deep in root.glob(f"*/*/src/main/resources/{sub}"):
                if deep.is_dir():
                    out.append((loc, deep))
    # Dedupe by resolved path.
    seen: set[Path] = set()
    unique: list[tuple[str, Path]] = []
    for tag, p in out:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        unique.append((tag, rp))
    return unique


# ── helpers ────────────────────────────────────────────────────────────

def _walk(root: Path, basename: str, max_depth: int) -> Iterable[Path]:
    """Shallow filesystem walk for files named [basename]."""
    root = root.resolve()
    base_depth = len(root.parts)
    for p in root.rglob(basename):
        try:
            depth = len(p.resolve().parts) - base_depth
        except OSError:
            continue
        if depth > max_depth:
            continue
        yield p


def _walk_configs(root: Path) -> Iterable[Path]:
    """Every `application*.{properties,yml,yaml}` anywhere under a root."""
    for pattern in (
        "**/application.properties",
        "**/application-*.properties",
        "**/application.yml",
        "**/application-*.yml",
        "**/application.yaml",
        "**/application-*.yaml",
    ):
        for p in root.glob(pattern):
            # Skip build output to avoid duplicate hits.
            parts = p.parts
            if "target" in parts or "build" in parts:
                continue
            yield p


def _read_config(cfg: Path) -> set[str]:
    """Extract `spring.flyway.locations` values from one config file."""
    try:
        text = cfg.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    out: set[str] = set()
    suffix = cfg.suffix.lower()
    if suffix == ".properties":
        for m in _PROP_LOCATION.finditer(text):
            value = m.group(1).strip()
            out.update(_split_csv(value))
    else:
        # YAML — cheap regex rather than full parse; Flyway keys are always
        # scalar strings or comma-separated lists under `spring.flyway.locations`.
        for m in _YAML_FLYWAY_LOCATIONS.finditer(text):
            value = m.group(1).strip()
            # Strip surrounding brackets/quotes.
            value = value.strip("[]")
            out.update(_split_csv(value))
    return out


def _split_csv(value: str) -> list[str]:
    return [v.strip().strip("'\"") for v in value.split(",") if v.strip()]
