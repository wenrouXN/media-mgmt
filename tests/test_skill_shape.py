"""skill-creator / agent-contract shape gates for media-mgmt SKILL.md."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")


def test_frontmatter_and_name():
    assert SKILL.startswith("---\n")
    assert "name: media-mgmt" in SKILL
    assert "description:" in SKILL
    assert "禁止手搓" in SKILL or "mp_api" in SKILL


def test_section0_must_read_fields():
    required = (
        "warnings",
        "consistency",
        "state",
        "resource_authority",
        "authority",
        "error",
    )
    # §0 block must exist
    assert "## 0." in SKILL or "读结果" in SKILL
    for field in required:
        assert field in SKILL, f"missing agent-must-read field: {field}"


def test_decision_table_no_duplicate_primary_workflows():
    """Primary decision rows (section 1 tables) should not duplicate the same run target."""
    lines = SKILL.splitlines()
    in_section = False
    runs: list[str] = []
    for line in lines:
        if line.startswith("## 1."):
            in_section = True
            continue
        if in_section and line.startswith("## ") and not line.startswith("### "):
            break
        if not in_section or not line.startswith("|"):
            continue
        if "只跑这个" in line or line.startswith("|---") or line.startswith("| 用户"):
            continue
        if "`run " not in line:
            continue
        import re

        found = re.findall(r"`run ([a-z0-9_]+)`", line)
        if found:
            key = "+".join(found)
            runs.append(key)
    from collections import Counter

    c = Counter(runs)
    dups = {k: v for k, v in c.items() if v > 1}
    assert not dups, f"duplicate decision rows: {dups}"


def test_skill_has_media_and_music_sections():
    assert "1A" in SKILL and "1B" in SKILL
    assert "禁止走 watch" in SKILL or "非影视" in SKILL


def test_registry_subset_of_decision_table():
    """Every registered workflow (except internal aliases) should appear in SKILL."""
    from media_mgmt_lib.workflows import list_workflows

    names = {w["name"] for w in list_workflows()}
    # status/retry/schedule may be secondary; still should be mentionable in refs
    for must in ("watch", "library", "search", "subscribe", "nextfind", "doctor", "listen", "link"):
        assert must in names
        assert must in SKILL or f"run {must}" in SKILL or f"`run {must}`" in SKILL


def test_hard_rule_library_and_netdisk():
    assert "NextFind only" in SKILL or "有没有 = NextFind" in SKILL
    assert "resources" in SKILL
    assert "pick_n" in SKILL
