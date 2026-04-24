"""Release snapshot producer (Lite-first).

Produces a tarball bundle of a FalkorDB Lite graph (`<graph>.rdb`) plus
optional ChromaDB context, with a bundle-internal `manifest.json` and
SHA256 checksum. Optionally signs with Cosign (keyless) and uploads to
GitHub Releases via `gh` CLI.

The legacy `scripts/bundle.sh` handles Docker FalkorDB. This module
intentionally does NOT support Docker — the OneLens CLI default is Lite
since Phase L.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MANIFEST_VERSION = 3
FALKORDB_LITE_VERSION = "bundled"  # Populated at runtime from `falkordblite`
SCHEMA_VERSION = 3  # Bump when collector output shape changes.


@dataclass
class PublishResult:
    bundle_path: Path
    manifest: dict
    sha256: str
    signed: bool
    uploaded_url: str | None
    warnings: list[str] = field(default_factory=list)


def publish(
    graph: str,
    tag: str,
    repo: str | None = None,
    include_embeddings: bool = False,
    sign: bool = True,
    backend: Literal["local", "github"] = "local",
    onelens_home: Path | None = None,
    out_dir: Path | None = None,
    commit_sha: str | None = None,
) -> PublishResult:
    """Bundle `<graph>` as `<graph>@<tag>`.

    - Reads `~/.onelens/graphs/<graph>/<graph>.rdb` (Lite).
    - Optionally reads `~/.onelens/context/<graph>/` (embeddings).
    - Emits `onelens-snapshot-<graph>-<tag>.tgz` into `out_dir`
      (default `~/.onelens/bundles/`).
    - Computes SHA256. Optionally cosign-signs (keyless). Optionally
      uploads to GitHub Release `tag` on `<repo>` via `gh release upload`.
    """
    warnings: list[str] = []
    onelens_home = onelens_home or Path.home() / ".onelens"
    out_dir = out_dir or (onelens_home / "bundles")
    out_dir.mkdir(parents=True, exist_ok=True)

    rdb_src = onelens_home / "graphs" / graph / f"{graph}.rdb"
    if not rdb_src.is_file() or rdb_src.stat().st_size < 10_000:
        raise ValueError(
            f"graph '{graph}' has no populated rdb at {rdb_src}. "
            "Run a full Sync Graph first."
        )

    ctx_src = onelens_home / "context" / graph
    has_ctx = include_embeddings and ctx_src.is_dir()

    bundle_name = f"onelens-snapshot-{graph}-{tag}.tgz"
    bundle_path = out_dir / bundle_name

    embed_model, embed_dim = _detect_embedder(ctx_src if has_ctx else None)
    manifest = {
        "manifestVersion": MANIFEST_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "graph": graph,
        "tag": tag,
        "commitSha": commit_sha or _detect_commit_sha(),
        "embedder": embed_model,
        "embedderDim": embed_dim,
        "falkordbLite": _detect_falkordb_version(),
        "includesEmbeddings": has_ctx,
        "buildTimestamp": int(time.time()),
        "producer": "onelens_snapshot_publish",
    }

    # Stage into a temp dir so tarball layout is deterministic.
    staging = out_dir / f".staging-{graph}-{tag}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        g_dst = staging / "graphs" / f"{graph}@{tag}"
        g_dst.mkdir(parents=True)
        shutil.copy2(rdb_src, g_dst / f"{graph}@{tag}.rdb")
        if has_ctx:
            shutil.copytree(ctx_src, staging / "context" / f"{graph}@{tag}")

        with tarfile.open(bundle_path, "w:gz") as tf:
            for item in staging.iterdir():
                tf.add(item, arcname=item.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    sha256 = _sha256_file(bundle_path)
    (bundle_path.parent / f"{bundle_name}.sha256").write_text(f"{sha256}  {bundle_name}\n")

    # Optional signing.
    signed = False
    if sign:
        if _has_binary("cosign"):
            try:
                subprocess.run(
                    ["cosign", "sign-blob", "--yes",
                     "--bundle", str(bundle_path.parent / f"{bundle_name}.sig"),
                     str(bundle_path)],
                    check=True, capture_output=True,
                )
                signed = True
            except subprocess.CalledProcessError as e:
                warnings.append(f"cosign signing failed: {e.stderr.decode(errors='ignore')[:200]}")
        else:
            warnings.append(
                "cosign not on PATH; producing unsigned bundle. "
                "Install: https://docs.sigstore.dev/cosign/installation/"
            )

    # Optional upload.
    uploaded_url: str | None = None
    if backend == "github":
        if not repo:
            raise ValueError("backend='github' requires --repo org/name")
        if not _has_binary("gh"):
            raise RuntimeError("gh CLI not found; install https://cli.github.com/ or use backend=local")
        assets = [bundle_path, bundle_path.parent / f"{bundle_name}.sha256"]
        sig = bundle_path.parent / f"{bundle_name}.sig"
        if sig.exists():
            assets.append(sig)
        cmd = ["gh", "release", "upload", tag, "--clobber", "--repo", repo, *map(str, assets)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            if "release not found" in (res.stderr or "").lower():
                # Try to create the release if the tag exists in git.
                create = subprocess.run(
                    ["gh", "release", "create", tag, "--repo", repo, "--title", tag,
                     "--notes", f"OneLens snapshot for {graph}", *map(str, assets)],
                    capture_output=True, text=True,
                )
                if create.returncode != 0:
                    raise RuntimeError(f"gh release create failed: {create.stderr}")
            else:
                raise RuntimeError(f"gh release upload failed: {res.stderr}")
        uploaded_url = f"https://github.com/{repo}/releases/tag/{tag}"
        _update_snapshots_index(repo, graph, manifest, sha256, bundle_path.stat().st_size, warnings)

    return PublishResult(
        bundle_path=bundle_path,
        manifest=manifest,
        sha256=sha256,
        signed=signed,
        uploaded_url=uploaded_url,
        warnings=warnings,
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_binary(name: str) -> bool:
    return shutil.which(name) is not None


def _detect_commit_sha() -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return None


def _detect_falkordb_version() -> str:
    try:
        import falkordblite  # type: ignore
        return getattr(falkordblite, "__version__", "unknown")
    except Exception:
        return "unknown"


def _detect_embedder(ctx_src: Path | None) -> tuple[str, int | None]:
    """Pull the actual embedder name + dim from config + collection metadata.

    Dim is authoritative (read from the ChromaDB sqlite's `collections` row).
    Name prefers the env override the plugin sets (`ONELENS_EMBED_MODEL`),
    falls back to the backend hint, and finally to a dim-keyed best-guess
    so older snapshots can still be read without a name.
    """
    dim: int | None = None
    if ctx_src and ctx_src.is_dir():
        sqlite_path = ctx_src / "chroma.sqlite3"
        if sqlite_path.is_file():
            try:
                import sqlite3
                with sqlite3.connect(str(sqlite_path)) as conn:
                    row = conn.execute(
                        "SELECT dimension FROM collections ORDER BY id LIMIT 1"
                    ).fetchone()
                    if row and row[0]:
                        dim = int(row[0])
            except Exception:
                pass

    env_model = os.environ.get("ONELENS_EMBED_MODEL")
    if env_model:
        return env_model, dim

    backend = (os.environ.get("ONELENS_EMBED_BACKEND") or "").lower()
    # Intentional: no dim-keyed guess fallback. Two widely-used 1024-dim
    # models exist (Qwen3-Embedding-0.6B, mxbai-embed-large) plus other
    # 768-dim models beyond Jina v2. A "guess" shipped in a manifest
    # misleads consumers into mounting a mismatched tokenizer. Better to
    # record "unknown" and let the consumer decide whether to trust the
    # collection dim alone.
    if backend == "local":
        # Backend name alone is unambiguous: only Jina v2 base code ships
        # on the local ONNX path today. If this ever gains a second local
        # model we flip to "unknown" here and require ONELENS_EMBED_MODEL.
        return "jinaai/jina-embeddings-v2-base-code", dim
    if backend == "openai":
        return "openai-compatible", dim
    return "unknown", dim


def _update_snapshots_index(
    repo: str, graph: str, manifest: dict, sha256: str, size: int, warnings: list[str]
) -> None:
    """Fetch / create / update the `snapshots.json` asset on the pinned
    `onelens-index` release, adding / replacing this graph's entry.
    """
    index_tag = "onelens-index"
    tmp = Path(f"/tmp/onelens-snapshots-{os.getpid()}.json")
    existing: dict = {"graphs": {}}
    res = subprocess.run(
        ["gh", "release", "download", index_tag, "--repo", repo,
         "--pattern", "snapshots.json", "-O", str(tmp)],
        capture_output=True, text=True,
    )
    if res.returncode == 0 and tmp.exists():
        try:
            existing = json.loads(tmp.read_text())
        except Exception:
            warnings.append("existing snapshots.json unparseable; overwriting")

    existing.setdefault("graphs", {}).setdefault(graph, [])
    entry = {
        "tag": manifest["tag"],
        "sha256": sha256,
        "size": size,
        "schemaVersion": manifest["schemaVersion"],
        "embedder": manifest["embedder"],
        "falkordbLite": manifest["falkordbLite"],
        "includesEmbeddings": manifest["includesEmbeddings"],
        "published": manifest["buildTimestamp"],
    }
    # Replace same-tag entry if present.
    existing["graphs"][graph] = [e for e in existing["graphs"][graph] if e.get("tag") != entry["tag"]]
    existing["graphs"][graph].insert(0, entry)
    existing["updatedAt"] = int(time.time())

    tmp.write_text(json.dumps(existing, indent=2, sort_keys=True))

    # Ensure the index release exists.
    subprocess.run(
        ["gh", "release", "view", index_tag, "--repo", repo],
        capture_output=True,
    )
    create = subprocess.run(
        ["gh", "release", "create", index_tag, "--repo", repo,
         "--title", "OneLens snapshot index",
         "--notes", "Auto-maintained index of OneLens snapshot bundles. Do not delete."],
        capture_output=True, text=True,
    )
    # Ignore "already exists" errors.
    if create.returncode != 0 and "already exists" not in (create.stderr or ""):
        warnings.append(f"index release create: {create.stderr[:200]}")

    up = subprocess.run(
        ["gh", "release", "upload", index_tag, "--clobber", "--repo", repo, str(tmp)],
        capture_output=True, text=True,
    )
    if up.returncode != 0:
        warnings.append(f"snapshots.json upload failed: {up.stderr[:200]}")
    tmp.unlink(missing_ok=True)
