from __future__ import annotations

from media_mgmt_lib.music_pick import decide_auto_download, rank_candidates, score_candidate


def test_exact_match_auto():
    buttons = [{"text": "夜曲 - 周杰伦"}, {"text": "夜曲 remix"}, {"text": "夜曲 live"}]
    ranked = rank_candidates("夜曲 - 周杰伦", buttons)
    d = decide_auto_download("夜曲 - 周杰伦", ranked)
    assert d["auto"] is True
    assert d["needs_confirm"] is False
    assert d["selected"]["index"] == 1


def test_ambiguous_requires_confirm():
    buttons = [
        {"text": "晴天 - 周杰伦"},
        {"text": "晴天 - 某翻唱"},
        {"text": "晴天钢琴版"},
    ]
    ranked = rank_candidates("晴天", buttons)
    d = decide_auto_download("晴天", ranked)
    # all contain 晴天 → likely ambiguous
    assert d["needs_confirm"] is True
    assert d["auto"] is False
    assert d["selected"] is not None


def test_single_candidate_auto():
    ranked = rank_candidates("Foo Bar", [{"text": "Foo Bar - Artist"}])
    d = decide_auto_download("Foo Bar", ranked)
    assert d["auto"] is True


def test_score_token_coverage():
    s = score_candidate("周杰伦 晴天", "晴天 周杰伦 专辑版", index=1)
    assert s["token_coverage"] == 1.0
    assert s["score"] >= 55
