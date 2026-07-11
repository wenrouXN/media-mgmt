from __future__ import annotations

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.workflows import list_workflows, run_workflow


REQUIRED = {
    "identify",
    "watch",
    "link",
    "share115",
    "listen",
    "doctor",
    "search",
    "status",
    "subscribe",
    "library",
    "updates",
    "schedule",
    "catchup",
    "duplicates",
    "hdhive",
    "retry",
    "upgrade",
    "playlist",
}


def test_upgrade_workflow_dry_plan():
    r = run_workflow(
        "upgrade",
        {
            "tmdbid": 296206,
            "title": "金特务：本色回归",
            "episode": 5,
            "resolution": "2160p",
            "hdr_mode": "sdr",
            "require_chinese": True,
            "prefer": "hdhive",
            "dry_run": True,
        },
    )
    assert r.get("workflow") == "upgrade"
    assert r.get("prefer") == "hdhive"
    assert r.get("quality", {}).get("resolution") == "2160p"
    assert r.get("quality", {}).get("hdr_mode") == "sdr"
    assert r.get("quality", {}).get("require_chinese") is True
    assert "plan" in r
    assert (r.get("actions") or {}).get("hdhive", {}).get("skipped") is True


def test_schedule_and_catchup_plan_live():
    sch = run_workflow("schedule", {"tmdbid": 296206, "title": "金特务：本色回归"})
    assert sch.get("success") is True
    assert "aired" in sch and "upcoming" in sch
    plan = run_workflow("catchup", {"tmdbid": 296206, "title": "金特务：本色回归", "dry_run": True})
    assert plan.get("success") is True
    assert "plan" in plan
    assert "download_now" in plan["plan"]
    assert "subscribe_for" in plan["plan"]


def test_identify_resolves_tmdbid():
    r = run_workflow("identify", {"title": "金特务"})
    assert r.get("success") is True
    assert r.get("tmdb_id") == 296206
    assert r.get("selected", {}).get("title")
    assert "candidates" in r


def test_all_fixed_workflows_registered():
    names = {w["name"] for w in list_workflows()}
    assert REQUIRED <= names


def test_doctor_workflow_live():
    r = run_workflow("doctor", {})
    assert r.get("workflow") == "doctor"
    assert "ok" in r and "total" in r


def test_library_and_updates_live():
    lib = run_workflow("library", {"title": "金特务：本色回归", "media_type": "电视剧"})
    assert lib.get("success") is True
    assert "exists" in lib
    upd = run_workflow("updates", {"title": "金特务：本色回归"})
    assert upd.get("success") is True
    assert "has_update" in upd


def test_duplicates_reports_only():
    r = run_workflow("duplicates", {"title": "金特务：本色回归", "tmdbid": 296206})
    assert r.get("success") is True
    assert "duplicate_groups" in r
    assert r.get("apply_requested") is False


def test_unknown_workflow():
    r = run_workflow("not-a-real-flow", {})
    assert r.get("success") is False
    assert r.get("error") == "unknown_workflow"
