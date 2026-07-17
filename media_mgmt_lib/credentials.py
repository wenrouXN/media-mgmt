"""Shared credential loading for media-mgmt.

Secrets live under workspace `.credentials/` (or env), not in skill config.json.
Format: KEY=value lines (same as checkin-manager / TOOLS.md).

Priority (secret fields only):
  1) process environment
  2) matching file under credentials dir
  3) skill config.json (legacy fallback)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]

# section -> field -> env key candidates
SECRET_MAP: dict[str, dict[str, list[str]]] = {
    "moviepilot": {
        "api_key": ["MOVIEPILOT_API_KEY", "MP_API_KEY", "API_KEY"],
    },
    "clouddrive": {
        "token": ["CLOUDDRIVE_TOKEN", "CD_TOKEN", "TOKEN"],
        "username": ["CLOUDDRIVE_USERNAME", "CD_USERNAME", "USERNAME"],
        "password": ["CLOUDDRIVE_PASSWORD", "CD_PASSWORD", "PASSWORD"],
    },
    "telegram_music": {
        "api_id": ["TELEGRAM_API_ID", "TG_API_ID", "API_ID"],
        "api_hash": ["TELEGRAM_API_HASH", "TG_API_HASH", "API_HASH"],
        "session_string": [
            "TELEGRAM_SESSION_STRING",
            "TG_SESSION_STRING",
            "SESSION_STRING",
        ],
    },
}

# optional non-secret overlays (only fill when config empty)
OPTIONAL_MAP: dict[str, dict[str, list[str]]] = {
    "moviepilot": {
        "base_url": ["MOVIEPILOT_BASE_URL", "MP_BASE_URL", "BASE_URL"],
    },
    "clouddrive": {
        "url": ["CLOUDDRIVE_URL", "CD_URL", "URL"],
        "default_folder": [
            "CLOUDDRIVE_DEFAULT_FOLDER",
            "CD_DEFAULT_FOLDER",
            "DEFAULT_FOLDER",
        ],
    },
}

# preferred credential filenames per section
SECTION_FILES: dict[str, list[str]] = {
    "moviepilot": ["moviepilot.env", "moviepilot.txt", "p115strm.txt"],
    "clouddrive": ["clouddrive.env", "clouddrive.txt"],
    "telegram_music": ["telegram_music.env", "telegram_music.txt", "telegram.env"],
}


def resolve_credentials_dir() -> Path:
    """Locate shared credentials directory."""
    for key in ("MEDIA_MGMT_CREDENTIALS_DIR", "OPENCLAW_CREDENTIALS_DIR"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return Path(raw).expanduser()

    local = SKILL_ROOT / ".credentials"
    if local.is_dir():
        return local

    # workspace/skills/media-mgmt → workspace/.credentials
    for parent in SKILL_ROOT.parents:
        cand = parent / ".credentials"
        if cand.is_dir():
            return cand

    # known main workspace (family agents often share this pool)
    main = Path("/vol1/1000/config/share/openclaw/state/workspace/.credentials")
    if main.is_dir():
        return main

    return SKILL_ROOT.parent.parent / ".credentials"


def load_kv_file(path: Path) -> dict[str, str]:
    """Parse KEY=value credential file. Keys kept as-is (case preserved)."""
    out: dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def load_section_file_kvs(section: str, cred_dir: Path | None = None) -> dict[str, str]:
    """Load first existing credential file for a section. Uppercased keys index."""
    base = cred_dir or resolve_credentials_dir()
    merged: dict[str, str] = {}
    for name in SECTION_FILES.get(section, [f"{section}.env", f"{section}.txt"]):
        path = base / name
        if not path.exists():
            continue
        kvs = load_kv_file(path)
        # later files do not override earlier preferred names
        for k, v in kvs.items():
            merged.setdefault(k, v)
            merged.setdefault(k.upper(), v)
            merged.setdefault(k.lower(), v)
        if kvs:
            break
    return merged


def _lookup(keys: list[str], file_kvs: dict[str, str]) -> str | None:
    for key in keys:
        env = os.environ.get(key)
        if env not in (None, ""):
            return str(env)
        for candidate in (key, key.upper(), key.lower()):
            val = file_kvs.get(candidate)
            if val not in (None, ""):
                return str(val)
    return None


def inject_secrets(
    config: dict[str, Any],
    *,
    cred_dir: Path | None = None,
    include_optional: bool = True,
) -> dict[str, Any]:
    """Return a shallow-copied config with secret fields filled from credentials.

    Existing non-empty config values are kept unless env/file provides a value
    (env/file win for mapped secret fields).
    """
    out: dict[str, Any] = dict(config)
    base = cred_dir or resolve_credentials_dir()

    # deep-copy field maps so optional overlays never mutate module globals
    maps: dict[str, dict[str, list[str]]] = {
        sec: {field: list(keys) for field, keys in fields.items()}
        for sec, fields in SECRET_MAP.items()
    }
    secret_fields = {
        sec: set(fields.keys()) for sec, fields in SECRET_MAP.items()
    }
    if include_optional:
        for sec, fields in OPTIONAL_MAP.items():
            bucket = maps.setdefault(sec, {})
            for field, keys in fields.items():
                bucket.setdefault(field, list(keys))

    for section_name, fields in maps.items():
        file_kvs = load_section_file_kvs(section_name, base)
        sec = out.get(section_name)
        if not isinstance(sec, dict):
            sec = {}
        else:
            sec = dict(sec)
        changed = False
        for field, keys in fields.items():
            found = _lookup(keys, file_kvs)
            if found not in (None, ""):
                # secrets always prefer credentials/env over config
                if field in secret_fields.get(section_name, set()):
                    sec[field] = found
                    changed = True
                elif sec.get(field) in (None, ""):
                    sec[field] = found
                    changed = True
            # legacy: keep config value if nothing found
        if changed or section_name in out:
            out[section_name] = sec
    return out


def secret_fields_for(section: str) -> list[str]:
    return list(SECRET_MAP.get(section, {}).keys())


def redact_config_for_log(config: dict[str, Any]) -> dict[str, Any]:
    """Copy config with secret fields redacted (for debug/logging)."""
    out: dict[str, Any] = {}
    for k, v in config.items():
        if isinstance(v, dict):
            sec_secrets = set(SECRET_MAP.get(k, {}))
            out[k] = {
                sk: ("***" if sk in sec_secrets and sv not in (None, "") else sv)
                for sk, sv in v.items()
            }
        else:
            out[k] = v
    return out
