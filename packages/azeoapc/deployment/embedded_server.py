"""Embedded OPC UA test server.

Publishes the simulator's CV/MV/DV values as nodes under
``ns=2;s=Plant.{tag}.{role}`` so the user can point the deployment loop
at themselves and exercise the full Read -> Step -> Write loop without
needing any external infrastructure.

Layout:
    Objects/
        Plant/
            <CV-tag>/
                PV    (Double, RW)        -- live measurement
                Status (Int32, RO)        -- 0 = good
                ...
            <MV-tag>/
                SP        (Double, RW)    -- setpoint written by deployment loop
                SP_FB     (Double, RO)    -- read-back of last applied SP
                Manual    (Boolean, RW)
                ...
            <DV-tag>/
                PV    (Double, RW)
        Controller/
            Status, Cycle, Watchdog, ...

The server runs on a background thread (asyncua.sync.Server which manages
its own asyncio loop). The simulator's PVs are pushed to the server every
``publish_interval`` seconds via ``push_state()``; the SP nodes are pulled
back via ``pull_setpoints()`` so the deployment loop sees its own writes.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional

try:
    from asyncua.sync import Server
    from asyncua import ua
    _HAS_ASYNCUA = True
except ImportError:
    _HAS_ASYNCUA = False
    Server = None  # type: ignore
    ua = None  # type: ignore

_LOG = logging.getLogger("azeoapc.deployment.embedded")

NS_URI = "urn:azeoapc:plant"


class EmbeddedPlantServer:
    """Tiny OPC UA server that mirrors a SimEngine's plant state.

    Not threadsafe across simultaneous reads/writes from multiple clients,
    but fine for the single-client deployment loop in this simulator.
    """

    def __init__(
        self, engine, endpoint: str = "opc.tcp://localhost:4840/azeoapc/server/",
    ):
        self.engine = engine
        self.endpoint = endpoint
        self._server: Optional[Server] = None
        self._ns_idx = 0
        self.running = False
        self.last_error = ""

        # NodeId -> (kind, index)
        # kind in {"cv_pv", "mv_sp", "mv_sp_fb", "dv_pv", "ctrl_*"}
        self._nodes: Dict[str, "ua.Node"] = {}

    # ------------------------------------------------------------------
    @staticmethod
    def is_available() -> bool:
        return _HAS_ASYNCUA

    # ------------------------------------------------------------------
    def start(self):
        if not _HAS_ASYNCUA:
            self.last_error = "asyncua not installed"
            return False
        if self.running:
            return True
        try:
            self._server = Server()
            self._server.set_endpoint(self.endpoint)
            self._server.set_server_name("Azeotrope APC Embedded Plant")
            self._ns_idx = self._server.register_namespace(NS_URI)
            self._build_address_space()
            self._server.start()
            self.running = True
            self.last_error = ""
            _LOG.info("embedded server started at %s", self.endpoint)
            return True
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            _LOG.warning("embedded server start failed: %s", self.last_error)
            self._server = None
            return False

    # ------------------------------------------------------------------
    def stop(self):
        if self._server and self.running:
            try:
                self._server.stop()
            except Exception as e:
                _LOG.warning("embedded server stop failed: %s", e)
        self._server = None
        self._nodes.clear()
        self.running = False

    # ------------------------------------------------------------------
    def _build_address_space(self):
        """Create one folder per variable plus a Controller telemetry folder."""
        objects = self._server.nodes.objects
        plant_folder = objects.add_folder(f"ns={self._ns_idx};s=Plant", "Plant")
        ctrl_folder = objects.add_folder(f"ns={self._ns_idx};s=Controller", "Controller")

        cfg = self.engine.cfg

        # CVs -- read-only PV from the engine
        for cv in cfg.cvs:
            f = plant_folder.add_folder(f"ns={self._ns_idx};s=Plant.{cv.tag}", cv.tag)
            pv = f.add_variable(
                f"ns={self._ns_idx};s=Plant.{cv.tag}.PV", "PV", float(cv.value),
                varianttype=ua.VariantType.Double)
            pv.set_writable()
            self._nodes[f"ns={self._ns_idx};s=Plant.{cv.tag}.PV"] = pv

            status = f.add_variable(
                f"ns={self._ns_idx};s=Plant.{cv.tag}.Status", "Status", 0,
                varianttype=ua.VariantType.Int32)
            self._nodes[f"ns={self._ns_idx};s=Plant.{cv.tag}.Status"] = status

        # MVs -- writable SP, read-only feedback
        for mv in cfg.mvs:
            f = plant_folder.add_folder(f"ns={self._ns_idx};s=Plant.{mv.tag}", mv.tag)
            sp = f.add_variable(
                f"ns={self._ns_idx};s=Plant.{mv.tag}.SP", "SP", float(mv.value),
                varianttype=ua.VariantType.Double)
            sp.set_writable()
            self._nodes[f"ns={self._ns_idx};s=Plant.{mv.tag}.SP"] = sp

            sp_fb = f.add_variable(
                f"ns={self._ns_idx};s=Plant.{mv.tag}.SP_FB", "SP_FB", float(mv.value),
                varianttype=ua.VariantType.Double)
            self._nodes[f"ns={self._ns_idx};s=Plant.{mv.tag}.SP_FB"] = sp_fb

            manual = f.add_variable(
                f"ns={self._ns_idx};s=Plant.{mv.tag}.Manual", "Manual", False,
                varianttype=ua.VariantType.Boolean)
            manual.set_writable()
            self._nodes[f"ns={self._ns_idx};s=Plant.{mv.tag}.Manual"] = manual

        # DVs -- writable PV (DCS would write disturbance values)
        for dv in cfg.dvs:
            f = plant_folder.add_folder(f"ns={self._ns_idx};s=Plant.{dv.tag}", dv.tag)
            pv = f.add_variable(
                f"ns={self._ns_idx};s=Plant.{dv.tag}.PV", "PV", float(dv.value),
                varianttype=ua.VariantType.Double)
            pv.set_writable()
            self._nodes[f"ns={self._ns_idx};s=Plant.{dv.tag}.PV"] = pv

        # Controller telemetry
        for name, default, vt in [
            ("Status", 0, ua.VariantType.Int32),
            ("Cycle", 0, ua.VariantType.Int32),
            ("RunCount", 0, ua.VariantType.Int32),
            ("FailCount", 0, ua.VariantType.Int32),
            ("Abort", False, ua.VariantType.Boolean),
            ("OnOffRequest", True, ua.VariantType.Boolean),
            ("OnOffStatus", True, ua.VariantType.Boolean),
            ("Watchdog", 0, ua.VariantType.Int32),
            ("AvgPredError", 0.0, ua.VariantType.Double),
            ("ActualMoves", 0.0, ua.VariantType.Double),
        ]:
            v = ctrl_folder.add_variable(
                f"ns={self._ns_idx};s=Controller.{name}", name, default,
                varianttype=vt)
            if name == "OnOffRequest":
                v.set_writable()
            self._nodes[f"ns={self._ns_idx};s=Controller.{name}"] = v

    # ------------------------------------------------------------------
    def push_pv_state(self):
        """Push the latest CV/DV PVs from the engine into the OPC nodes.

        Called by the deployment runtime each cycle BEFORE it reads back.
        This is what makes the embedded server behave like a real plant:
        the engine's plant model evolves -> we publish PVs -> the
        deployment loop reads them back as if they came from the field.
        """
        if not self.running or self._server is None:
            return
        cfg = self.engine.cfg
        try:
            for cv in cfg.cvs:
                node = self._nodes.get(f"ns={self._ns_idx};s=Plant.{cv.tag}.PV")
                if node is not None:
                    node.write_value(float(cv.value))
            for dv in cfg.dvs:
                node = self._nodes.get(f"ns={self._ns_idx};s=Plant.{dv.tag}.PV")
                if node is not None:
                    node.write_value(float(dv.value))
            # Mirror MV value to feedback so the SP_FB tag is correct
            for mv in cfg.mvs:
                node = self._nodes.get(f"ns={self._ns_idx};s=Plant.{mv.tag}.SP_FB")
                if node is not None:
                    node.write_value(float(mv.value))
        except Exception as e:
            _LOG.debug("push_pv_state failed: %s", e)

    # ------------------------------------------------------------------
    def push_controller_telemetry(self, cycle: int, status: int = 0,
                                   abort: bool = False):
        """Push controller diagnostic telemetry to the General nodes."""
        if not self.running or self._server is None:
            return
        try:
            ns = self._ns_idx

            def _i32(v: int):
                return ua.DataValue(ua.Variant(int(v), ua.VariantType.Int32))

            self._nodes[f"ns={ns};s=Controller.Cycle"].write_value(_i32(cycle))
            self._nodes[f"ns={ns};s=Controller.Status"].write_value(_i32(status))
            self._nodes[f"ns={ns};s=Controller.Abort"].write_value(bool(abort))
            self._nodes[f"ns={ns};s=Controller.Watchdog"].write_value(
                _i32(cycle % 1000))
            # Cumulative counters
            run = int(
                self._nodes[f"ns={ns};s=Controller.RunCount"].read_value())
            self._nodes[f"ns={ns};s=Controller.RunCount"].write_value(_i32(run + 1))
        except Exception as e:
            _LOG.debug("push_controller_telemetry failed: %s", e)

    # ------------------------------------------------------------------
    def pull_mv_setpoints(self) -> Dict[str, float]:
        """Read SP nodes back into a dict {mv_tag: sp_value}.

        The deployment loop normally writes the SPs and the next cycle's
        engine.step() applies them. This helper exists for tests / for
        loops that want to verify the writes round-tripped.
        """
        out: Dict[str, float] = {}
        if not self.running or self._server is None:
            return out
        ns = self._ns_idx
        for mv in self.engine.cfg.mvs:
            node = self._nodes.get(f"ns={ns};s=Plant.{mv.tag}.SP")
            if node is not None:
                try:
                    out[mv.tag] = float(node.read_value())
                except Exception:
                    pass
        return out
