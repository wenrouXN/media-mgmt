"""CloudDrive2 gRPC client for magnet offline download.

Auth: API token as Bearer metadata (same as newbyte Downloader.clouddrive).
Core RPC: AddOfflineFiles(urls, toFolder).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import grpc
from google.protobuf import empty_pb2, wrappers_pb2

from media_mgmt_lib.providers.clouddrive.generated import (
    clouddrive_offline_pb2 as pb2,
)
from media_mgmt_lib.providers.clouddrive.generated import (
    clouddrive_offline_pb2_grpc as pb2_grpc,
)


@dataclass
class CloudDriveConfig:
    host: str = "127.0.0.1"
    port: int = 19798
    token: str = ""
    username: str = ""
    password: str = ""
    default_folder: str = "/115open/download"
    timeout: float = 30.0
    insecure: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "CloudDriveConfig":
        data = data or {}
        host = str(data.get("host") or "").strip()
        port = data.get("port")
        url = str(data.get("url") or "").strip()
        if url and (not host or port in (None, "")):
            parsed = urlparse(url if "://" in url else f"http://{url}")
            host = host or (parsed.hostname or "127.0.0.1")
            if port in (None, ""):
                port = parsed.port or 19798
        if not host:
            host = "127.0.0.1"
        if port in (None, ""):
            port = 19798
        default_folder = str(
            data.get("default_folder")
            or data.get("default_path")
            or data.get("save_path")
            or ""
        ).strip()
        # support newbyte-style save_paths[0].path
        if not default_folder:
            paths = data.get("save_paths") or []
            if isinstance(paths, list) and paths:
                first = paths[0]
                if isinstance(first, dict):
                    default_folder = str(first.get("path") or "").strip()
                elif isinstance(first, str):
                    default_folder = first.strip()
        if not default_folder:
            default_folder = "/115open/download"
        return cls(
            host=host,
            port=int(port),
            token=str(data.get("token") or "").strip(),
            username=str(data.get("username") or data.get("userName") or "").strip(),
            password=str(data.get("password") or "").strip(),
            default_folder=default_folder,
            timeout=float(data.get("timeout") or 30),
            insecure=str(data.get("insecure", True)).lower()
            not in {"0", "false", "no"},
        )

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"


class CloudDriveClient:
    def __init__(self, conf: CloudDriveConfig):
        self.conf = conf
        self._channel: grpc.Channel | None = None
        self._stub: pb2_grpc.CloudDriveFileSrvStub | None = None
        self._bearer: str = conf.token

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None

    def __enter__(self) -> "CloudDriveClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _ensure(self) -> pb2_grpc.CloudDriveFileSrvStub:
        if self._stub is not None:
            return self._stub
        if self.conf.insecure:
            self._channel = grpc.insecure_channel(self.conf.target)
        else:
            creds = grpc.ssl_channel_credentials()
            self._channel = grpc.secure_channel(self.conf.target, creds)
        self._stub = pb2_grpc.CloudDriveFileSrvStub(self._channel)
        return self._stub

    def _metadata(self) -> list[tuple[str, str]]:
        if not self._bearer:
            return []
        return [("authorization", f"Bearer {self._bearer}")]

    def _timeout(self) -> float:
        return float(self.conf.timeout or 30)

    def authenticate(self) -> dict[str, Any]:
        """Ensure bearer token. Prefer configured API token; else username/password GetToken."""
        if self._bearer:
            return {"success": True, "mode": "api_token", "has_token": True}
        if not (self.conf.username and self.conf.password):
            return {
                "success": False,
                "error": "auth_failed",
                "detail": "missing token or username/password",
            }
        stub = self._ensure()
        try:
            resp = stub.GetToken(
                pb2.GetTokenRequest(
                    userName=self.conf.username,
                    password=self.conf.password,
                ),
                timeout=self._timeout(),
            )
        except grpc.RpcError as e:  # type: ignore[attr-defined]
            return {
                "success": False,
                "error": "rpc_error",
                "detail": f"GetToken: {e.code()}: {e.details()}",  # type: ignore[attr-defined]
            }
        if not resp.success or not resp.token:
            return {
                "success": False,
                "error": "auth_failed",
                "detail": resp.errorMessage or "GetToken failed",
            }
        self._bearer = resp.token
        return {"success": True, "mode": "password", "has_token": True}

    def health(self) -> dict[str, Any]:
        stub = self._ensure()
        auth = self.authenticate()
        if not auth.get("success"):
            return auth
        out: dict[str, Any] = {
            "success": True,
            "target": self.conf.target,
            "auth_mode": auth.get("mode"),
            "default_folder": self.conf.default_folder,
        }
        try:
            info = stub.GetSystemInfo(empty_pb2.Empty(), timeout=self._timeout())
            out["is_login"] = bool(info.isLogin)
            out["user_name"] = info.userName or None
        except grpc.RpcError as e:  # type: ignore[attr-defined]
            # system info may work without auth; still report
            out["system_info_error"] = f"{e.code()}: {e.details()}"  # type: ignore[attr-defined]
        try:
            if self.conf.token:
                # validate API token shape when provided
                stub.GetApiTokenInfo(
                    wrappers_pb2.StringValue(value=self.conf.token),
                    timeout=self._timeout(),
                )
                out["api_token_ok"] = True
        except grpc.RpcError as e:  # type: ignore[attr-defined]
            # token may still work as Bearer even if this RPC fails
            out["api_token_check"] = f"{e.code()}: {e.details()}"  # type: ignore[attr-defined]
        try:
            acct = stub.GetAccountStatus(
                empty_pb2.Empty(),
                metadata=self._metadata(),
                timeout=self._timeout(),
            )
            out["account"] = {
                "user_name": getattr(acct, "userName", None),
                "is_active": getattr(acct, "isActive", None),
            }
        except grpc.RpcError as e:  # type: ignore[attr-defined]
            code = e.code()  # type: ignore[attr-defined]
            detail = e.details()  # type: ignore[attr-defined]
            if code == grpc.StatusCode.UNAUTHENTICATED:
                return {
                    "success": False,
                    "error": "auth_failed",
                    "detail": detail,
                    "target": self.conf.target,
                }
            out["account_error"] = f"{code}: {detail}"
        return out

    def add_offline(
        self,
        urls: str,
        to_folder: str | None = None,
        *,
        check_folder_after_secs: int | None = None,
    ) -> dict[str, Any]:
        urls = (urls or "").strip()
        if not urls:
            return {"success": False, "error": "missing_param", "need": "urls|magnet"}
        folder = (to_folder or self.conf.default_folder or "").strip()
        if not folder:
            return {
                "success": False,
                "error": "missing_param",
                "need": "to_folder|save_path|default_folder",
            }
        auth = self.authenticate()
        if not auth.get("success"):
            return auth
        stub = self._ensure()
        req = pb2.AddOfflineFileRequest(urls=urls, toFolder=folder)
        if check_folder_after_secs is not None:
            req.checkFolderAfterSecs = int(check_folder_after_secs)
        try:
            resp = stub.AddOfflineFiles(
                req,
                metadata=self._metadata(),
                timeout=self._timeout(),
            )
        except grpc.RpcError as e:  # type: ignore[attr-defined]
            code = e.code()  # type: ignore[attr-defined]
            detail = e.details()  # type: ignore[attr-defined]
            err = "rpc_error"
            if code == grpc.StatusCode.UNAUTHENTICATED:
                err = "auth_failed"
            elif code == grpc.StatusCode.PERMISSION_DENIED:
                err = "permission_denied"
            elif code == grpc.StatusCode.INVALID_ARGUMENT:
                err = "path_not_offlineable"
            return {
                "success": False,
                "error": err,
                "detail": f"{code}: {detail}",
                "to_folder": folder,
                "urls": _redact_magnet(urls),
            }
        ok = bool(resp.success)
        result: dict[str, Any] = {
            "success": ok,
            "to_folder": folder,
            "urls": _redact_magnet(urls),
            "error_message": resp.errorMessage or None,
            "result_paths": list(resp.resultFilePaths or []),
        }
        if not ok:
            result["error"] = "add_offline_failed"
            msg = (resp.errorMessage or "").lower()
            if "quota" in msg or "配额" in (resp.errorMessage or ""):
                result["error"] = "quota"
            elif "offline" in msg or "离线" in (resp.errorMessage or ""):
                result["error"] = "path_not_offlineable"
        return result

    def list_offline(self, path: str | None = None) -> dict[str, Any]:
        folder = (path or self.conf.default_folder or "").strip()
        if not folder:
            return {"success": False, "error": "missing_param", "need": "path"}
        auth = self.authenticate()
        if not auth.get("success"):
            return auth
        stub = self._ensure()
        try:
            resp = stub.ListOfflineFilesByPath(
                pb2.FileRequest(path=folder),
                metadata=self._metadata(),
                timeout=self._timeout(),
            )
        except grpc.RpcError as e:  # type: ignore[attr-defined]
            return {
                "success": False,
                "error": "rpc_error",
                "detail": f"{e.code()}: {e.details()}",  # type: ignore[attr-defined]
                "path": folder,
            }
        items = []
        for f in resp.offlineFiles or []:
            items.append(
                {
                    "name": f.name,
                    "size": int(f.size) if f.size else 0,
                    "url": _redact_magnet(f.url or ""),
                    "status": int(f.status) if f.status is not None else None,
                    "info_hash": f.infoHash or None,
                    "percent": float(f.percendDone) if f.percendDone else None,
                }
            )
        return {"success": True, "path": folder, "items": items, "count": len(items)}


def _redact_magnet(url: str) -> str:
    text = str(url or "")
    if text.startswith("magnet:?"):
        # keep xt=urn:btih:HASH prefix only when long
        if "btih:" in text.lower():
            try:
                part = text.split("btih:", 1)[1]
                h = part.split("&", 1)[0][:40]
                return f"magnet:?xt=urn:btih:{h}..."
            except Exception:  # noqa: BLE001
                return "magnet:?..."
        return "magnet:?..."
    if len(text) > 120:
        return text[:80] + "..."
    return text


def client_from_config(cfg: dict[str, Any] | None) -> CloudDriveClient:
    return CloudDriveClient(CloudDriveConfig.from_dict(cfg))
