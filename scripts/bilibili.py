#!/usr/bin/env python3
"""Thin wrapper for bilibili CLI."""
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
repo_root_str = str(repo_root)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

from media_mgmt_lib.providers.bilibili.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
