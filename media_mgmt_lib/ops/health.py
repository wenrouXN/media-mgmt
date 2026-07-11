"""Service health probes."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from media_mgmt_lib.catalog import Service, load_catalog
from media_mgmt_lib.config import load_json_config, section


def _http_get(url: str, timeout: float = 8.0) -> tuple[int | None, str, Any]:
    try:
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            code = resp.status
        try:
            return code, raw[:500], json.loads(raw)
        except json.JSONDecodeError:
            return code, raw[:500], raw[:200]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
        return e.code, body[:500], body[:200]
    except Exception as e:  # noqa: BLE001
        return None, str(e), None


def _resolve_url(svc: Service, conf: dict[str, Any], health: dict[str, Any]) -> str | None:
    if health.get("url_from") == "config.url" and conf.get("url"):
        base = str(conf["url"]).rstrip("/")
    elif health.get("url_from") == "config.api_base_url" and conf.get("api_base_url"):
        base = str(conf["api_base_url"]).rstrip("/")
    elif health.get("url_from") == "config.cloak_url" and conf.get("cloak_url"):
        base = str(conf["cloak_url"]).rstrip("/")
    elif conf.get("base_url"):
        base = str(conf["base_url"]).rstrip("/")
    else:
        return None
    path = health.get("path") or ""
    if path and not path.startswith("/"):
        path = "/" + path
    return base + path


def check_service(svc: Service, root_config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = root_config if root_config is not None else load_json_config()
    conf = svc.config(cfg)
    missing = svc.missing_config(cfg)
    base = {
        "success": False,
        "service": svc.id,
        "op": "health",
        "name": svc.name,
        "kind": svc.kind,
    }
    if missing and svc.health.get("type") != "moviepilot_downloader":
        # still allow some probes if url present; but report missing
        if svc.health.get("type") == "config_present":
            return {**base, "success": False, "status": "misconfigured", "missing_config": missing}
        if not conf:
            return {**base, "success": False, "status": "misconfigured", "missing_config": missing}

    htype = (svc.health or {}).get("type") or "config_present"

    if htype == "always_ok":
        return {
            **base,
            "success": True,
            "status": "ok",
            "note": "no external dependency",
            "missing_config": missing,
        }

    if htype == "config_present":
        ok = not missing
        return {
            **base,
            "success": ok,
            "status": "ok" if ok else "misconfigured",
            "missing_config": missing,
            "note": "config-only health (no live probe)",
        }

    if htype == "http_get":
        url = _resolve_url(svc, conf, svc.health)
        if not url and svc.health.get("auth") == "apikey_query":
            base_url = str(conf.get("base_url") or "").rstrip("/")
            path = svc.health.get("path") or "/"
            key = conf.get("api_key")
            if base_url and key:
                url = f"{base_url}{path}?{urllib.parse.urlencode({'apikey': key})}"
        if not url:
            return {**base, "success": False, "status": "misconfigured", "missing_config": missing or ["url"], "error": "no_url"}
        # apikey already embedded if needed
        if svc.health.get("auth") == "apikey_query" and "apikey=" not in url:
            key = conf.get("api_key")
            if key:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{urllib.parse.urlencode({'apikey': key})}"
        code, raw, parsed = _http_get(url)
        ok_status = set(svc.health.get("ok_status") or [200])
        ok = code in ok_status
        return {
            **base,
            "success": ok,
            "status": "ok" if ok else "down",
            "http_status": code,
            "url": url.split("?")[0],  # strip secrets
            "detail": parsed if not isinstance(parsed, str) else raw[:200],
            "missing_config": missing,
        }

    if htype == "moviepilot_downloader":
        mp = section(cfg, "moviepilot")
        base_url = str(mp.get("base_url") or "").rstrip("/")
        key = mp.get("api_key")
        name = svc.health.get("name") or svc.id
        if not base_url or not key:
            return {**base, "success": False, "status": "misconfigured", "missing_config": ["moviepilot.base_url", "moviepilot.api_key"]}
        url = f"{base_url}/api/v1/download/clients?{urllib.parse.urlencode({'apikey': key})}"
        code, raw, parsed = _http_get(url)
        clients = []
        if isinstance(parsed, list):
            clients = parsed
        elif isinstance(parsed, dict):
            clients = parsed.get("data") or parsed.get("clients") or []
        names = []
        for c in clients or []:
            if isinstance(c, dict):
                names.append(str(c.get("name") or c.get("type") or ""))
            else:
                names.append(str(c))
        ok = any(n.upper() == str(name).upper() or str(name).upper() in n.upper() for n in names)
        return {
            **base,
            "success": ok,
            "status": "ok" if ok else "missing",
            "downloader": name,
            "clients": names,
            "http_status": code,
        }

    if htype == "cloak_profile":
        cloak = str(conf.get(svc.health.get("url_key") or "cloak_url") or "").rstrip("/")
        pid = conf.get(svc.health.get("profile_id_key") or "profile_id")
        if not cloak:
            return {**base, "success": False, "status": "misconfigured", "missing_config": missing or ["cloak_url"]}
        # manager up?
        code, raw, parsed = _http_get(cloak + "/api/profiles")
        manager_ok = code == 200
        profile_ok = None
        profile_status = None
        if manager_ok and pid:
            c2, r2, p2 = _http_get(f"{cloak}/api/profiles/{pid}/status")
            profile_ok = c2 == 200
            profile_status = p2 if isinstance(p2, dict) else r2[:200]
        ok = manager_ok and (profile_ok is not False)
        return {
            **base,
            "success": ok,
            "status": "ok" if ok else "down",
            "manager_http_status": code,
            "profile_id": pid or None,
            "profile_status": profile_status,
            "missing_config": missing,
        }

    return {**base, "success": False, "status": "unknown_health_type", "health_type": htype}


def check_all(root_config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = root_config if root_config is not None else load_json_config()
    results = []
    for svc in load_catalog():
        results.append(check_service(svc, cfg))
    ok = sum(1 for r in results if r.get("success"))
    return {
        "success": ok == len(results),
        "ok": ok,
        "total": len(results),
        "services": results,
    }
