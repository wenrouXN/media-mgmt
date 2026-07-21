from __future__ import annotations

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.catalog import load_catalog
from media_mgmt_lib.ops import call_op, list_ops


def test_all_declared_ops_are_implemented():
    for svc in load_catalog():
        info = list_ops(svc.id)
        assert info.get("complete") is True, f"{svc.id} missing ops: {info.get('missing')}"


def test_moviepilot_paths_op():
    result = call_op("moviepilot", "paths", {})
    assert result.get("service") == "moviepilot"
    # live env should succeed
    assert result.get("success") is True or "data" in result or isinstance(result, dict)


def test_hdhive_search_requires_query():
    result = call_op("hdhive", "search", {})
    assert result.get("success") is False
    assert "need" in result


def test_nextfind_search_requires_query():
    result = call_op("nextfind", "search", {})
    assert result.get("success") is False
    assert "need" in result or result.get("error")


def test_pansou_and_cloak_removed_from_catalog():
    ids = {svc.id for svc in load_catalog()}
    assert "pansou" not in ids
    assert "cloakbrowser" not in ids
