#!/usr/bin/env python3
"""Probe all media services from the service catalog."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from media_mgmt_lib.ops.health import check_all, check_service
from media_mgmt_lib.catalog import load_service, list_service_ids


def main() -> int:
    p = argparse.ArgumentParser(description="Media service doctor")
    p.add_argument("service", nargs="?", help="optional service id")
    p.add_argument("--json", action="store_true", help="JSON only (default)")
    args = p.parse_args()

    if args.service:
        svc = load_service(args.service)
        result = check_service(svc)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("success") else 1

    report = check_all()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # human one-liner on stderr
    for s in report.get("services") or []:
        mark = "OK" if s.get("success") else "!!"
        print(f"[{mark}] {s.get('service')}: {s.get('status')}", file=sys.stderr)
    print(f"summary: {report.get('ok')}/{report.get('total')} ok", file=sys.stderr)
    return 0 if report.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(main())
