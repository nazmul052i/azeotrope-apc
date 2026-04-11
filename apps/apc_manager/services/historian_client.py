"""HTTP client for the apc_historian REST API."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class HistorianClient:
    def __init__(self, base_url: str, *, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Dict[str, Any]:
        url = self.base_url + path
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"historian GET {path} -> HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"historian GET {path} -> {e.reason}") from e

    # ------------------------------------------------------------------
    def healthz(self) -> Dict[str, Any]:
        return self._get("/healthz")

    def list_controllers(self) -> List[Dict[str, Any]]:
        return self._get("/controllers").get("controllers", [])

    def get_controller(self, name: str) -> Dict[str, Any]:
        return self._get(f"/controllers/{urllib.parse.quote(name)}")

    def kpi(self, name: str, *, window_min: int = 60) -> Dict[str, Any]:
        return self._get(
            f"/controllers/{urllib.parse.quote(name)}/kpi"
            f"?window_min={window_min}")

    def cv_trend(self, name: str, cv_tag: str, *,
                  field: str = "measured",
                  limit: int = 500,
                  since_ms: Optional[int] = None) -> Dict[str, Any]:
        path = (f"/controllers/{urllib.parse.quote(name)}"
                f"/cv/{urllib.parse.quote(cv_tag)}"
                f"?field={field}&limit={limit}")
        if since_ms is not None:
            path += f"&since_ms={since_ms}"
        return self._get(path)

    def mv_trend(self, name: str, mv_tag: str, *,
                  field: str = "value",
                  limit: int = 500,
                  since_ms: Optional[int] = None) -> Dict[str, Any]:
        path = (f"/controllers/{urllib.parse.quote(name)}"
                f"/mv/{urllib.parse.quote(mv_tag)}"
                f"?field={field}&limit={limit}")
        if since_ms is not None:
            path += f"&since_ms={since_ms}"
        return self._get(path)
