"""Shared config helpers for media-mgmt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from media_mgmt_lib.credentials import inject_secrets


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = SKILL_ROOT / "config.json"
EMPTY_VALUES = (None, "")


def load_json_config(
    path: str | Path | None = None,
    *,
    inject: bool = True,
) -> dict[str, Any]:
    """Load skill config JSON and inject secrets from workspace .credentials/.

    Secrets (api_key/token/session…) prefer env + `.credentials/*` over config.json.
    Missing optional configs return empty dict.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        data: dict[str, Any] = {}
    else:
        with open(config_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        data = raw if isinstance(raw, dict) else {}
    if inject:
        return inject_secrets(data)
    return data


def merge_config_sources(cli_values: dict[str, Any], json_defaults: dict[str, Any]) -> dict[str, Any]:
    """Merge config values, preferring non-empty CLI values over JSON defaults."""
    merged = dict(json_defaults)
    for key, value in cli_values.items():
        if value not in EMPTY_VALUES:
            merged[key] = value
    return merged


def section(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name)
    return value if isinstance(value, dict) else {}


def get_nested(config: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def moviepilot_credentials(config: dict[str, Any]) -> dict[str, str]:
    """Return MoviePilot REST credentials from config (already secret-injected)."""
    moviepilot = section(config, "moviepilot")
    base_url = moviepilot.get("base_url")
    api_key = moviepilot.get("api_key")
    if base_url and api_key:
        return {"BASE_URL": str(base_url), "API_KEY": str(api_key)}
    return {}
