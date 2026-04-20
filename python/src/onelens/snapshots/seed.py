"""Snapshot-as-seed — promote an installed <graph>@<tag> to the live graph.

Flow (atomic ordering — any step failure bails without writing the marker):

    1. Copy snapshot rdb → ~/.onelens/graphs/<graph>/<graph>.rdb
    2. GRAPH.COPY + GRAPH.DELETE + SAVE to rename internal key back to <graph>
    3. Copy snapshot context dir → ~/.onelens/context/<graph>/ (if present)
    4. Only then: write ~/.onelens/graphs/<graph>/.onelens-baseline marker

Partial promote without marker = structural graph works, DeltaTracker sees no
marker and falls back to timestamp diff. Design: docs/design/phase-r-stage-1d.
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
from pathlib import Path

from onelens.snapshots.consumer import _rename_graph_in_rdb

MARKER_FILENAME = ".onelens-baseline"


def promote(graph: str, tag: str, onelens_home: Path | None = None) -> dict:
    """Seed live graph from an installed <graph>@<tag> snapshot.

    Returns {live_rdb, live_context, commitSha, warnings}. Raises if the
    snapshot isn't installed.
    """
    home = onelens_home or Path.home() / ".onelens"
    warnings: list[str] = []

    snap_dir = home / "graphs" / f"{graph}@{tag}"
    snap_rdb = snap_dir / f"{graph}@{tag}.rdb"
    snap_ctx = home / "context" / f"{graph}@{tag}"
    manifest_from_snapshot = snap_dir / "manifest.json"

    if not snap_rdb.is_file():
        raise RuntimeError(
            f"snapshot not installed: {snap_rdb} missing. "
            f"Install {graph}@{tag} first via onelens_snapshots_pull --repo local."
        )
    if not manifest_from_snapshot.is_file():
        # Fallback — pre-Stage-1d installs didn't copy manifest alongside
        # the rdb. Read it from the bundle in ~/.onelens/bundles/ if present.
        bundle_path = home / "bundles" / f"onelens-snapshot-{graph}-{tag}.tgz"
        if not bundle_path.is_file():
            raise RuntimeError(
                f"manifest not in snapshot dir and bundle not in bundles/: "
                f"{manifest_from_snapshot} / {bundle_path}. "
                "Re-install the snapshot."
            )
        import tarfile as _tarfile
        with _tarfile.open(bundle_path, "r:gz") as tf:
            member = tf.extractfile("manifest.json")
            if member is None:
                raise RuntimeError(
                    f"bundle {bundle_path} has no manifest.json — corrupted."
                )
            manifest = json.loads(member.read().decode("utf-8"))
    else:
        manifest = json.loads(manifest_from_snapshot.read_text())
    # Older bundles may carry commitSha=null (publisher ran outside a git
    # context). Resolve lazily from the tag name via `git rev-parse`.
    if not manifest.get("commitSha"):
        manifest["commitSha"] = _resolve_tag_commit(tag, warnings)
    commit_sha = manifest.get("commitSha")
    schema_version = manifest.get("schemaVersion", 0)
    producer_version = manifest.get("producerVersion", "unknown")
    embedder = manifest.get("embedder", "unknown")
    if not commit_sha:
        raise RuntimeError(
            f"manifest missing commitSha; refusing to write baseline marker."
        )

    live_dir = home / "graphs" / graph
    live_dir.mkdir(parents=True, exist_ok=True)
    live_rdb = live_dir / f"{graph}.rdb"

    # Step 1 — copy rdb. Log any overwrite so debug is possible later.
    if live_rdb.exists():
        prev_size = live_rdb.stat().st_size
        prev_mtime = live_rdb.stat().st_mtime
        warnings.append(
            f"overwrote existing live rdb ({prev_size:,} bytes, "
            f"mtime={int(prev_mtime)})"
        )
    shutil.copy2(snap_rdb, live_rdb)

    # Step 2 — rename internal graph key from <graph>@<tag> → <graph>.
    src_key = f"{graph}@{tag}"
    dst_key = graph
    _rename_graph_in_rdb(live_rdb, src_key, dst_key, warnings)

    # Step 3 — copy context dir if the snapshot had one. Bail without marker
    # on failure, so DeltaTracker doesn't use a half-applied seed.
    live_ctx = home / "context" / graph
    if snap_ctx.is_dir():
        try:
            if live_ctx.exists():
                shutil.rmtree(live_ctx)
            shutil.copytree(snap_ctx, live_ctx)
        except (OSError, shutil.Error) as e:
            warnings.append(
                f"context copy failed ({e}); seed partially applied, "
                "marker NOT written — semantic search may need rebuild. "
                "Next sync will fall back to full export."
            )
            return {
                "live_rdb": str(live_rdb),
                "live_context": None,
                "commitSha": commit_sha,
                "markerWritten": False,
                "warnings": warnings,
            }
    else:
        warnings.append(
            "snapshot did not include context/ — semantic search "
            "will need rebuild if semantic index is enabled."
        )

    # Step 4 — write the marker last.
    marker_path = live_dir / MARKER_FILENAME
    marker = {
        "tag": tag,
        "commitSha": commit_sha,
        "promotedAt": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds",
        ).replace("+00:00", "Z"),
        "schemaVersion": schema_version,
        "producerVersion": producer_version,
        "embedder": embedder,
    }
    marker_path.write_text(json.dumps(marker, indent=2))

    return {
        "live_rdb": str(live_rdb),
        "live_context": str(live_ctx) if live_ctx.exists() else None,
        "commitSha": commit_sha,
        "markerWritten": True,
        "marker": marker,
        "warnings": warnings,
    }


def _resolve_tag_commit(tag: str, warnings: list[str]) -> str | None:
    """Resolve a git tag to its commit SHA via `git rev-parse`.

    Falls back to None + warning if not in a git repo or tag unknown.
    Caller is expected to invoke from within the target repo's cwd.
    """
    import subprocess
    for ref in (tag, f"refs/tags/{tag}"):
        try:
            out = subprocess.check_output(
                ["git", "rev-parse", ref],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if out and len(out) >= 7:
                warnings.append(
                    f"manifest lacked commitSha; resolved @{tag} via "
                    f"git rev-parse ({ref}) → {out[:7]}…"
                )
                return out
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    warnings.append(
        f"manifest lacked commitSha and `git rev-parse {tag}` failed; "
        "baseline marker will not be written. Ensure you run promote "
        "from within the project repo, or republish the snapshot with "
        "commitSha populated."
    )
    return None
