"""Write-ahead log — mirrors MemPalace ~/.mempalace/wal/write_log.jsonl.

Every Palace write tool appends one JSON line. Synchronous flush.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .paths import WAL_FILE, ensure_layout


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(tool: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
    ensure_layout()
    entry = {
        "ts": _utc_iso(),
        "tool": tool,
        "payload": payload,
        "result": {k: v for k, v in result.items() if k != "content"},
    }
    with WAL_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
