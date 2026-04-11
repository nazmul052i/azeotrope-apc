"""Synchronous OPC UA client wrapper for the deployment runtime.

We use ``asyncua.sync.Client`` so the deployment loop can stay on a Qt
worker thread without juggling an asyncio event loop. The client is
deliberately thin: connect / browse / read batch / write batch / test +
disconnect. NodeIds come straight from the IOTag rows; datatype is
inferred from the IOTag's ``datatype`` field on writes.

asyncua's NodeId parser handles the standard string forms:
  ns=2;s=Plant.TI-201.PV
  ns=2;i=1234
  ns=0;g=09087e75-8e5e-499b-954f-f2a9603db28a
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from asyncua.sync import Client
    from asyncua import ua
    _HAS_ASYNCUA = True
except ImportError:
    _HAS_ASYNCUA = False
    Client = None  # type: ignore
    ua = None  # type: ignore


_LOG = logging.getLogger("azeoapc.deployment.opcua")


# Mapping from our IOTag.datatype string -> asyncua VariantType + Python coercion
_DTYPE_MAP = {
    "Real":    ("Double",  float),
    "Float":   ("Float",   float),
    "Integer": ("Int32",   int),
    "Int":     ("Int32",   int),
    "Int16":   ("Int16",   int),
    "Int64":   ("Int64",   int),
    "Boolean": ("Boolean", bool),
    "Bool":    ("Boolean", bool),
    "String":  ("String",  str),
}


def _to_variant(value: Any, datatype: str):
    """Wrap a Python value in an asyncua DataValue with the right VariantType."""
    if not _HAS_ASYNCUA:
        raise RuntimeError("asyncua not installed")
    vt_name, cast = _DTYPE_MAP.get(datatype, ("Double", float))
    vt = getattr(ua.VariantType, vt_name)
    return ua.DataValue(ua.Variant(cast(value), vt))


class OpcUaClient:
    """Thin synchronous OPC UA client used by the deployment runtime.

    Lifecycle:
        c = OpcUaClient("opc.tcp://localhost:4840/...")
        c.connect()
        values = c.read_many(["ns=2;s=Plant.TI-201.PV", ...])
        c.write_many({"ns=2;s=Plant.FIC-101.SP": (102.5, "Real")})
        c.disconnect()
    """

    def __init__(self, url: str, username: str = "", password: str = "",
                 timeout_sec: float = 4.0):
        self.url = url
        self.username = username
        self.password = password
        self.timeout_sec = timeout_sec
        self._client: Optional[Client] = None
        self.connected = False
        self.last_error = ""

    # ------------------------------------------------------------------
    @staticmethod
    def is_available() -> bool:
        """Whether asyncua is importable."""
        return _HAS_ASYNCUA

    # ------------------------------------------------------------------
    def connect(self) -> Tuple[bool, str]:
        if not _HAS_ASYNCUA:
            self.last_error = "asyncua not installed (pip install asyncua)"
            return (False, self.last_error)
        try:
            self._client = Client(url=self.url, timeout=self.timeout_sec)
            if self.username:
                self._client.set_user(self.username)
                if self.password:
                    self._client.set_password(self.password)
            self._client.connect()
            self.connected = True
            self.last_error = ""
            _LOG.info("connected to %s", self.url)
            return (True, "")
        except Exception as e:
            self.connected = False
            self.last_error = f"{type(e).__name__}: {e}"
            _LOG.warning("connect failed: %s", self.last_error)
            return (False, self.last_error)

    # ------------------------------------------------------------------
    def disconnect(self):
        if self._client and self.connected:
            try:
                self._client.disconnect()
            except Exception as e:
                _LOG.warning("disconnect failed: %s", e)
        self._client = None
        self.connected = False

    # ------------------------------------------------------------------
    def read_one(self, node_id: str) -> Tuple[bool, Any, str]:
        """Read a single NodeId. Returns (ok, value, error)."""
        if not self.connected or self._client is None:
            return (False, None, "not connected")
        try:
            node = self._client.get_node(node_id)
            value = node.read_value()
            return (True, value, "")
        except Exception as e:
            return (False, None, f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    def read_many(self, node_ids: List[str]) -> Dict[str, Tuple[bool, Any, str]]:
        """Read a list of NodeIds in one round-trip when possible.

        Returns a dict {node_id: (ok, value, error)}.
        """
        out: Dict[str, Tuple[bool, Any, str]] = {}
        if not self.connected or self._client is None:
            for nid in node_ids:
                out[nid] = (False, None, "not connected")
            return out
        # Try the batched read first; fall back to per-node on failure
        try:
            nodes = [self._client.get_node(nid) for nid in node_ids]
            values = self._client.read_values(nodes)
            for nid, val in zip(node_ids, values):
                out[nid] = (True, val, "")
            return out
        except Exception as e:
            _LOG.debug("batched read failed (%s); falling back to per-node", e)
        for nid in node_ids:
            out[nid] = self.read_one(nid)
        return out

    # ------------------------------------------------------------------
    def write_one(self, node_id: str, value: Any, datatype: str) -> Tuple[bool, str]:
        """Write a single value. Returns (ok, error)."""
        if not self.connected or self._client is None:
            return (False, "not connected")
        try:
            node = self._client.get_node(node_id)
            dv = _to_variant(value, datatype)
            node.write_value(dv)
            return (True, "")
        except Exception as e:
            return (False, f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    def write_many(
        self, writes: Dict[str, Tuple[Any, str]]
    ) -> Dict[str, Tuple[bool, str]]:
        """Write multiple {node_id: (value, datatype)} pairs.

        Returns {node_id: (ok, error)}. Falls back to per-node writes if
        the batched call raises.
        """
        out: Dict[str, Tuple[bool, str]] = {}
        if not self.connected or self._client is None:
            for nid in writes:
                out[nid] = (False, "not connected")
            return out
        try:
            nodes = []
            dvs = []
            order = []
            for nid, (val, dt) in writes.items():
                nodes.append(self._client.get_node(nid))
                dvs.append(_to_variant(val, dt))
                order.append(nid)
            self._client.write_values(nodes, dvs)
            for nid in order:
                out[nid] = (True, "")
            return out
        except Exception as e:
            _LOG.debug("batched write failed (%s); falling back to per-node", e)
        for nid, (val, dt) in writes.items():
            out[nid] = self.write_one(nid, val, dt)
        return out

    # ------------------------------------------------------------------
    def browse_root(self, max_depth: int = 3) -> List[Dict]:
        """Walk the Objects folder; return a tree of {name, node_id, children}.

        Used by the Tag Browser pane in the Deployment GUI.
        """
        if not self.connected or self._client is None:
            return []
        try:
            objects = self._client.nodes.objects
            return [_walk_node(objects, max_depth)]
        except Exception as e:
            _LOG.warning("browse failed: %s", e)
            return []


def _walk_node(node, depth: int) -> Dict:
    """Recursive helper for browse_root."""
    try:
        name = node.read_browse_name().Name
    except Exception:
        name = "?"
    try:
        nid = node.nodeid.to_string()
    except Exception:
        nid = ""
    out = {"name": name, "node_id": nid, "children": []}
    if depth <= 0:
        return out
    try:
        for child in node.get_children():
            out["children"].append(_walk_node(child, depth - 1))
    except Exception:
        pass
    return out
