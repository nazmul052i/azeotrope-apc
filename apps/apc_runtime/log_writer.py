"""Cycle log writer -- per-cycle JSON-lines + a latest.json snapshot.

Each Runner owns one CycleLogWriter that emits a single JSON object
per cycle to a rotating ``cycles.jsonl`` file plus an atomically-
updated ``latest.json`` snapshot. The latter is what the REST surface
serves on ``GET /status``.

File layout:

    runs/
      <controller-name>/
        cycles.jsonl       <- append-only, one JSON object per line
        latest.json        <- latest snapshot (atomic write)
        events.log         <- human-readable info/warn/error log

JSON record fields per cycle:

    {
      "ts": "2026-04-11T14:32:01.234",
      "cycle": 142,
      "controller": "fired_heater",
      "duration_ms": 18.3,
      "engine_ok": true,
      "engine_error": "",
      "n_reads_ok": 7,
      "n_reads_failed": 0,
      "n_writes_ok": 3,
      "n_writes_failed": 0,
      "bad_variables": [],
      "cv": [{"tag": "TI-201.PV", "value": 752.4, "setpoint": 750.0,
              "error": 2.4, "lo_limit": 705, "hi_limit": 795}, ...],
      "mv": [{"tag": "FIC-101.SP", "value": 102.5, "ss_target": 102.5,
              "du": 0.5, "lo_limit": 81, "hi_limit": 119,
              "at_lo": false, "at_hi": false}, ...],
      "dv": [{"tag": "TI-101.PV", "value": 540.2}, ...],
      "solver": {"layer1_ms": 4.2, "layer2_ms": 1.1, "ok": true}
    }

The writer is thread-safe via an internal lock so the multi-runner
can write to one shared event log if it wants to.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class CycleRecord:
    """One cycle's snapshot. Becomes one line in cycles.jsonl."""
    ts: str
    cycle: int
    controller: str
    duration_ms: float
    engine_ok: bool
    engine_error: str = ""
    n_reads_ok: int = 0
    n_reads_failed: int = 0
    n_writes_ok: int = 0
    n_writes_failed: int = 0
    bad_variables: List[str] = field(default_factory=list)
    cv: List[Dict[str, Any]] = field(default_factory=list)
    mv: List[Dict[str, Any]] = field(default_factory=list)
    dv: List[Dict[str, Any]] = field(default_factory=list)
    solver: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CycleLogWriter:
    """Append-only cycle log + atomic latest.json snapshot.

    Designed to survive process kills mid-write: ``cycles.jsonl`` is
    line-buffered and flushed after each record so an interrupted run
    leaves a consistent file. ``latest.json`` is written to a temp file
    and renamed atomically.
    """

    def __init__(self, run_dir: str, controller_name: str):
        self.run_dir = os.path.abspath(run_dir)
        self.controller_name = controller_name
        os.makedirs(self.run_dir, exist_ok=True)
        self.jsonl_path = os.path.join(self.run_dir, "cycles.jsonl")
        self.latest_path = os.path.join(self.run_dir, "latest.json")
        self.events_path = os.path.join(self.run_dir, "events.log")
        self._lock = threading.Lock()
        self._jsonl_fh = open(self.jsonl_path, "a", encoding="utf-8")
        self._events_fh = open(self.events_path, "a", encoding="utf-8")

    # ------------------------------------------------------------------
    def write_cycle(self, record: CycleRecord) -> None:
        line = json.dumps(record.to_dict(), separators=(",", ":"))
        with self._lock:
            self._jsonl_fh.write(line + "\n")
            self._jsonl_fh.flush()
            self._write_latest_atomic(record.to_dict())

    def _write_latest_atomic(self, payload: Dict[str, Any]) -> None:
        tmp = self.latest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, self.latest_path)

    def write_event(self, level: str, message: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        line = f"{ts} [{level.upper():5s}] {message}\n"
        with self._lock:
            self._events_fh.write(line)
            self._events_fh.flush()

    def read_latest(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.latest_path):
            return None
        try:
            with open(self.latest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def close(self) -> None:
        with self._lock:
            try:
                self._jsonl_fh.close()
            except Exception:
                pass
            try:
                self._events_fh.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
def build_cycle_record(
    *,
    cycle: int,
    controller: str,
    cycle_result,
    engine,
) -> CycleRecord:
    """Snapshot the engine + cycle result into a CycleRecord.

    Pulls live values directly off the engine's CV/MV/DV objects so we
    capture exactly what the controller acted on this cycle.
    """
    cfg = engine.cfg
    cv_payload = []
    for cv in cfg.cvs:
        lo = float(cv.limits.operating_lo)
        hi = float(cv.limits.operating_hi)
        cv_payload.append({
            "tag": cv.tag,
            "value": float(cv.value),
            "setpoint": float(cv.setpoint),
            "error": float(cv.value - cv.setpoint),
            "lo_limit": lo if lo > -1e19 else None,
            "hi_limit": hi if hi < 1e19 else None,
        })

    mv_payload = []
    for i, mv in enumerate(cfg.mvs):
        lo = float(mv.limits.operating_lo)
        hi = float(mv.limits.operating_hi)
        du = float(engine.du[i]) if hasattr(engine, "du") and len(engine.du) > i else 0.0
        # Force native Python bool (numpy bools are not json-serializable
        # by the stdlib encoder).
        at_lo = bool((lo > -1e19) and (float(mv.value) <= lo + 1e-6))
        at_hi = bool((hi < 1e19) and (float(mv.value) >= hi - 1e-6))
        mv_payload.append({
            "tag": mv.tag,
            "value": float(mv.value),
            "du": du,
            "lo_limit": lo if lo > -1e19 else None,
            "hi_limit": hi if hi < 1e19 else None,
            "at_lo": at_lo,
            "at_hi": at_hi,
        })

    dv_payload = [{"tag": dv.tag, "value": float(dv.value)} for dv in cfg.dvs]

    solver = {
        "layer1_ms": float(getattr(engine, "last_l1_ms", 0.0)),
        "layer2_ms": float(getattr(engine, "last_l2_ms", 0.0)),
        "total_ms":  float(getattr(engine, "last_total_ms", 0.0)),
        # Coerce to native Python bool (numpy bools break json.dumps)
        "ok": bool(bool(getattr(engine, "last_ok", True))),
    }

    return CycleRecord(
        ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        cycle=cycle,
        controller=controller,
        duration_ms=float(cycle_result.duration_ms),
        engine_ok=bool(cycle_result.engine_ok),
        engine_error=str(cycle_result.engine_error),
        n_reads_ok=int(cycle_result.n_reads_ok),
        n_reads_failed=int(cycle_result.n_reads_failed),
        n_writes_ok=int(cycle_result.n_writes_ok),
        n_writes_failed=int(cycle_result.n_writes_failed),
        bad_variables=list(cycle_result.bad_variables),
        cv=cv_payload,
        mv=mv_payload,
        dv=dv_payload,
        solver=solver,
    )
