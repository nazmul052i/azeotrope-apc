"""HTTP client for the apc_runtime REST API.

Uses stdlib urllib (no aiohttp dep). All methods are blocking; the
manager's request handlers run in FastAPI's threadpool so blocking is
fine. Methods return parsed JSON dicts or raise RuntimeError on
network/HTTP failure.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class RuntimeClient:
    """Thin wrapper around the apc_runtime REST surface."""

    def __init__(self, base_url: str, *, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    def _get(self, path: str) -> Dict[str, Any]:
        return self._request("GET", path)

    def _post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str,
                  payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self.base_url + path
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers,
                                       method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"runtime {method} {path} -> HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"runtime {method} {path} -> {e.reason}") from e

    # ------------------------------------------------------------------
    def healthz(self) -> Dict[str, Any]:
        return self._get("/healthz")

    def list_controllers(self) -> List[Dict[str, Any]]:
        return self._get("/controllers").get("controllers", [])

    def status(self, key: str) -> Dict[str, Any]:
        return self._get(f"/controllers/{urllib.parse.quote(key)}/status")

    def latest(self, key: str) -> Dict[str, Any]:
        return self._get(f"/controllers/{urllib.parse.quote(key)}/latest")

    def pause(self, key: str) -> Dict[str, Any]:
        return self._post(f"/controllers/{urllib.parse.quote(key)}/pause")

    def resume(self, key: str) -> Dict[str, Any]:
        return self._post(f"/controllers/{urllib.parse.quote(key)}/resume")

    def reload(self, key: str) -> Dict[str, Any]:
        return self._post(f"/controllers/{urllib.parse.quote(key)}/reload")

    def set_cv_setpoint(self, key: str, cv_tag: str, sp: float) -> Dict[str, Any]:
        return self._post(
            f"/controllers/{urllib.parse.quote(key)}"
            f"/cv/{urllib.parse.quote(cv_tag)}/setpoint",
            {"setpoint": sp})

    def set_cv_limits(self, key: str, cv_tag: str,
                       lo: Optional[float] = None,
                       hi: Optional[float] = None) -> Dict[str, Any]:
        return self._post(
            f"/controllers/{urllib.parse.quote(key)}"
            f"/cv/{urllib.parse.quote(cv_tag)}/limits",
            {"lo": lo, "hi": hi})

    def set_mv_limits(self, key: str, mv_tag: str,
                       lo: Optional[float] = None,
                       hi: Optional[float] = None) -> Dict[str, Any]:
        return self._post(
            f"/controllers/{urllib.parse.quote(key)}"
            f"/mv/{urllib.parse.quote(mv_tag)}/limits",
            {"lo": lo, "hi": hi})

    def set_mv_move_suppress(self, key: str, mv_tag: str,
                              value: float) -> Dict[str, Any]:
        return self._post(
            f"/controllers/{urllib.parse.quote(key)}"
            f"/mv/{urllib.parse.quote(mv_tag)}/move-suppress",
            {"value": value})
