"""HTTP calls made from methods (Dart's Dio calls) become ApiCall rows for the HITS bridge."""

from onelens.importer.bridge_http import normalize_path
from onelens.importer.graph_writer import method_api_calls

CALLER = "acme.services.request_service.RequestService#getRequest(int)"


def test_interpolated_dart_path_matches_the_spring_endpoint_path():
    rows = method_api_calls([
        {"method": "get", "path": "/request/${id}", "parametric": True, "callerFqn": CALLER, "line": 54},
    ], "itsm-mobile")
    assert len(rows) == 1
    row = rows[0]
    assert row["method"] == "GET"
    assert row["wing"] == "itsm-mobile"
    assert normalize_path(row["path"]) == normalize_path("/request/{id}")


def test_same_call_twice_in_one_method_is_one_node_and_unusable_rows_are_dropped():
    rows = method_api_calls([
        {"method": "POST", "path": "/request/search", "callerFqn": CALLER, "line": 10},
        {"method": "POST", "path": "/request/search", "callerFqn": CALLER, "line": 20},
        {"method": "GET", "path": "", "callerFqn": CALLER},
        {"method": "GET", "path": "/x", "callerFqn": ""},
    ], "itsm-mobile")
    assert [r["line"] for r in rows] == [10]
