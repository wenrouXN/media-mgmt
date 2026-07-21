"""Watch stage progress (stderr + list for JSON)."""
from __future__ import annotations

import time
from typing import Any

STAGES: list[dict[str, Any]] = []


def clear_stages() -> None:
    STAGES.clear()


def stage(name: str, **extra: Any) -> None:
    entry = {"stage": name, "t": round(time.time(), 3), **extra}
    STAGES.append(entry)
    bits = [f"[watch] {name}"]
    for k, v in extra.items():
        if v is None or v == "":
            continue
        bits.append(f"{k}={v}")
    print(" ".join(bits), file=__import__("sys").stderr, flush=True)


def stages_snapshot() -> list[dict[str, Any]]:
    return list(STAGES)
