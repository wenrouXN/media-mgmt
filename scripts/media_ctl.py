#!/usr/bin/env python3
"""Media control plane: list services, health, call ops, run workflows."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# register all built-in ops
import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.catalog import catalog_summary, load_service
from media_mgmt_lib.ops import call_op, list_ops
from media_mgmt_lib.ops.health import check_all, check_service


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_list(_: argparse.Namespace) -> int:
    print_json({"services": catalog_summary()})
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    if args.service:
        r = check_service(load_service(args.service))
        print_json(r)
        return 0 if r.get("success") else 1
    r = check_all()
    print_json(r)
    return 0 if r.get("success") else 2


def cmd_ops(args: argparse.Namespace) -> int:
    print_json(list_ops(args.service))
    return 0


def cmd_call(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    for item in args.param or []:
        if "=" not in item:
            raise SystemExit(f"bad --param {item!r}, expected key=value")
        k, v = item.split("=", 1)
        params[k] = v
    # coerce common numeric fields
    for num_key in ("tmdbid", "episode", "season", "year", "button_index"):
        if num_key in params:
            try:
                params[num_key] = int(params[num_key])
            except ValueError:
                pass
    result = call_op(args.service, args.op, params)
    print_json(result)
    return 0 if result.get("success") else 1


def cmd_watch(args: argparse.Namespace) -> int:
    """Delegate workflow to scripts/watch.py (composition root)."""
    py = ROOT / ".venv" / "bin" / "python"
    exe = str(py) if py.exists() else sys.executable
    cmd = [exe, str(ROOT / "scripts" / "watch.py"), *args.watch_args]
    proc = subprocess.run(cmd, cwd=str(ROOT))
    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Media services control plane")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="list services from catalog")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("health", help="health check one/all services")
    s.add_argument("service", nargs="?")
    s.set_defaults(func=cmd_health)

    s = sub.add_parser("ops", help="list ops for a service")
    s.add_argument("service", nargs="?")
    s.set_defaults(func=cmd_ops)

    s = sub.add_parser("call", help="call a service op")
    s.add_argument("service")
    s.add_argument("op")
    s.add_argument("--param", action="append", default=[], help="key=value (repeatable)")
    s.set_defaults(func=cmd_call)

    s = sub.add_parser("watch", help="workflow: pass-through to watch.py")
    s.add_argument("watch_args", nargs=argparse.REMAINDER, help="args after -- for watch.py")
    s.set_defaults(func=cmd_watch)

    s = sub.add_parser("doctor", help="alias of health all")
    s.set_defaults(func=lambda a: cmd_health(argparse.Namespace(service=None)))

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # strip leading -- from watch remainder
    if getattr(args, "watch_args", None) is not None and args.watch_args[:1] == ["--"]:
        args.watch_args = args.watch_args[1:]
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
