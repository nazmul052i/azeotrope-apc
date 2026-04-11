"""Headless cycle engine -- pure Python, no Qt.

Extracted from ``DeploymentRuntime`` so apc_runtime (headless) and
apc_architect's deployment GUI (Qt) can share one canonical cycle
implementation. The cycle order is the same as DMC3's online controller:

  1. Read all CV measurement + DV measurement nodes from the plant.
  2. Run validity checks; on failure, increment the per-variable
     read-failure counter and substitute the last good value.
  3. If too many failures, mark the variable BAD/OFFLINE.
  4. Push the read PVs into the engine's CV/DV objects.
  5. Call engine.step() to advance the controller.
  6. Read the new MV values back from the engine.
  7. Write each MV setpoint to its OPC node. Increment write-failure
     counters on failure.
  8. Push controller telemetry (Cycle, Status, Watchdog) to the
     General nodes if an embedded server is in the loop.

The class is intentionally side-effect-free except for the OPC client
calls and the engine step. Logging and telemetry callbacks are
injected so the caller (Qt or threading) can route them however it
likes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .opcua_client import OpcUaClient
from .tag_model import (
    DeploymentConfig, IOTag, ParamRole, VarType, VariableDeployment,
)

_LOG = logging.getLogger("azeoapc.deployment.cycle_engine")


# Callback types
LogCallback = Callable[[str, str], None]                  # (level, message)
VarStatusCallback = Callable[[str, str, float], None]     # (tag, status, value)


@dataclass
class CycleResult:
    """Per-cycle summary returned by ``CycleEngine.run_one_cycle``."""
    cycle: int
    duration_ms: float = 0.0
    n_reads_ok: int = 0
    n_reads_failed: int = 0
    n_writes_ok: int = 0
    n_writes_failed: int = 0
    engine_ok: bool = True
    engine_error: str = ""
    bad_variables: List[str] = field(default_factory=list)


class CycleEngine:
    """Stateless wrapper around the read-step-write cycle.

    Holds a reference to the SimEngine, the deployment config, and an
    OpcUaClient. Each call to ``run_one_cycle()`` performs one full
    pass and returns a ``CycleResult`` summarising what happened.

    Lifecycle:
        ce = CycleEngine(engine, dep_cfg, embedded_server=server)
        ok, err = ce.connect()
        while running:
            result = ce.run_one_cycle()
            ...
        ce.disconnect()

    The class deliberately does NOT spawn its own thread or sleep --
    that's the caller's job. apc_architect wraps it in a QThread,
    apc_runtime wraps it in a stdlib threading.Thread.
    """

    def __init__(
        self,
        engine,
        deployment_cfg: DeploymentConfig,
        embedded_server=None,
        log: Optional[LogCallback] = None,
        on_variable_status: Optional[VarStatusCallback] = None,
    ):
        self.engine = engine
        self.dep_cfg = deployment_cfg
        self.embedded = embedded_server
        self._log_cb = log or (lambda lvl, msg: None)
        self._var_cb = on_variable_status or (lambda t, s, v: None)
        self.client: Optional[OpcUaClient] = None
        self.cycle_count = 0

    # ------------------------------------------------------------------
    def connect(self) -> tuple:
        """Connect to the OPC UA server. Returns (ok, error_msg)."""
        if self.client is not None:
            return (True, "")
        self.client = OpcUaClient(
            self.dep_cfg.server_url,
            self.dep_cfg.server_username,
            self.dep_cfg.server_password,
        )
        ok, err = self.client.connect()
        if ok:
            self._log_cb("info", f"connected to {self.dep_cfg.server_url}")
        else:
            self._log_cb("error", f"connect failed: {err}")
            self.client = None
        return ok, err

    def disconnect(self):
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception as e:
                _LOG.warning("disconnect: %s", e)
            self.client = None

    # ------------------------------------------------------------------
    def run_one_cycle(self) -> CycleResult:
        """One pass of read -> validate -> engine.step() -> write."""
        import time
        result = CycleResult(cycle=self.cycle_count)
        t0 = time.perf_counter()

        cfg = self.dep_cfg
        engine = self.engine

        if self.embedded is not None:
            self.embedded.push_pv_state()

        # ── 1. Collect read NodeIds for CV/DV measurements + MV feedback ──
        read_nodes: List[str] = []
        node_to_var: Dict[str, VariableDeployment] = {}
        node_to_role: Dict[str, str] = {}  # cv | dv | mv_fb
        for vd in cfg.variables:
            if vd.var_type not in (VarType.INPUT, VarType.DISTURBANCE,
                                   VarType.OUTPUT):
                continue
            for tag in vd.io_tags:
                if tag.parameter == "Measurement":
                    read_nodes.append(tag.node_id)
                    node_to_var[tag.node_id] = vd
                    node_to_role[tag.node_id] = (
                        "cv" if vd.var_type == VarType.INPUT
                        else "dv" if vd.var_type == VarType.DISTURBANCE
                        else "mv_fb")
                elif (tag.parameter == "SetPointFeedback"
                      and vd.var_type == VarType.OUTPUT):
                    read_nodes.append(tag.node_id)
                    node_to_var[tag.node_id] = vd
                    node_to_role[tag.node_id] = "mv_fb"

        # ── 2. Read them in one batch ──
        results = (self.client.read_many(read_nodes)
                   if read_nodes and self.client is not None else {})

        # ── 3. Validate + push to engine ──
        cv_by_tag = {cv.tag: cv for cv in engine.cfg.cvs}
        mv_by_tag = {mv.tag: mv for mv in engine.cfg.mvs}
        dv_by_tag = {dv.tag: dv for dv in engine.cfg.dvs}

        for nid, (ok, value, err) in results.items():
            vd = node_to_var[nid]
            role = node_to_role[nid]
            if not ok:
                vd.read_failure_count += 1
                vd.last_status = "BAD"
                if vd.read_failure_count >= cfg.general_settings.read_failure_limit:
                    vd.last_status = "OFFLINE"
                self._var_cb(vd.variable_tag, vd.last_status,
                             vd.last_good_value or 0.0)
                self._log_cb("warn", f"read {vd.variable_tag}: {err}")
                result.n_reads_failed += 1
                result.bad_variables.append(vd.variable_tag)
                continue

            try:
                fval = float(value)
            except Exception:
                vd.read_failure_count += 1
                vd.last_status = "BAD"
                result.n_reads_failed += 1
                result.bad_variables.append(vd.variable_tag)
                continue

            v = vd.validation
            if not (v.validity_lo <= fval <= v.validity_hi):
                vd.read_failure_count += 1
                vd.last_status = "BAD"
                self._log_cb("warn",
                             f"{vd.variable_tag} reading {fval:.4g} outside "
                             f"validity [{v.validity_lo}, {v.validity_hi}]")
                self._var_cb(vd.variable_tag, "BAD", fval)
                result.n_reads_failed += 1
                result.bad_variables.append(vd.variable_tag)
                continue

            vd.read_failure_count = 0
            vd.last_good_value = fval
            vd.last_status = "OK"
            self._var_cb(vd.variable_tag, "OK", fval)
            result.n_reads_ok += 1

            if role == "cv" and vd.variable_tag in cv_by_tag:
                cv_by_tag[vd.variable_tag].value = fval
            elif role == "dv" and vd.variable_tag in dv_by_tag:
                dv_by_tag[vd.variable_tag].value = fval
            # mv_fb is informational -- don't override engine.u

        # ── 4. Step the engine ──
        try:
            engine.step()
            result.engine_ok = True
        except Exception as e:
            result.engine_ok = False
            result.engine_error = f"{type(e).__name__}: {e}"
            self._log_cb("error", f"engine.step() failed: {e}")
            result.duration_ms = (time.perf_counter() - t0) * 1000.0
            return result

        # ── 5. Write MV setpoints back ──
        writes: Dict[str, tuple] = {}
        write_routing: Dict[str, VariableDeployment] = {}
        for vd in cfg.variables:
            if vd.var_type != VarType.OUTPUT:
                continue
            if vd.variable_tag not in mv_by_tag:
                continue
            mv = mv_by_tag[vd.variable_tag]
            sp_tag = next(
                (t for t in vd.io_tags if t.parameter == "SetPoint"), None)
            if sp_tag is None:
                continue
            writes[sp_tag.node_id] = (float(mv.value), sp_tag.datatype)
            write_routing[sp_tag.node_id] = vd

        if writes and self.client is not None:
            wresults = self.client.write_many(writes)
            for nid, (ok, err) in wresults.items():
                vd = write_routing[nid]
                if ok:
                    vd.write_failure_count = 0
                    result.n_writes_ok += 1
                else:
                    vd.write_failure_count += 1
                    result.n_writes_failed += 1
                    self._log_cb("warn", f"write {vd.variable_tag}.SP: {err}")
                    if (vd.write_failure_count
                            >= cfg.general_settings.write_failure_limit):
                        vd.last_status = "WRITE_FAIL"

        # ── 6. Push controller telemetry ──
        if self.embedded is not None:
            self.embedded.push_controller_telemetry(
                self.cycle_count, status=0 if engine.last_ok else 1,
                abort=not engine.last_ok)

        result.duration_ms = (time.perf_counter() - t0) * 1000.0
        self.cycle_count += 1
        return result
