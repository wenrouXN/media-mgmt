#!/usr/bin/env python3
"""Deprecated Cloak HDHive CLI.

Use NextFind OpenAPI via media_ctl instead:
  python3 scripts/media_ctl.py run nextfind --param q=关键词 --param dry_run=true
  python3 scripts/media_ctl.py call nextfind search --param q=关键词
  python3 scripts/media_ctl.py call nextfind grab --param q=关键词 --param dry_run=true
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print(
        "scripts/hdhive.py removed (Cloak path retired).\n"
        "Use:\n"
        "  python3 scripts/media_ctl.py run nextfind --param q=... --param dry_run=true\n"
        "  python3 scripts/media_ctl.py call nextfind grab --param q=... --param dry_run=true\n"
        "Alias: run hdhive / call hdhive (same NextFind OpenAPI).\n",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
