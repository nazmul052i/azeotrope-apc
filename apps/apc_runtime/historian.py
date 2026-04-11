"""SQLite historian -- per-controller cycle store.

Schema mirrors ``core/include/azeoapc/storage.h`` so a future C++
historian could read the same database. We deliberately keep the
schema separated by table type (cv_timeseries, mv_timeseries, etc.)
rather than one wide row, because real APC engineers query "show me
TI-201 over the last 4 hours" much more often than "show me cycle 1284".

Tables:

  controller_info       -- one row per controller (name, created_at)
  cv_timeseries         -- per-CV per-cycle: measured/sp/error/limits
  mv_timeseries         -- per-MV per-cycle: value/du/limits/at-limit flags
  dv_timeseries         -- per-DV per-cycle: value
  solver_log            -- per-layer per-cycle: status/objective/solve_ms
  controller_state      -- per-cycle: mode, total_ms, diagnostics_json

All tables key on (timestamp_ms, cycle). Indices on (cycle) and on
(name, cycle) for fast tag lookups.

Use as:

    h = Historian("runs/fired_heater/history.db")
    h.init_schema("fired_heater", cv_names, mv_names, dv_names)
    h.log_cycle(timestamp_ms, cycle, engine, cycle_result)
    ...
    h.close()

Writes are wrapped in a single transaction per cycle (commit at the
end of log_cycle) so a process kill mid-write loses at most the last
in-flight cycle.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS controller_info (
        controller_name TEXT PRIMARY KEY,
        config_hash     TEXT,
        created_at      TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS cv_timeseries (
        timestamp_ms INTEGER NOT NULL,
        cycle        INTEGER NOT NULL,
        cv_index     INTEGER NOT NULL,
        cv_name      TEXT    NOT NULL,
        measured     REAL,
        setpoint     REAL,
        ss_target    REAL,
        predicted    REAL,
        lo_limit     REAL,
        hi_limit     REAL,
        disturbance  REAL,
        error        REAL,
        weight       REAL,
        enabled      INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS mv_timeseries (
        timestamp_ms INTEGER NOT NULL,
        cycle        INTEGER NOT NULL,
        mv_index     INTEGER NOT NULL,
        mv_name      TEXT    NOT NULL,
        value        REAL,
        ss_target    REAL,
        du           REAL,
        lo_limit     REAL,
        hi_limit     REAL,
        rate_limit   REAL,
        at_lo_limit  INTEGER,
        at_hi_limit  INTEGER,
        enabled      INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS dv_timeseries (
        timestamp_ms INTEGER NOT NULL,
        cycle        INTEGER NOT NULL,
        dv_index     INTEGER NOT NULL,
        dv_name      TEXT    NOT NULL,
        value        REAL
    )""",
    """CREATE TABLE IF NOT EXISTS solver_log (
        timestamp_ms        INTEGER NOT NULL,
        cycle               INTEGER NOT NULL,
        layer               INTEGER NOT NULL,
        status              TEXT,
        objective           REAL,
        solve_time_ms       REAL,
        iterations          INTEGER,
        relaxed_priorities  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS controller_state (
        timestamp_ms     INTEGER PRIMARY KEY,
        cycle            INTEGER NOT NULL,
        mode             TEXT,
        total_solve_ms   REAL,
        diagnostics_json TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cv_name_cycle ON cv_timeseries(cv_name, cycle)",
    "CREATE INDEX IF NOT EXISTS idx_mv_name_cycle ON mv_timeseries(mv_name, cycle)",
    "CREATE INDEX IF NOT EXISTS idx_dv_name_cycle ON dv_timeseries(dv_name, cycle)",
    "CREATE INDEX IF NOT EXISTS idx_solver_layer_cycle ON solver_log(layer, cycle)",
    "CREATE INDEX IF NOT EXISTS idx_state_cycle ON controller_state(cycle)",
]


class Historian:
    """Thread-safe SQLite cycle historian."""

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        # check_same_thread=False because the multi-runner may write
        # from worker threads. We serialize writes with our own lock.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.Lock()
        self._initialized = False
        self.controller_name = ""

    # ------------------------------------------------------------------
    def init_schema(
        self,
        controller_name: str,
        cv_names: List[str],
        mv_names: List[str],
        dv_names: List[str],
    ) -> None:
        with self._lock:
            cur = self._conn.cursor()
            for stmt in _SCHEMA:
                cur.execute(stmt)
            cur.execute(
                "INSERT OR IGNORE INTO controller_info "
                "(controller_name, config_hash, created_at) VALUES (?,?,?)",
                (controller_name, "",
                 time.strftime("%Y-%m-%dT%H:%M:%S")),
            )
            self._conn.commit()
        self.controller_name = controller_name
        self._initialized = True

    # ------------------------------------------------------------------
    def log_cycle(
        self,
        timestamp_ms: int,
        cycle: int,
        engine,
        cycle_result,
    ) -> None:
        """Append one cycle's worth of rows. Single transaction."""
        if not self._initialized:
            raise RuntimeError("Historian.init_schema() must be called first")

        cfg = engine.cfg

        with self._lock:
            cur = self._conn.cursor()
            try:
                # CV rows
                for i, cv in enumerate(cfg.cvs):
                    cur.execute(
                        "INSERT INTO cv_timeseries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            timestamp_ms, cycle, i, cv.tag,
                            float(cv.value),
                            float(cv.setpoint),
                            float(cv.setpoint),         # ss_target -- placeholder
                            float(cv.value),            # predicted -- placeholder
                            _bound(cv.limits.operating_lo),
                            _bound(cv.limits.operating_hi),
                            0.0,                        # disturbance
                            float(cv.value - cv.setpoint),
                            float(cv.weight),
                            1,                          # enabled
                        ),
                    )

                # MV rows
                for i, mv in enumerate(cfg.mvs):
                    du = (float(engine.du[i])
                          if hasattr(engine, "du") and len(engine.du) > i
                          else 0.0)
                    lo_lim = _bound(mv.limits.operating_lo)
                    hi_lim = _bound(mv.limits.operating_hi)
                    cur.execute(
                        "INSERT INTO mv_timeseries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            timestamp_ms, cycle, i, mv.tag,
                            float(mv.value),
                            float(mv.value),            # ss_target -- placeholder
                            du,
                            lo_lim, hi_lim,
                            float(mv.rate_limit),
                            int((lo_lim is not None) and (mv.value <= lo_lim + 1e-6)),
                            int((hi_lim is not None) and (mv.value >= hi_lim - 1e-6)),
                            1,
                        ),
                    )

                # DV rows
                for i, dv in enumerate(cfg.dvs):
                    cur.execute(
                        "INSERT INTO dv_timeseries VALUES (?,?,?,?,?)",
                        (timestamp_ms, cycle, i, dv.tag, float(dv.value)),
                    )

                # Solver layers (1 + 2; layer 3 only when RTO ran)
                cur.execute(
                    "INSERT INTO solver_log VALUES (?,?,?,?,?,?,?,?)",
                    (
                        timestamp_ms, cycle, 1,
                        "OK" if cycle_result.engine_ok else "ERROR",
                        0.0,
                        float(getattr(engine, "last_l1_ms", 0.0)),
                        0,
                        "[]",
                    ),
                )
                cur.execute(
                    "INSERT INTO solver_log VALUES (?,?,?,?,?,?,?,?)",
                    (
                        timestamp_ms, cycle, 2,
                        "OK" if cycle_result.engine_ok else "ERROR",
                        0.0,
                        float(getattr(engine, "last_l2_ms", 0.0)),
                        0,
                        "[]",
                    ),
                )

                # Overall controller state
                diag = {
                    "n_reads_ok": cycle_result.n_reads_ok,
                    "n_reads_failed": cycle_result.n_reads_failed,
                    "n_writes_ok": cycle_result.n_writes_ok,
                    "n_writes_failed": cycle_result.n_writes_failed,
                    "bad_variables": cycle_result.bad_variables,
                    "engine_error": cycle_result.engine_error,
                }
                cur.execute(
                    "INSERT OR REPLACE INTO controller_state "
                    "VALUES (?,?,?,?,?)",
                    (
                        timestamp_ms, cycle,
                        "AUTO" if cycle_result.engine_ok else "ERROR",
                        float(cycle_result.duration_ms),
                        json.dumps(diag),
                    ),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ------------------------------------------------------------------
    def query_cv(self, cv_name: str, field: str = "measured",
                  limit: int = 1000) -> List[tuple]:
        """Return [(timestamp_ms, value)] for one CV. Used by REST + tests."""
        allowed = {"measured", "setpoint", "ss_target", "predicted",
                    "lo_limit", "hi_limit", "error"}
        if field not in allowed:
            raise ValueError(f"unknown CV field: {field}")
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                f"SELECT timestamp_ms, {field} FROM cv_timeseries "
                f"WHERE cv_name = ? ORDER BY cycle DESC LIMIT ?",
                (cv_name, limit),
            )
            return cur.fetchall()

    def query_mv(self, mv_name: str, field: str = "value",
                  limit: int = 1000) -> List[tuple]:
        allowed = {"value", "ss_target", "du", "lo_limit", "hi_limit",
                    "rate_limit"}
        if field not in allowed:
            raise ValueError(f"unknown MV field: {field}")
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                f"SELECT timestamp_ms, {field} FROM mv_timeseries "
                f"WHERE mv_name = ? ORDER BY cycle DESC LIMIT ?",
                (mv_name, limit),
            )
            return cur.fetchall()

    def cycle_count(self) -> int:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM controller_state")
            (count,) = cur.fetchone()
            return int(count)

    def latest_cycle_state(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT timestamp_ms, cycle, mode, total_solve_ms, "
                "diagnostics_json FROM controller_state "
                "ORDER BY cycle DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                return None
            ts, cycle, mode, total_ms, diag_json = row
            try:
                diag = json.loads(diag_json) if diag_json else {}
            except json.JSONDecodeError:
                diag = {}
            return {
                "timestamp_ms": ts,
                "cycle": cycle,
                "mode": mode,
                "total_solve_ms": total_ms,
                "diagnostics": diag,
            }

    def database_size(self) -> int:
        try:
            return os.path.getsize(self.db_path)
        except OSError:
            return 0

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
def _bound(v: float) -> Optional[float]:
    """Convert sentinel infinities to None for SQLite NULL."""
    if v is None:
        return None
    if v <= -1e19 or v >= 1e19:
        return None
    return float(v)
