"""Single-controller Runner -- one SimEngine on a worker thread.

The Runner owns:
  * The SimConfig + SimEngine built from a .apcproj file
  * The CycleEngine that drives the read-step-write loop
  * An optional EmbeddedPlantServer (for self-test deployments)
  * A CycleLogWriter (JSON-lines + latest.json snapshot)
  * An optional Historian (SQLite)

Lifecycle:
  r = Runner(project_path, run_dir="runs/fired_heater")
  r.start()        # spawns a worker thread, returns immediately
  r.snapshot()     # call from another thread to read latest state
  r.pause()        # cycle loop sleeps but stays connected
  r.resume()
  r.stop()         # graceful stop, joins the worker thread
  r.reload()       # re-read tuning sections from the .apcproj file

The cycle loop sleeps `sample_time` seconds between cycles. The Runner
deliberately uses stdlib `threading.Thread` -- not QThread -- so it
runs on a headless server with no Qt installed.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from azeoapc.deployment.cycle_engine import CycleEngine, CycleResult
from azeoapc.deployment.tag_model import (
    DeploymentConfig, VarType, VariableDeployment, ValidationLimits,
)
from azeoapc.deployment.tag_templates import generate_io_tags
from azeoapc.models.config_loader import SimConfig, load_config
from azeoapc.sim_engine import SimEngine

from .historian import Historian
from .historian_forwarder import HistorianForwarder
from .log_writer import CycleLogWriter, build_cycle_record


_LOG = logging.getLogger("apc_runtime.runner")


class RunnerStatus(str, Enum):
    IDLE     = "IDLE"
    STARTING = "STARTING"
    RUNNING  = "RUNNING"
    PAUSED   = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED  = "STOPPED"
    ERROR    = "ERROR"


@dataclass
class RunnerSnapshot:
    """Lightweight serialisable snapshot of a Runner's state.

    Returned by ``Runner.snapshot()`` and used by the REST surface to
    answer ``GET /status``. Held by the Runner under a lock so external
    callers always see a consistent view.
    """
    controller_name: str = ""
    project_path: str = ""
    status: str = RunnerStatus.IDLE.value
    cycle: int = 0
    last_cycle_ms: float = 0.0
    avg_cycle_ms: float = 0.0
    total_cycles: int = 0
    started_at: Optional[str] = None
    last_error: str = ""
    n_cv: int = 0
    n_mv: int = 0
    n_dv: int = 0
    bad_variables: list = field(default_factory=list)


class Runner:
    """One controller's full runtime: load config, build engine, run cycles."""

    def __init__(
        self,
        project_path: str,
        run_dir: Optional[str] = None,
        *,
        use_embedded_server: bool = True,
        enable_historian: bool = True,
        wall_period: Optional[float] = None,
        historian_url: Optional[str] = None,
    ):
        self.project_path = os.path.abspath(project_path)
        self.run_dir = os.path.abspath(
            run_dir or os.path.join("runs", _slug(os.path.basename(project_path))))
        self.use_embedded_server = use_embedded_server
        self.enable_historian = enable_historian
        self.historian_url = historian_url
        self._wall_period_override = wall_period

        self.cfg: Optional[SimConfig] = None
        self.engine: Optional[SimEngine] = None
        self.cycle_engine: Optional[CycleEngine] = None
        self.embedded_server = None
        self.log_writer: Optional[CycleLogWriter] = None
        self.historian: Optional[Historian] = None
        self.forwarder: Optional[HistorianForwarder] = None

        # Threading + state
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._lock = threading.Lock()
        self._snapshot = RunnerSnapshot(project_path=self.project_path)
        self._cycle_ms_ema: float = 0.0
        self._reload_requested = False

    # ==================================================================
    # Public API
    # ==================================================================
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"apc-runner-{_slug(self.project_path)}",
            daemon=True)
        self._thread.start()

    def stop(self, join_timeout: float = 10.0) -> None:
        self._stop_event.set()
        self._pause_event.clear()  # don't deadlock pause
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
            self._thread = None

    def pause(self) -> None:
        self._pause_event.set()
        with self._lock:
            self._snapshot.status = RunnerStatus.PAUSED.value

    def resume(self) -> None:
        self._pause_event.clear()
        with self._lock:
            if self._snapshot.status == RunnerStatus.PAUSED.value:
                self._snapshot.status = RunnerStatus.RUNNING.value

    def reload(self) -> None:
        """Request a tuning reload at the next cycle boundary.

        Re-reads the .apcproj file and copies tunable fields (CV
        weights, setpoints, MV move suppression, limits) into the live
        engine WITHOUT rebuilding the controller. Variable structure
        and plant model are NOT touched -- a structural change requires
        stop + start.
        """
        self._reload_requested = True

    # ==================================================================
    # Operator actions (called from REST -- thread-safe via _lock)
    # ==================================================================
    def set_cv_setpoint(self, cv_tag: str, setpoint: float) -> bool:
        """Push a new setpoint to one CV. Returns True if found."""
        if self.engine is None:
            return False
        with self._lock:
            for cv in self.engine.cfg.cvs:
                if cv.tag == cv_tag:
                    cv.setpoint = float(setpoint)
                    self._apply_opt_type_safe()
                    if self.log_writer:
                        self.log_writer.write_event(
                            "info",
                            f"operator: set {cv_tag}.setpoint = {setpoint}")
                    return True
        return False

    def set_cv_limits(self, cv_tag: str, lo: Optional[float] = None,
                       hi: Optional[float] = None) -> bool:
        """Update one CV's operating limits."""
        if self.engine is None:
            return False
        with self._lock:
            for cv in self.engine.cfg.cvs:
                if cv.tag == cv_tag:
                    if lo is not None:
                        cv.limits.operating_lo = float(lo)
                    if hi is not None:
                        cv.limits.operating_hi = float(hi)
                    self._apply_opt_type_safe()
                    if self.log_writer:
                        self.log_writer.write_event(
                            "info",
                            f"operator: set {cv_tag} limits lo={lo} hi={hi}")
                    return True
        return False

    def set_mv_limits(self, mv_tag: str, lo: Optional[float] = None,
                       hi: Optional[float] = None) -> bool:
        """Update one MV's operating limits."""
        if self.engine is None:
            return False
        with self._lock:
            for mv in self.engine.cfg.mvs:
                if mv.tag == mv_tag:
                    if lo is not None:
                        mv.limits.operating_lo = float(lo)
                    if hi is not None:
                        mv.limits.operating_hi = float(hi)
                    self._apply_opt_type_safe()
                    if self.log_writer:
                        self.log_writer.write_event(
                            "info",
                            f"operator: set {mv_tag} limits lo={lo} hi={hi}")
                    return True
        return False

    def set_mv_move_suppress(self, mv_tag: str, value: float) -> bool:
        """Update one MV's move-suppression weight."""
        if self.engine is None:
            return False
        with self._lock:
            for mv in self.engine.cfg.mvs:
                if mv.tag == mv_tag:
                    mv.move_suppress = float(value)
                    self._apply_opt_type_safe()
                    if self.log_writer:
                        self.log_writer.write_event(
                            "info",
                            f"operator: set {mv_tag}.move_suppress = {value}")
                    return True
        return False

    def _apply_opt_type_safe(self):
        """Best-effort push of tuning into the C++ controller."""
        if hasattr(self.engine, "apply_opt_type"):
            try:
                self.engine.apply_opt_type()
            except Exception as e:
                _LOG.warning("apply_opt_type failed: %s", e)

    def snapshot(self) -> RunnerSnapshot:
        with self._lock:
            # Return a defensive copy
            from dataclasses import replace
            return replace(self._snapshot,
                            bad_variables=list(self._snapshot.bad_variables))

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ==================================================================
    # Worker thread
    # ==================================================================
    def _run(self) -> None:
        self._set_status(RunnerStatus.STARTING)
        try:
            self._init_engine_and_io()
        except Exception as e:
            _LOG.exception("Runner init failed")
            with self._lock:
                self._snapshot.status = RunnerStatus.ERROR.value
                self._snapshot.last_error = f"{type(e).__name__}: {e}"
            return

        # Connect to OPC UA
        ok, err = self.cycle_engine.connect()
        if not ok:
            with self._lock:
                self._snapshot.status = RunnerStatus.ERROR.value
                self._snapshot.last_error = f"OPC connect failed: {err}"
            self._teardown()
            return

        wall_period = self._wall_period_override or max(
            float(self.cfg.sample_time), 0.05)
        with self._lock:
            self._snapshot.status = RunnerStatus.RUNNING.value
            self._snapshot.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.log_writer.write_event(
            "info", f"Runner started: {self.cfg.name}, dt={wall_period}s")

        try:
            while not self._stop_event.is_set():
                # Pause check
                if self._pause_event.is_set():
                    time.sleep(0.1)
                    continue

                # Reload check (between cycles only)
                if self._reload_requested:
                    self._do_reload()
                    self._reload_requested = False

                t0 = time.perf_counter()
                result = self.cycle_engine.run_one_cycle()
                self._handle_cycle_result(result)
                slept = time.perf_counter() - t0
                if slept < wall_period:
                    # Sleep in chunks so stop is responsive
                    remaining = wall_period - slept
                    end = time.perf_counter() + remaining
                    while not self._stop_event.is_set():
                        chunk = min(0.1, end - time.perf_counter())
                        if chunk <= 0:
                            break
                        time.sleep(chunk)
        except Exception as e:
            _LOG.exception("Runner crashed")
            with self._lock:
                self._snapshot.status = RunnerStatus.ERROR.value
                self._snapshot.last_error = f"{type(e).__name__}: {e}"
            if self.log_writer:
                self.log_writer.write_event(
                    "error", f"Runner crashed: {e}")
        finally:
            self._teardown()

    # ------------------------------------------------------------------
    def _init_engine_and_io(self) -> None:
        """Load config, build SimEngine, set up CycleEngine + log + historian."""
        self.cfg = load_config(self.project_path)
        self.engine = SimEngine(self.cfg)

        # Use the deployment config from the .apcproj if it exists,
        # otherwise build a default one with auto-generated tags so
        # the user can plug in a real OPC server later.
        dep_cfg = getattr(self.cfg, "deployment", None)
        if dep_cfg is None:
            dep_cfg = self._default_deployment_config()
            self.cfg.deployment = dep_cfg

        # Optionally bring up the embedded plant server (for self-test
        # deployments where the plant model IS the simulator).
        if self.use_embedded_server:
            from azeoapc.deployment.embedded_server import EmbeddedPlantServer
            self.embedded_server = EmbeddedPlantServer(
                self.engine, endpoint=dep_cfg.server_url)
            ok = self.embedded_server.start()
            if not ok:
                err = self.embedded_server.last_error or "unknown"
                _LOG.warning("embedded server start failed: %s", err)
                self.embedded_server = None
                # Surface the failure: without an embedded server AND
                # no real OPC server out there, the cycle engine has
                # nothing to talk to. Fail loudly so REST callers see it.
                raise RuntimeError(
                    f"Embedded OPC UA server failed to start at "
                    f"{dep_cfg.server_url}: {err}")

        # Log writer
        self.log_writer = CycleLogWriter(
            self.run_dir, controller_name=self.cfg.name)
        self.log_writer.write_event(
            "info", f"loaded {self.project_path}")

        # Historian (local SQLite)
        if self.enable_historian:
            db_path = os.path.join(self.run_dir, "history.db")
            self.historian = Historian(db_path)
            self.historian.init_schema(
                controller_name=self.cfg.name,
                cv_names=[cv.tag for cv in self.cfg.cvs],
                mv_names=[mv.tag for mv in self.cfg.mvs],
                dv_names=[dv.tag for dv in self.cfg.dvs],
            )

        # Optional centralized historian forwarder
        if self.historian_url:
            self.forwarder = HistorianForwarder(self.historian_url)
            self.forwarder.start()
            self.log_writer.write_event(
                "info", f"forwarding cycles to {self.historian_url}")

        # Build the headless cycle engine
        self.cycle_engine = CycleEngine(
            engine=self.engine,
            deployment_cfg=dep_cfg,
            embedded_server=self.embedded_server,
            log=lambda lvl, msg: self.log_writer.write_event(lvl, msg),
        )

        with self._lock:
            self._snapshot.controller_name = self.cfg.name
            self._snapshot.n_cv = len(self.cfg.cvs)
            self._snapshot.n_mv = len(self.cfg.mvs)
            self._snapshot.n_dv = len(self.cfg.dvs)

    # ------------------------------------------------------------------
    # OPC UA port pool. Each Runner picks the next available port so
    # multiple controllers in the same MultiRunner don't collide.
    _next_port = 4842
    _port_lock = threading.Lock()

    @classmethod
    def _allocate_port(cls) -> int:
        with cls._port_lock:
            port = cls._next_port
            cls._next_port += 1
            return port

    def _default_deployment_config(self) -> DeploymentConfig:
        """Build a deployment config from scratch using the controller's tags."""
        dep = DeploymentConfig()
        port = self._allocate_port()
        dep.server_url = (
            f"opc.tcp://localhost:{port}/azeoapc/{_slug(self.cfg.name)}/")
        for cv in self.cfg.cvs:
            vd = VariableDeployment(variable_tag=cv.tag, var_type=VarType.INPUT)
            vd.io_tags = generate_io_tags(cv.tag, VarType.INPUT)
            vd.validation = ValidationLimits(
                validity_lo=cv.limits.validity_lo,
                validity_hi=cv.limits.validity_hi,
                engineer_lo=cv.limits.engineering_lo,
                engineer_hi=cv.limits.engineering_hi,
                operator_lo=cv.limits.operating_lo,
                operator_hi=cv.limits.operating_hi,
            )
            dep.variables.append(vd)
        for mv in self.cfg.mvs:
            vd = VariableDeployment(variable_tag=mv.tag, var_type=VarType.OUTPUT)
            vd.io_tags = generate_io_tags(mv.tag, VarType.OUTPUT)
            dep.variables.append(vd)
        for dv in self.cfg.dvs:
            vd = VariableDeployment(
                variable_tag=dv.tag, var_type=VarType.DISTURBANCE)
            vd.io_tags = generate_io_tags(dv.tag, VarType.DISTURBANCE)
            dep.variables.append(vd)
        return dep

    # ------------------------------------------------------------------
    def _handle_cycle_result(self, result: CycleResult) -> None:
        cycle = result.cycle
        ts_ms = int(time.time() * 1000)
        # Cycle log
        record = build_cycle_record(
            cycle=cycle,
            controller=self.cfg.name,
            cycle_result=result,
            engine=self.engine,
        )
        try:
            self.log_writer.write_cycle(record)
        except Exception as e:
            _LOG.warning("log_writer.write_cycle failed: %s", e)

        # Historian (local SQLite)
        if self.historian is not None:
            try:
                self.historian.log_cycle(
                    timestamp_ms=ts_ms,
                    cycle=cycle,
                    engine=self.engine,
                    cycle_result=result,
                )
            except Exception as e:
                _LOG.warning("historian.log_cycle failed: %s", e)

        # Optional remote historian forwarder
        if self.forwarder is not None:
            try:
                payload = record.to_dict()
                payload["timestamp_ms"] = ts_ms
                self.forwarder.enqueue(payload)
            except Exception as e:
                _LOG.warning("forwarder.enqueue failed: %s", e)

        # Update snapshot
        with self._lock:
            self._snapshot.cycle = cycle
            self._snapshot.last_cycle_ms = result.duration_ms
            self._snapshot.total_cycles += 1
            n = self._snapshot.total_cycles
            # Exponential moving average for stability
            self._cycle_ms_ema = (
                0.95 * self._cycle_ms_ema + 0.05 * result.duration_ms
                if n > 1 else result.duration_ms)
            self._snapshot.avg_cycle_ms = self._cycle_ms_ema
            self._snapshot.bad_variables = list(result.bad_variables)
            if not result.engine_ok:
                self._snapshot.last_error = result.engine_error

    # ------------------------------------------------------------------
    def _do_reload(self) -> None:
        """Re-read tunable fields from the .apcproj into the live engine."""
        try:
            new_cfg = load_config(self.project_path)
        except Exception as e:
            self.log_writer.write_event(
                "error", f"reload failed: {e}")
            return

        # Copy tunable CV fields
        old_cv = {cv.tag: cv for cv in self.cfg.cvs}
        new_cv = {cv.tag: cv for cv in new_cfg.cvs}
        for tag, new in new_cv.items():
            old = old_cv.get(tag)
            if old is None:
                continue
            old.setpoint = new.setpoint
            old.weight = new.weight
            old.concern_lo = new.concern_lo
            old.concern_hi = new.concern_hi
            old.limits.operating_lo = new.limits.operating_lo
            old.limits.operating_hi = new.limits.operating_hi
            old.opt_type = new.opt_type

        # Copy tunable MV fields
        old_mv = {mv.tag: mv for mv in self.cfg.mvs}
        new_mv = {mv.tag: mv for mv in new_cfg.mvs}
        for tag, new in new_mv.items():
            old = old_mv.get(tag)
            if old is None:
                continue
            old.move_suppress = new.move_suppress
            old.cost = new.cost
            old.cost_rank = new.cost_rank
            old.limits.operating_lo = new.limits.operating_lo
            old.limits.operating_hi = new.limits.operating_hi
            old.opt_type = new.opt_type
            old.rate_limit = new.rate_limit

        # Push new tuning into the C++ MPC controller
        if hasattr(self.engine, "apply_opt_type"):
            try:
                self.engine.apply_opt_type()
            except Exception as e:
                self.log_writer.write_event(
                    "warn", f"apply_opt_type after reload: {e}")

        self.log_writer.write_event(
            "info", "tuning reloaded from .apcproj")

    # ------------------------------------------------------------------
    def _teardown(self) -> None:
        if self.cycle_engine is not None:
            try:
                self.cycle_engine.disconnect()
            except Exception:
                pass
        if self.forwarder is not None:
            try:
                self.forwarder.stop()
            except Exception:
                pass
        if self.embedded_server is not None:
            try:
                self.embedded_server.stop()
            except Exception:
                pass
        if self.log_writer is not None:
            try:
                self.log_writer.write_event("info", "Runner stopped")
                self.log_writer.close()
            except Exception:
                pass
        if self.historian is not None:
            try:
                self.historian.close()
            except Exception:
                pass
        with self._lock:
            if self._snapshot.status not in (
                    RunnerStatus.ERROR.value,):
                self._snapshot.status = RunnerStatus.STOPPED.value

    # ------------------------------------------------------------------
    def _set_status(self, s: RunnerStatus) -> None:
        with self._lock:
            self._snapshot.status = s.value


# ---------------------------------------------------------------------------
def _slug(s: str) -> str:
    """Conservative filesystem-friendly slug from a controller name."""
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in s)
    return out.lower().rstrip("._") or "controller"
