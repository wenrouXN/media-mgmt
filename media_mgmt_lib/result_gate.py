"""Agent result gates: must-read fields + grab safety."""
from __future__ import annotations

from typing import Any

MUST_READ_KEYS = (
    "warnings",
    "consistency",
    "state",
    "resource_authority",
    "authority",
    "error",
    "degraded",
    "partial",
    "lock",
    "agent_must_read",
)


def _truthy(v: Any) -> bool:
    return str(v or "").lower() in {"1", "true", "yes", "on"}


def collect_must_read(payload: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    """Collect non-empty must-read fields from payload and shallow nested result."""
    if not isinstance(payload, dict) or depth > 2:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in MUST_READ_KEYS:
        if key == "agent_must_read":
            continue
        val = payload.get(key)
        if val in (None, "", [], {}, False):
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append({key: val})
    nested = payload.get("result")
    if isinstance(nested, dict):
        for item in collect_must_read(nested, depth=depth + 1):
            k = next(iter(item))
            if k not in seen:
                seen.add(k)
                out.append(item)
    # also nextfind / library nested blobs
    for nest_key in ("nextfind", "library", "subscribe", "fill"):
        blob = payload.get(nest_key)
        if isinstance(blob, dict):
            for item in collect_must_read(blob, depth=depth + 1):
                k = next(iter(item))
                if k not in seen:
                    seen.add(k)
                    out.append(item)
    return out


def decorate_agent_result(result: Any) -> Any:
    """Attach agent_must_read summary for media_ctl / workflows."""
    if not isinstance(result, dict):
        return result
    must = collect_must_read(result)
    out = dict(result)
    out["agent_must_read"] = must
    out["agent_must_read_keys"] = [next(iter(x)) for x in must]
    # one-line hint for models
    if must:
        keys = ", ".join(out["agent_must_read_keys"])
        note = f"Agent: read fields before concluding success → {keys}"
        if out.get("summary"):
            out["summary"] = f"{out['summary']} ｜ {note}"
        else:
            out["agent_note"] = note
    return out


def grab_resources_gate(
    *,
    resources: list[dict[str, Any]],
    search_hint_count: int | None = None,
    force_grab: Any = False,
    identified: Any = None,
) -> dict[str, Any] | None:
    """Return error dict if grab should stop; None if OK to continue.

    - Empty resources always blocks transfer path (cannot invent slug).
  - When search/identify hinted results but resources empty, error name is explicit
    and force_grab does NOT invent resources (only documents override attempt).
    """
    n = len(resources or [])
    hints = search_hint_count
    if hints is None and isinstance(identified, dict):
        hints = 1  # had an identify pick
    if n > 0:
        return None

    warnings: list[str] = []
    if hints and int(hints) > 0:
        warnings.append("nf_search_hint_but_resources_empty")

    err = "no_resources"
    if warnings:
        err = "nf_search_hint_but_resources_empty"

    out: dict[str, Any] = {
        "success": False,
        "error": err,
        "stage": "resources",
        "resources_count": 0,
        "warnings": warnings,
        "resource_authority": "resources_op",
        "hint": (
            "NextFind resources empty — cannot grab/transfer. "
            "Do not claim netdisk available. "
            "PT: force_mp_search=true or run watch prefer=pt. "
            "force_grab=true does not invent slugs when resources are empty."
        ),
    }
    if _truthy(force_grab):
        out["force_grab_ignored"] = True
        out["hint"] += " (force_grab set but resources still empty — blocked)"
    return out
