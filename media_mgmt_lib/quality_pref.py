"""Shared quality preference matching for PT torrents and HDHive resources."""
from __future__ import annotations

import re
from typing import Any

# Chinese audio / subtitle signals commonly seen on CN trackers / HDHive
_CN_POS = [
    "中字",
    "简中",
    "繁中",
    "国语",
    "国配",
    "普通话",
    "中文",
    "双语",
    "多语",
    "chs",
    "cht",
    "zh-cn",
    "zh-tw",
    "chinese",
    "mandarin",
    "multi.?sub",
    "multisub",
    "简繁",
    "内封",
    "外挂",
]
_CN_RE = re.compile("|".join(_CN_POS), re.I)

# High-quality / special-effect subtitle signals (movie prefer)
_FX_SUB_POS = [
    "特效字幕",
    "特效",
    "花字",
    "双语特效",
    "中字特效",
    "特效中字",
    r"FX.?SUB",
    r"Special.?Effect.?Sub",
    r"\bASS\b",
    r"\bSSA\b",
    r"\bPGS\b",
    r"\bSUP\b",
    "内封特效",
]
_FX_SUB_RE = re.compile("|".join(_FX_SUB_POS), re.I)

# Original disc / remux — exclude for movie default unless user allows
_DISC_POS = [
    r"\bREMUX\b",
    r"\bBDREMUX\b",
    r"\bUHD.?REMUX\b",
    "原盘",
    "蓝光原盘",
    r"\bCOMPLETE.?BLURAY\b",
    r"\bBLURAY.?COMPLETE\b",
    r"\bBD25\b",
    r"\bBD50\b",
    r"\bBD66\b",
    r"\bBD100\b",
    r"\bISO\b",
    r"\bm2ts\b",
    r"\bBDMV\b",
]
_DISC_RE = re.compile("|".join(_DISC_POS), re.I)

_HDR_POS = re.compile(r"\b(hdr10\+?|hdr|dolby.?vision|dovi|dv|hlg)\b", re.I)
_SDR_HINT = re.compile(r"\bsdr\b", re.I)

_RES_PATTERNS = {
    "2160p": re.compile(r"(2160p|4k|uhd)", re.I),
    "4k": re.compile(r"(2160p|4k|uhd)", re.I),
    "1080p": re.compile(r"(1080p|1080i)", re.I),
    "720p": re.compile(r"720p", re.I),
    "480p": re.compile(r"480p", re.I),
}


def blob_of(*parts: Any) -> str:
    return " ".join(str(p) for p in parts if p)


def has_chinese(text: str) -> bool:
    return bool(_CN_RE.search(text or ""))


def has_fx_subtitle(text: str) -> bool:
    """Special-effect / high-quality styled subtitles."""
    return bool(_FX_SUB_RE.search(text or ""))


def is_original_disc(text: str) -> bool:
    """True for remux / 原盘 / BDMV-style disc rips."""
    return bool(_DISC_RE.search(text or ""))


def has_hdr(text: str) -> bool:
    return bool(_HDR_POS.search(text or ""))


def has_sdr_label(text: str) -> bool:
    return bool(_SDR_HINT.search(text or ""))


def resolution_hit(text: str, prefer: str | None) -> bool:
    if not prefer:
        return True
    key = prefer.lower().strip()
    # normalize
    if key in {"2160", "2160p", "4k", "uhd"}:
        key = "2160p"
    pat = _RES_PATTERNS.get(key) or re.compile(re.escape(key), re.I)
    return bool(pat.search(text or ""))


def detected_resolution(text: str) -> str | None:
    t = text or ""
    if _RES_PATTERNS["2160p"].search(t):
        return "2160p"
    if _RES_PATTERNS["1080p"].search(t):
        return "1080p"
    if _RES_PATTERNS["720p"].search(t):
        return "720p"
    if _RES_PATTERNS["480p"].search(t):
        return "480p"
    return None


# Absolute resolution ladder for soft fallback ranking (higher = better).
_RES_RANK = {
    "2160p": 4,
    "4k": 4,
    "uhd": 4,
    "1080p": 3,
    "720p": 2,
    "480p": 1,
}


def resolution_rank(text: str | None) -> int:
    """Rank detected resolution for 'best available quality' fallback."""
    det = detected_resolution(text or "")
    if not det:
        return 0
    return int(_RES_RANK.get(det, 0))


def matches_quality(
    text: str,
    *,
    resolution: str | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",  # any | sdr | hdr
) -> bool:
    t = text or ""
    if resolution and not resolution_hit(t, resolution):
        return False
    if require_chinese and not has_chinese(t):
        return False
    mode = (hdr_mode or "any").lower()
    if mode == "sdr":
        # reject clear HDR/DV labels; bare absence of HDR counts as SDR
        if has_hdr(t) and not has_sdr_label(t):
            return False
    elif mode == "hdr":
        if not has_hdr(t):
            return False
    return True


def quality_score(
    text: str,
    *,
    resolution: str | None = "1080p",
    require_chinese: bool = False,
    hdr_mode: str = "any",
    prefer_fx_sub: bool = False,
    exclude_disc: bool = False,
) -> dict[str, Any]:
    """Soft score components (higher better). Does not hard-filter."""
    t = text or ""
    res_ok = resolution_hit(t, resolution) if resolution else True
    cn = has_chinese(t)
    fx = has_fx_subtitle(t)
    disc = is_original_disc(t)
    hdr = has_hdr(t)
    sdr_lbl = has_sdr_label(t)
    mode = (hdr_mode or "any").lower()

    score = 0
    reasons: list[str] = []
    if exclude_disc and disc:
        score -= 200
        reasons.append("disc_excluded")
    if res_ok:
        score += 50
        reasons.append("resolution_hit")
    else:
        reasons.append("resolution_miss")

    if cn:
        score += 40
        reasons.append("chinese")
    elif require_chinese:
        score -= 40
        reasons.append("chinese_missing")

    if prefer_fx_sub:
        if fx:
            score += 55
            reasons.append("fx_sub")
        else:
            reasons.append("fx_sub_missing")

    if mode == "sdr":
        if hdr and not sdr_lbl:
            score -= 35
            reasons.append("hdr_penalty")
        else:
            score += 15
            reasons.append("sdr_ok")
    elif mode == "hdr":
        if hdr:
            score += 20
            reasons.append("hdr_hit")
        else:
            score -= 15
            reasons.append("hdr_missing")

    det = detected_resolution(t)
    # Absolute ladder so fallback (no preferred match) still prefers 4K > 1080 > 720
    abs_rank = resolution_rank(t)
    score += abs_rank * 8
    if abs_rank:
        reasons.append(f"res_rank={det or abs_rank}")

    matches_hard = matches_quality(
        t, resolution=resolution, require_chinese=require_chinese, hdr_mode=hdr_mode
    )
    if prefer_fx_sub and not fx:
        matches_hard = False
    if exclude_disc and disc:
        matches_hard = False

    return {
        "score": score,
        "resolution_hit": res_ok,
        "chinese": cn,
        "fx_sub": fx,
        "is_disc": disc,
        "hdr": hdr,
        "detected_resolution": det,
        "resolution_rank": abs_rank,
        "matches_hard": matches_hard,
        "reasons": reasons,
    }


def parse_quality_params(params: dict[str, Any]) -> dict[str, Any]:
    res = params.get("resolution") or params.get("prefer_resolution")
    if res:
        res = str(res)
        if res.lower() in {"4k", "uhd", "2160"}:
            res = "2160p"
    hdr_mode = str(params.get("hdr_mode") or params.get("hdr") or "any").lower()
    if hdr_mode in {"true", "1", "yes"}:
        hdr_mode = "hdr"
    if hdr_mode in {"false", "0", "no"}:
        hdr_mode = "any"
    require_chinese = str(params.get("require_chinese") or params.get("chinese") or "").lower() in {
        "1",
        "true",
        "yes",
        "中文",
        "中字",
        "国语",
    }
    # shorthand: lang=zh / lang=chinese
    lang = str(params.get("lang") or params.get("language") or "").lower()
    if lang in {"zh", "cn", "chinese", "中文", "chs"}:
        require_chinese = True
    return {
        "resolution": res,
        "require_chinese": require_chinese,
        "hdr_mode": hdr_mode if hdr_mode in {"any", "sdr", "hdr"} else "any",
    }
