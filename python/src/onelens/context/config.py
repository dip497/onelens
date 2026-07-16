"""
OneLens Context Graph configuration.

Priority: env vars > config file (~/.onelens/context_config.json) > defaults
"""

import json
import os
import re
from pathlib import Path


DEFAULT_CONTEXT_BASE = os.path.expanduser("~/.onelens/context")
DEFAULT_COLLECTION_NAME = "onelens_drawers"

# Engineering hall types
HALL_CODE = "hall_code"
HALL_GIT = "hall_git"
HALL_ISSUES = "hall_issues"
HALL_CICD = "hall_cicd"
HALL_RUNTIME = "hall_runtime"
HALL_DECISIONS = "hall_decisions"
HALL_DOCS = "hall_docs"

# Palace content-type halls (orthogonal to source-type halls above).
# See docs/design/palace-mcp.md and LESSONS-LEARNED "dual hall taxonomy".
HALL_SIGNATURE = "hall_signature"
HALL_EVENT = "hall_event"
HALL_FACT = "hall_fact"
HALL_DOC = "hall_doc"

# ── Input validation (from MemPalace) ────────────────────────────────────────

MAX_NAME_LENGTH = 128
_SAFE_NAME_RE = re.compile(r"^(?:[^\W_]|[^\W_][\w .'-]{0,126}[^\W_])$")


def sanitize_name(value: str, field_name: str = "name") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    value = value.strip()
    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f"{field_name} exceeds maximum length of {MAX_NAME_LENGTH} characters")
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} contains invalid path characters")
    if "\x00" in value:
        raise ValueError(f"{field_name} contains null bytes")
    return value


def sanitize_content(value: str, max_length: int = 100_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("content must be a non-empty string")
    if len(value) > max_length:
        raise ValueError(f"content exceeds maximum length of {max_length} characters")
    if "\x00" in value:
        raise ValueError("content contains null bytes")
    return value


class OneLensContextConfig:
    """Configuration for the OneLens context graph layer."""

    def __init__(self, config_dir=None):
        self._config_dir = (
            Path(config_dir) if config_dir else Path(os.path.expanduser("~/.onelens"))
        )
        self._config_file = self._config_dir / "context_config.json"
        self._file_config = {}

        if self._config_file.exists():
            try:
                with open(self._config_file, "r") as f:
                    self._file_config = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._file_config = {}

    def context_path(self, graph_name: str) -> str:
        """Per-graph context directory: ~/.onelens/context/<graph>/"""
        base = (
            os.environ.get("ONELENS_CONTEXT_PATH")
            or self._file_config.get("context_path", DEFAULT_CONTEXT_BASE)
        )
        return os.path.join(base, graph_name)

    @property
    def collection_name(self) -> str:
        return self._file_config.get("collection_name", DEFAULT_COLLECTION_NAME)

    def init(self, graph_name: str) -> Path:
        """Create context directory for a graph."""
        path = Path(self.context_path(graph_name))
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except (OSError, NotImplementedError):
            pass
        return path
