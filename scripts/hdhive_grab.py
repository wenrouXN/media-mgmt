#!/usr/bin/env python3
"""Deprecated Cloak HDHive grab CLI — use NextFind OpenAPI."""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print(
        "scripts/hdhive_grab.py removed (Cloak path retired).\n"
        "Use: python3 scripts/media_ctl.py run nextfind --param q=... --param dry_run=true\n",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
