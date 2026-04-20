"""Filesystem layout for Palace sidecars.

~/.onelens/palace/
├── wal/
│   └── write_log.jsonl    # append-only audit of every write tool invocation
├── manifest.json          # version + taxonomy spec tag
└── diary/                 # unused on disk; diaries live in Chroma under wing=agent:<n>

Code graphs remain under ~/.onelens/graphs/<wing>/ and Chroma under
~/.onelens/context/<wing>/ — Palace does not touch those locations.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PALACE_ROOT = Path(os.environ.get("ONELENS_PALACE_ROOT", "~/.onelens/palace")).expanduser()
WAL_DIR = PALACE_ROOT / "wal"
WAL_FILE = WAL_DIR / "write_log.jsonl"
MANIFEST = PALACE_ROOT / "manifest.json"

KG_GRAPH_NAME = "onelens_palace_kg"

CONTEXT_BASE = Path(os.environ.get("ONELENS_CONTEXT_BASE", "~/.onelens/context")).expanduser()
GRAPHS_BASE = Path(os.environ.get("ONELENS_GRAPHS_BASE", "~/.onelens/graphs")).expanduser()


def ensure_layout() -> dict:
    """Create sidecar dirs + manifest on first use. Idempotent."""
    WAL_DIR.mkdir(parents=True, exist_ok=True)
    if not MANIFEST.exists():
        MANIFEST.write_text(
            json.dumps(
                {
                    "palace_version": 1,
                    "taxonomy_spec": "onelens-v1",
                    "aaak_enabled": False,
                },
                indent=2,
            )
        )
    return json.loads(MANIFEST.read_text())
