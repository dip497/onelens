"""Release snapshot consumer — list/pull/verify/unpack."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SnapshotInfo:
    graph: str
    tag: str
    sha256: str
    size: int
    schema_version: int
    embedder: str
    includes_embeddings: bool
    published: int


def list_remote(graph: str, repo: str) -> list[SnapshotInfo]:
    """Fetch `snapshots.json` for `repo`, return entries for `graph`."""
    url = f"https://github.com/{repo}/releases/download/onelens-index/snapshots.json"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            index = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []  # no index yet — repo has never published a snapshot
        raise
    entries = index.get("graphs", {}).get(graph, [])
    return [
        SnapshotInfo(
            graph=graph,
            tag=e["tag"],
            sha256=e["sha256"],
            size=e["size"],
            schema_version=e.get("schemaVersion", 0),
            embedder=e.get("embedder", "unknown"),
            includes_embeddings=e.get("includesEmbeddings", False),
            published=e.get("published", 0),
        )
        for e in entries
    ]


def pull(
    graph: str,
    tag: str,
    repo: str,
    verify: bool = True,
    onelens_home: Path | None = None,
    progress_cb=None,
) -> dict:
    """Download, verify, and unpack `<graph>@<tag>` from `<repo>`.

    Returns a dict with `{graph_name, rdb_path, context_path, manifest, warnings}`.
    """
    onelens_home = onelens_home or Path.home() / ".onelens"
    warnings: list[str] = []
    bundle_name = f"onelens-snapshot-{graph}-{tag}.tgz"
    is_local = repo == "local"
    url = f"https://github.com/{repo}/releases/download/{tag}/{bundle_name}"

    with tempfile.TemporaryDirectory(prefix="onelens-pull-") as tmp:
        tmpdir = Path(tmp)
        tgz = tmpdir / bundle_name

        if is_local:
            # Local install from ~/.onelens/bundles/ — skip HTTP fetch, skip
            # cosign (no .sig for local publishes). SHA256 via sidecar only.
            src = onelens_home / "bundles" / bundle_name
            if not src.is_file():
                raise RuntimeError(f"local bundle not found: {src}")
            shutil.copy2(src, tgz)
            sidecar = Path(f"{src}.sha256")
            expected_sha = (
                sidecar.read_text().split()[0].strip()
                if sidecar.is_file() else None
            )
            verify = False
        else:
            _download(url, tgz, progress_cb)
            # Expected sha256 from the index (authoritative) — falls back to sidecar.
            expected_sha = _expected_sha256(repo, graph, tag, warnings) or _fetch_sidecar_sha(
                repo, tag, bundle_name, warnings
            )
        actual_sha = _sha256_file(tgz)
        if expected_sha and expected_sha != actual_sha:
            raise RuntimeError(
                f"sha256 mismatch for {bundle_name}: expected {expected_sha}, got {actual_sha}"
            )
        if not expected_sha:
            warnings.append("no sha256 available for verification")

        # Optional cosign verify.
        if verify:
            sig_url = f"{url}.sig"
            sig_path = tmpdir / f"{bundle_name}.sig"
            try:
                _download(sig_url, sig_path, None)
                if shutil.which("cosign"):
                    res = subprocess.run(
                        ["cosign", "verify-blob", "--bundle", str(sig_path),
                         "--certificate-oidc-issuer",
                         "https://token.actions.githubusercontent.com",
                         "--certificate-identity-regexp", ".+",
                         str(tgz)],
                        capture_output=True, text=True,
                    )
                    if res.returncode != 0:
                        warnings.append(
                            "cosign verify failed: "
                            + (res.stderr or "").strip()[:200]
                        )
                else:
                    warnings.append("cosign not on PATH; skipping signature verification")
            except urllib.error.HTTPError:
                warnings.append("no signature asset found; bundle is unsigned")

        # Unpack.
        with tarfile.open(tgz, "r:gz") as tf:
            _safe_extractall(tf, tmpdir / "unpack")
        unpack = tmpdir / "unpack"
        manifest = json.loads((unpack / "manifest.json").read_text())

        dst_graph = onelens_home / "graphs" / f"{graph}@{tag}"
        dst_ctx = onelens_home / "context" / f"{graph}@{tag}"
        if dst_graph.exists():
            shutil.rmtree(dst_graph)
        shutil.copytree(unpack / "graphs" / f"{graph}@{tag}", dst_graph)

        # Copy manifest alongside the rdb so Stage 1d promote can read
        # commitSha + schemaVersion without re-extracting the tgz.
        shutil.copy2(unpack / "manifest.json", dst_graph / "manifest.json")

        # FalkorDB Lite encodes graph name as a Redis key inside the rdb.
        # The publisher bundles the rdb whose internal key = source graph
        # name; rename it to `<graph>@<tag>` via GRAPH.COPY so Lite's
        # select_graph() resolves correctly.
        rdb_path = dst_graph / f"{graph}@{tag}.rdb"
        src_key = manifest.get("graph", graph)
        dst_key = f"{graph}@{tag}"
        if src_key != dst_key:
            _rename_graph_in_rdb(rdb_path, src_key, dst_key, warnings)

        if (unpack / "context" / f"{graph}@{tag}").is_dir():
            if dst_ctx.exists():
                shutil.rmtree(dst_ctx)
            shutil.copytree(unpack / "context" / f"{graph}@{tag}", dst_ctx)

    return {
        "graph_name": f"{graph}@{tag}",
        "rdb_path": str(dst_graph / f"{graph}@{tag}.rdb"),
        "context_path": str(dst_ctx) if dst_ctx.exists() else None,
        "manifest": manifest,
        "warnings": warnings,
    }


# ── helpers ──────────────────────────────────────────────────────────────────


def _download(url: str, dst: Path, progress_cb) -> None:
    with urllib.request.urlopen(url, timeout=60) as r:
        total = int(r.getheader("content-length") or 0)
        done = 0
        with dst.open("wb") as f:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _expected_sha256(repo: str, graph: str, tag: str, warnings: list[str]) -> str | None:
    try:
        url = f"https://github.com/{repo}/releases/download/onelens-index/snapshots.json"
        with urllib.request.urlopen(url, timeout=10) as r:
            idx = json.loads(r.read().decode())
        for e in idx.get("graphs", {}).get(graph, []):
            if e.get("tag") == tag:
                return e.get("sha256")
    except Exception as exc:
        warnings.append(f"snapshots.json fetch failed: {exc}")
    return None


def _fetch_sidecar_sha(repo: str, tag: str, bundle_name: str, warnings: list[str]) -> str | None:
    url = f"https://github.com/{repo}/releases/download/{tag}/{bundle_name}.sha256"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            text = r.read().decode()
        return text.split()[0] if text else None
    except Exception:
        return None


def _rename_graph_in_rdb(rdb_path: Path, old: str, new: str, warnings: list[str]) -> None:
    """Rename the graph key inside a FalkorDB Lite rdb via GRAPH.COPY + GRAPH.DELETE + SAVE."""
    try:
        from redislite.falkordb_client import FalkorDB
    except ImportError as e:
        warnings.append(f"falkordblite not available for rename: {e}")
        return
    db = FalkorDB(dbfilename=str(rdb_path))
    try:
        # If dst already exists (stale from earlier status probe), drop it.
        try:
            db.connection.execute_command("GRAPH.DELETE", new)
        except Exception:
            pass
        db.connection.execute_command("GRAPH.COPY", old, new)
        try:
            db.connection.execute_command("GRAPH.DELETE", old)
        except Exception:
            pass
        db.connection.execute_command("SAVE")
    except Exception as exc:
        warnings.append(f"GRAPH.COPY rename failed: {exc}")
    finally:
        try:
            db.close()
        except Exception:
            pass


def _safe_extractall(tf: tarfile.TarFile, dst: Path) -> None:
    """Guard against tarball path traversal. Python 3.12+ has data filter; this
    is a belt-and-suspenders check for older environments."""
    dst.mkdir(parents=True, exist_ok=True)
    for m in tf.getmembers():
        target = (dst / m.name).resolve()
        if not str(target).startswith(str(dst.resolve())):
            raise RuntimeError(f"unsafe path in bundle: {m.name}")
    tf.extractall(dst, filter="data")
