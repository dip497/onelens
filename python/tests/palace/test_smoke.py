"""Smoke: 19 tools registered + core KG round-trip + taxonomy shape."""

from __future__ import annotations

import os
import tempfile

import pytest


def test_19_tools_registered() -> None:
    from onelens.palace import server

    tools = [t for t in dir(server) if t.startswith("palace_") and callable(getattr(server, t))]
    assert len(tools) == 19, f"expected 19 palace tools, got {len(tools)}: {sorted(tools)}"


def test_mcp_instance_name() -> None:
    from onelens.palace.server import mcp

    assert mcp.name == "onelens-palace"


def test_protocol_non_empty() -> None:
    from onelens.palace.protocol import PROTOCOL

    assert "ON WAKE-UP" in PROTOCOL
    assert "palace_search" in PROTOCOL


def test_aaak_spec_constant() -> None:
    from onelens.palace.aaak import AAAK_SPEC

    assert "AAAK" in AAAK_SPEC
    assert "HALLS" in AAAK_SPEC


def test_paths_isolated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ONELENS_PALACE_ROOT", str(tmp_path / "palace"))
    # Re-import to pick env
    import importlib

    import onelens.palace.paths as paths_mod

    importlib.reload(paths_mod)
    paths_mod.ensure_layout()
    assert (tmp_path / "palace" / "wal").is_dir()
    assert (tmp_path / "palace" / "manifest.json").exists()


@pytest.mark.skipif(
    os.environ.get("ONELENS_SKIP_KG") == "1",
    reason="KG round-trip requires a live FalkorDB (or lite).",
)
def test_kg_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ONELENS_PALACE_ROOT", str(tmp_path / "palace"))
    monkeypatch.setenv("ONELENS_GRAPHS_BASE", str(tmp_path / "graphs"))
    monkeypatch.setenv("ONELENS_BACKEND", "falkordblite")

    # Force fresh state caches.
    import importlib

    from onelens.palace import kg as kg_mod
    from onelens.palace import paths, store

    importlib.reload(paths)
    importlib.reload(store)
    importlib.reload(kg_mod)

    r = kg_mod.add("Alice", "owns", "RepoX", wing="t1")
    assert r["created"] is True

    q = kg_mod.query("RepoX", include_structural=False)
    assert any(t["predicate"] == "owns" for t in q)

    inv = kg_mod.invalidate("Alice", "owns", "RepoX")
    assert inv["invalidated"] >= 1

    tl = kg_mod.timeline("RepoX")
    kinds = {e["event"] for e in tl}
    assert "asserted" in kinds and "ended" in kinds

    stats = kg_mod.stats()
    assert stats["entities"] >= 2
