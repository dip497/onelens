"""Merging per-language exports of one component into a single graph export."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "merge_exports", Path(__file__).parents[2] / "tools" / "extractors" / "merge_exports.py")
merge_exports = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(merge_exports)


def _go():
    return {
        "version": "1.0", "exportType": "full", "project": {"name": "unified-agent"},
        "classes": [{"fqn": "agent/internal.Runner", "name": "Runner"}],
        "methods": [{"fqn": "agent/internal.Runner#Run()", "name": "Run"}],
        "callGraph": [{"callerFqn": "agent/internal.Runner#Run()", "calleeFqn": "fmt#Println(...any)", "line": 9}],
        "adapters": ["go-types"],
    }


def _csharp():
    return {
        "version": "1.0", "exportType": "full", "project": {"name": "windows"},
        "classes": [{"fqn": "WindowsAgent.Program", "name": "Program"}],
        "methods": [{"fqn": "WindowsAgent.Program#Main(string[])", "name": "Main"}],
        "callGraph": [{"callerFqn": "WindowsAgent.Program#Main(string[])", "calleeFqn": "System.Console#WriteLine(string)", "line": 3}],
        "spring": {"beans": [], "endpoints": [{"id": "GET:/api/x", "path": "/api/x"}]},
        "stats": {"classCount": 1},
        "adapters": ["csharp-roslyn"],
    }


def test_every_part_lands_in_one_graph():
    doc = merge_exports.merge([_go(), _csharp()], "serviceopsagent")
    assert doc["project"]["name"] == "serviceopsagent"
    assert {c["fqn"] for c in doc["classes"]} == {"agent/internal.Runner", "WindowsAgent.Program"}
    assert len(doc["callGraph"]) == 2
    assert doc["spring"]["endpoints"] == [{"id": "GET:/api/x", "path": "/api/x"}]
    assert doc["adapters"] == ["go-types", "csharp-roslyn"]


def test_same_fqn_from_two_parts_is_kept_once_first_wins():
    a, b = _csharp(), _csharp()
    b["classes"][0]["name"] = "Changed"
    doc = merge_exports.merge([a, b], "poller")
    assert doc["classes"] == [{"fqn": "WindowsAgent.Program", "name": "Program"}]
    assert len(doc["callGraph"]) == 1


def test_stats_are_summed_and_empty_blocks_filled():
    first = dict(_go(), spring=None, stats={"classCount": 2})
    doc = merge_exports.merge([first, _csharp()], "edge")
    assert doc["stats"]["classCount"] == 3
    assert doc["spring"]["endpoints"][0]["id"] == "GET:/api/x"
