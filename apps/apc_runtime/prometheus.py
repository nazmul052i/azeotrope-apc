"""Prometheus text-format metrics exporter.

We deliberately hand-roll the format instead of pulling in the
prometheus_client dependency: the text format is dead simple, the
runtime collects only a handful of gauges, and we don't want a heavy
dep for what amounts to a few HELP/TYPE/value lines.

Format spec: https://prometheus.io/docs/instrumenting/exposition_formats/

Metrics emitted (per controller, labelled by name):

  apc_cycle_total{controller="..."}                  -- monotonic counter
  apc_cycle_duration_ms{controller="..."}            -- gauge, last cycle
  apc_cycle_duration_ms_avg{controller="..."}        -- gauge, EMA
  apc_runner_status{controller="...",state="..."}    -- 1 if in state else 0
  apc_engine_ok{controller="..."}                    -- 0/1 from latest cycle
  apc_reads_failed_total{controller="..."}           -- monotonic counter
  apc_writes_failed_total{controller="..."}          -- monotonic counter
  apc_cv_value{controller="...",cv="..."}            -- last measured value
  apc_cv_setpoint{controller="...",cv="..."}         -- last setpoint
  apc_cv_error{controller="...",cv="..."}            -- last error
  apc_mv_value{controller="...",mv="..."}            -- last MV value
  apc_mv_at_lo{controller="...",mv="..."}            -- 1 if pinned to lo
  apc_mv_at_hi{controller="...",mv="..."}            -- 1 if pinned to hi
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

from .multi_runner import MultiRunner


_STATES = ("IDLE", "STARTING", "RUNNING", "PAUSED", "STOPPING",
           "STOPPED", "ERROR")


def build_metrics_text(multi: MultiRunner) -> str:
    """Render the current state of all runners as Prometheus text format."""
    lines: List[str] = []

    def emit_help_type(name: str, help_text: str, kind: str = "gauge"):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")

    def emit(name: str, labels: List[Tuple[str, str]], value: float):
        if labels:
            label_str = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
            lines.append(f"{name}{{{label_str}}} {value}")
        else:
            lines.append(f"{name} {value}")

    snapshots = multi.snapshot_all()

    # ── Cycle counter (monotonic) ──
    emit_help_type("apc_cycle_total",
                    "Total cycles run since this Runner started", "counter")
    for key, snap in snapshots.items():
        emit("apc_cycle_total", [("controller", key)], snap.total_cycles)

    # ── Cycle duration ──
    emit_help_type("apc_cycle_duration_ms",
                    "Duration of the most recent cycle in milliseconds")
    for key, snap in snapshots.items():
        emit("apc_cycle_duration_ms", [("controller", key)], snap.last_cycle_ms)

    emit_help_type("apc_cycle_duration_ms_avg",
                    "EMA of cycle duration in milliseconds")
    for key, snap in snapshots.items():
        emit("apc_cycle_duration_ms_avg", [("controller", key)],
             snap.avg_cycle_ms)

    # ── Status (one-hot) ──
    emit_help_type("apc_runner_status",
                    "Runner state -- 1 if in this state, 0 otherwise")
    for key, snap in snapshots.items():
        for state in _STATES:
            emit("apc_runner_status",
                 [("controller", key), ("state", state)],
                 1 if snap.status == state else 0)

    # ── Engine OK + read/write failures (from the latest cycle record) ──
    emit_help_type("apc_engine_ok",
                    "Whether engine.step() succeeded on the most recent cycle")
    emit_help_type("apc_reads_failed_last",
                    "Number of failed reads on the most recent cycle")
    emit_help_type("apc_writes_failed_last",
                    "Number of failed writes on the most recent cycle")

    for key, snap in snapshots.items():
        runner = multi.get(key)
        if runner is None or runner.log_writer is None:
            continue
        latest = runner.log_writer.read_latest()
        if not latest:
            continue
        emit("apc_engine_ok", [("controller", key)],
             1 if latest.get("engine_ok", True) else 0)
        emit("apc_reads_failed_last", [("controller", key)],
             int(latest.get("n_reads_failed", 0)))
        emit("apc_writes_failed_last", [("controller", key)],
             int(latest.get("n_writes_failed", 0)))

    # ── Per-CV metrics ──
    emit_help_type("apc_cv_value",
                    "Last measured value of a controlled variable")
    emit_help_type("apc_cv_setpoint", "Setpoint of a controlled variable")
    emit_help_type("apc_cv_error", "CV error (measured - setpoint)")
    for key, snap in snapshots.items():
        runner = multi.get(key)
        if runner is None or runner.log_writer is None:
            continue
        latest = runner.log_writer.read_latest()
        if not latest:
            continue
        for cv in latest.get("cv", []):
            labels = [("controller", key), ("cv", cv["tag"])]
            emit("apc_cv_value", labels, float(cv["value"]))
            emit("apc_cv_setpoint", labels, float(cv["setpoint"]))
            emit("apc_cv_error", labels, float(cv["error"]))

    # ── Per-MV metrics ──
    emit_help_type("apc_mv_value", "Last value of a manipulated variable")
    emit_help_type("apc_mv_at_lo",
                    "1 if the MV is pinned at its operating low limit")
    emit_help_type("apc_mv_at_hi",
                    "1 if the MV is pinned at its operating high limit")
    for key, snap in snapshots.items():
        runner = multi.get(key)
        if runner is None or runner.log_writer is None:
            continue
        latest = runner.log_writer.read_latest()
        if not latest:
            continue
        for mv in latest.get("mv", []):
            labels = [("controller", key), ("mv", mv["tag"])]
            emit("apc_mv_value", labels, float(mv["value"]))
            emit("apc_mv_at_lo", labels, 1 if mv.get("at_lo") else 0)
            emit("apc_mv_at_hi", labels, 1 if mv.get("at_hi") else 0)

    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    """Escape a label value per the Prometheus exposition format."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
