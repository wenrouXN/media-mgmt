"""Service catalog: load services/*.json and merge with config.json sections."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from media_mgmt_lib.config import DEFAULT_CONFIG_PATH, load_json_config, section

SKILL_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = SKILL_ROOT / "services"


@dataclass(slots=True)
class Service:
    id: str
    name: str
    kind: str
    description: str = ""
    config_section: str = ""
    required_config: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    ops: list[str] = field(default_factory=list)
    health: dict[str, Any] = field(default_factory=dict)
    endpoints: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def config(self, root_config: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = root_config if root_config is not None else load_json_config()
        sec = self.config_section or self.id
        return section(cfg, sec)

    def missing_config(self, root_config: dict[str, Any] | None = None) -> list[str]:
        conf = self.config(root_config)
        missing = []
        for key in self.required_config:
            val = conf.get(key)
            if val is None or val == "":
                missing.append(key)
        return missing


def list_service_ids(services_dir: Path | None = None) -> list[str]:
    d = services_dir or SERVICES_DIR
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def load_service(service_id: str, services_dir: Path | None = None) -> Service:
    d = services_dir or SERVICES_DIR
    path = d / f"{service_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"service not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"service json must be object: {path}")
    return Service(
        id=str(raw.get("id") or service_id),
        name=str(raw.get("name") or service_id),
        kind=str(raw.get("kind") or "unknown"),
        description=str(raw.get("description") or ""),
        config_section=str(raw.get("config_section") or service_id),
        required_config=list(raw.get("required_config") or []),
        depends_on=list(raw.get("depends_on") or []),
        ops=list(raw.get("ops") or []),
        health=dict(raw.get("health") or {}),
        endpoints=dict(raw.get("endpoints") or {}),
        raw=raw,
    )


def load_catalog(services_dir: Path | None = None) -> list[Service]:
    return [load_service(sid, services_dir) for sid in list_service_ids(services_dir)]


def catalog_summary(root_config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = root_config if root_config is not None else load_json_config(DEFAULT_CONFIG_PATH)
    out = []
    for svc in load_catalog():
        missing = svc.missing_config(cfg)
        out.append(
            {
                "id": svc.id,
                "name": svc.name,
                "kind": svc.kind,
                "description": svc.description,
                "ops": svc.ops,
                "depends_on": svc.depends_on,
                "config_section": svc.config_section,
                "configured": not missing,
                "missing_config": missing,
            }
        )
    return out
