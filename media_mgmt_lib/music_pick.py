"""Score Telegram music bot inline candidates against a query."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_PUNCT_RE = re.compile(r"[\s\-_/\\|.,，。!！?？:：;；'\"“”‘’()\[\]{}【】<>《》·•]+")


def normalize_text(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "")
    s = s.strip().lower()
    s = _PUNCT_RE.sub(" ", s)
    return " ".join(s.split())


def tokens(text: str) -> list[str]:
    return [t for t in normalize_text(text).split(" ") if t]


def score_candidate(query: str, button_text: str, *, index: int = 1) -> dict[str, Any]:
    """Return score details for one candidate button.

    Higher is better. Index is 1-based (bot order); earlier index gets a tiny tie-break.
    """
    q = normalize_text(query)
    b = normalize_text(button_text)
    q_tokens = tokens(query)
    b_tokens = tokens(button_text)

    if not q or not b:
        return {
            "index": index,
            "text": button_text,
            "score": 0.0,
            "exact": False,
            "token_coverage": 0.0,
            "reasons": ["empty_query_or_text"],
        }

    reasons: list[str] = []
    score = 0.0

    exact = q == b or q in b and len(q) >= 4 and abs(len(b) - len(q)) <= 2
    if q == b:
        score += 100
        reasons.append("exact_equal")
    elif q in b:
        score += 70
        reasons.append("query_substring")
    elif b in q and len(b) >= 4:
        score += 45
        reasons.append("button_substring")

    if q_tokens:
        hit = sum(1 for t in q_tokens if t in b)
        coverage = hit / len(q_tokens)
        score += coverage * 40
        reasons.append(f"token_coverage={coverage:.2f}")
        # bonus if all tokens hit
        if hit == len(q_tokens):
            score += 15
            reasons.append("all_tokens")
    else:
        coverage = 0.0

    # light preference for earlier bot ranking
    score += max(0.0, 3.0 - (index - 1) * 0.35)

    # penalize huge mismatched blobs when coverage is low
    if coverage < 0.5 and len(b) > max(20, len(q) * 3):
        score -= 10
        reasons.append("long_mismatch_penalty")

    return {
        "index": index,
        "text": button_text,
        "score": round(score, 3),
        "exact": bool(q == b),
        "token_coverage": round(coverage, 3),
        "reasons": reasons,
    }


def rank_candidates(query: str, buttons: list[dict[str, Any]] | list[str]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for i, btn in enumerate(buttons, start=1):
        if isinstance(btn, str):
            text = btn
            data = None
        else:
            text = str(btn.get("text") or "")
            data = btn.get("data")
        item = score_candidate(query, text, index=i)
        if data is not None:
            item["data"] = data if isinstance(data, str) else repr(data)
        ranked.append(item)
    ranked.sort(key=lambda x: (x["score"], -x["index"]), reverse=True)
    return ranked


def decide_auto_download(
    query: str,
    ranked: list[dict[str, Any]],
    *,
    min_score: float = 55.0,
    min_gap: float = 12.0,
    min_coverage: float = 0.8,
) -> dict[str, Any]:
    """High-confidence auto download policy.

    Auto when:
    - only one candidate and score high enough, OR
    - top score >= min_score AND coverage >= min_coverage AND gap to #2 >= min_gap
      (or no #2)
    """
    if not ranked:
        return {
            "auto": False,
            "needs_confirm": True,
            "confidence": "none",
            "selected": None,
            "reason": "no_candidates",
        }

    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    gap = top["score"] - second["score"] if second else 999.0

    if len(ranked) == 1 and top["score"] >= min_score * 0.7:
        return {
            "auto": True,
            "needs_confirm": False,
            "confidence": "high",
            "selected": top,
            "gap": gap,
            "reason": "single_candidate",
        }

    if top.get("exact") and (not second or gap >= 5):
        return {
            "auto": True,
            "needs_confirm": False,
            "confidence": "high",
            "selected": top,
            "gap": gap,
            "reason": "exact_match",
        }

    if (
        top["score"] >= min_score
        and top.get("token_coverage", 0) >= min_coverage
        and gap >= min_gap
    ):
        return {
            "auto": True,
            "needs_confirm": False,
            "confidence": "high",
            "selected": top,
            "gap": gap,
            "reason": "top_clear_winner",
        }

    # ambiguous
    conf = "medium" if top["score"] >= min_score * 0.6 else "low"
    return {
        "auto": False,
        "needs_confirm": True,
        "confidence": conf,
        "selected": top,  # suggestion only
        "gap": gap,
        "reason": "ambiguous_multi_match" if len(ranked) > 1 else "low_score",
    }
