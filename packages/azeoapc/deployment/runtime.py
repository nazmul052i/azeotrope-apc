"""Deployment runtime: read PVs over OPC UA, step engine, write SPs back.

This is what DMC3 calls the "Online" controller. It runs in a Qt worker
thread so the GUI stays responsive. Each cycle:

  1. Read all CV measurement + DV measurement nodes from the plant.
  2. Run validity checks; on failure, increment the per-variable
     read-failure counter and substitute the last good value.
  3. If too many failures, mark the variable BAD; if the counter exceeds
     read_failure_limit, abort that variable (skip the engine update).
  4. Push the read PVs into the engine's CV/DV objects.
  5. Call engine.step() to advance the controller.
  6. Read the new MV values back from the engine.
  7. Write each MV setpoint to its OPC node. Increment write-failure
     counters on failure.
  8. Push controller telemetry (Cycle, Status, Watchdog) to the General
     nodes.
  9. Sleep until the next sample period.

Stop condition: ``stop()`` flips the run flag and the loop exits at the
next safe point.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from .cycle_engine import CycleEngine
from .opcua_client import OpcUaClient
from .tag_model import (
    DeploymentConfig, IOTag, ParamRole, VarType, VariableDeployment,
)

_LOG = logging.getLogger("azeoapc.deployment.runtime")


class DeploymentRuntime(QThread):
    """Background thread that drives the deployment cycle loop."""

    # Signals to the GUI
    cycle_completed = Signal(int, float)        # cycle_number, total_ms
    status_changed = Signal(str)                # "STARTING" | "RUNNING" | "STOPPED" | "ERROR: ..."
    variable_status = Signal(str, str, float)   # var_tag, status, value
    log = Signal(str, str)                      # level, message

    def __init__(self, engine, deployment_cfg: DeploymentConfig,
                 embedded_server=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.dep_cfg = deployment_cfg
        self.embedded = embedded_server  # optional EmbeddedPlantServer
        self._stop_requested = False
        self.cycle_count = 0
        self.last_cycle_ms = 0.0
        # Headless cycle engine that does the actual work; the QThread
        # wrapper just bridges its callbacks onto Qt signals.
        self._cycle_engine: Optional[CycleEngine] = None

    # ------------------------------------------------------------------
    def request_stop(self):
        self._stop_requested = True

    # ------------------------------------------------------------------
    def run(self):
        """QThread entry point -- DO NOT call directly, use start()."""
        self._stop_requested = False
        self.cycle_count = 0
        self.status_changed.emit("STARTING")

        # Build the headless cycle engine and route its callbacks
        # through Qt signals so the GUI gets live updates.
        self._cycle_engine = CycleEngine(
            engine=self.engine,
            deployment_cfg=self.dep_cfg,
            embedded_server=self.embedded,
            log=lambda lvl, msg: self.log.emit(lvl, msg),
            on_variable_status=lambda t, s, v: self.variable_status.emit(t, s, v),
        )
        ok, err = self._cycle_engine.connect()
        if not ok:
            self.status_changed.emit(f"ERROR: {err}")
            return
        self.status_changed.emit("RUNNING")

        sample_period = max(self.engine.cfg.sample_time, 0.05)
        wall_period = sample_period  # treat as seconds for live demo

        try:
            while not self._stop_requested:
                t0 = time.perf_counter()
                result = self._cycle_engine.run_one_cycle()
                self.last_cycle_ms = result.duration_ms
                self.cycle_count = result.cycle + 1
                self.cycle_completed.emit(result.cycle, result.duration_ms)
                slept = (time.perf_counter() - t0)
                if slept < wall_period:
                    time.sleep(wall_period - slept)
        except Exception as e:
            self.log.emit("error", f"runtime crash: {type(e).__name__}: {e}")
            self.status_changed.emit(f"ERROR: {e}")
        finally:
            if self._cycle_engine is not None:
                self._cycle_engine.disconnect()
            self.status_changed.emit("STOPPED")
            self.log.emit("info", "runtime stopped")

    # The cycle logic now lives in CycleEngine. This Qt wrapper just
    # bridges the cycle engine's callbacks onto Qt signals so the GUI
    # can drive its live status displays.
