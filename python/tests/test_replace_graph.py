"""Swapping a rebuilt graph file in under a running MCP server.

A scheduled rebuild replaces `<graph>.rdb` while the server keeps the graph
open. These tests drive the real MCP tools over an in-process client and
real falkordblite servers.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("redislite")

from fastmcp import Client

from onelens.graph.backends.falkordb_lite import FalkorDBLiteBackend
from onelens.mcp_server import _STATE, mcp

GRAPH = "release"


def _call(tool: str, **arguments):
    async def run():
        async with Client(mcp) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def _count(db_path: Path) -> int:
    result = _call("onelens_query", cypher="MATCH (n) RETURN count(n) AS c",
                   graph=GRAPH, db_path=str(db_path))
    return result.structured_content["result"][0]["c"]


def _write_graph_file(directory: Path, nodes: int) -> Path:
    backend = FalkorDBLiteBackend(db_path=str(directory), graph_name=GRAPH)
    backend.execute(f"UNWIND range(1, {nodes}) AS i CREATE (:Node {{i: i}})")
    backend._db.client._cleanup()
    return directory / f"{GRAPH}.rdb"


def _upload(rebuilt: Path, db_path: Path) -> None:
    shutil.copy(rebuilt, db_path / GRAPH / f"{GRAPH}.rdb.incoming")


@pytest.fixture
def db_path(tmp_path):
    yield tmp_path / "graphs"
    for handle in _STATE["db_handles"].values():
        handle.close()
    _STATE["db_handles"].clear()


def test_open_graph_serves_the_rebuilt_file_after_replace(db_path, tmp_path):
    _write_graph_file(db_path / GRAPH, nodes=3)
    assert _count(db_path) == 3

    _upload(_write_graph_file(tmp_path / "rebuilt", nodes=5), db_path)
    _call("onelens_replace_graph", graph=GRAPH, db_path=str(db_path))

    assert _count(db_path) == 5


def test_old_copy_is_not_saved_over_the_rebuilt_file(db_path, tmp_path):
    _write_graph_file(db_path / GRAPH, nodes=3)
    assert _count(db_path) == 3

    _upload(_write_graph_file(tmp_path / "rebuilt", nodes=5), db_path)
    _call("onelens_replace_graph", graph=GRAPH, db_path=str(db_path))
    for handle in _STATE["db_handles"].values():
        handle.close()
    _STATE["db_handles"].clear()

    assert _count(db_path) == 5


def test_server_left_over_from_a_killed_process_is_replaced(db_path, tmp_path):
    graph_dir = db_path / GRAPH
    _write_graph_file(graph_dir, nodes=3)
    killed_parent = textwrap.dedent(f"""
        import os
        from onelens.graph.backends.falkordb_lite import FalkorDBLiteBackend
        b = FalkorDBLiteBackend(db_path={str(graph_dir)!r}, graph_name={GRAPH!r})
        b.execute("CREATE (:Node {{i: 99}})")
        os._exit(0)
    """)
    subprocess.run([sys.executable, "-c", killed_parent], check=True)
    assert Path(f"{graph_dir / GRAPH}.rdb.settings").is_file()

    _upload(_write_graph_file(tmp_path / "rebuilt", nodes=5), db_path)
    result = _call("onelens_replace_graph", graph=GRAPH, db_path=str(db_path))

    assert result.structured_content["stopped_left_over_server"] is True
    assert _count(db_path) == 5


def test_refuses_a_graph_name_that_is_a_path(db_path):
    with pytest.raises(Exception, match="not a plain graph name"):
        _call("onelens_replace_graph", graph="../etc", db_path=str(db_path))
