"""Centralised SQLite historian store.

Schema is the same shape as ``apc_runtime.historian`` (which mirrors
``core/include/azeoapc/storage.h``) but every table carries an extra
``controller`` column so one database can hold many controllers.

Tables (additions in **bold**):

  controllers           -- one row per controller (name, first_seen, last_seen)
  cv_timeseries         -- + **controller**, all the same columns as runtime
  mv_timeseries         -- + **controller**
  dv_timeseries         -- + **controller**
  controller_state      -- + **controller**
  solver_log            -- + **controller**

Indices on ``(controller, cv_name, cycle)`` etc. so per-tag queries are
fast even when the table holds millions of rows.

The store also handles retention: ``purge_older_than(ts_ms)`` deletes
records below a cutoff timestamp, and ``compact()`` runs ``VACUUM``.
A background thread can call these on a schedule.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS controllers (
        controller   TEXT PRIMARY KEY,
        first_seen   INTEGER NOT NULL,
        last_seen    INTEGER NOT NULL,
        n_cv         INTEGER,
        n_mv         INTEGER,
        n_dv         INTEGER,
        config_hash  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS cv_timeseries (
        controller   TEXT    NOT NULL,
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
        error        REAL
    )""",
    """CREATE TABLE IF NOT EXISTS mv_timeseries (
        controller   TEXT    NOT NULL,
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
        at_hi_limit  INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS dv_timeseries (
        controller   TEXT    NOT NULL,
        timestamp_ms INTEGER NOT NULL,
        cycle        INTEGER NOT NULL,
        dv_index     INTEGER NOT NULL,
        dv_name      TEXT    NOT NULL,
        value        REAL
    )""",
    """CREATE TABLE IF NOT EXISTS controller_state (
        controller       TEXT    NOT NULL,
        timestamp_ms     INTEGER NOT NULL,
        cycle            INTEGER NOT NULL,
        mode             TEXT,
        total_solve_ms   REAL,
        diagnostics_json TEXT,
        PRIMARY KEY (controller, timestamp_ms)
    )""",
    """CREATE TABLE IF NOT EXISTS solver_log (
        controller          TEXT    NOT NULL,
        timestamp_ms        INTEGER NOT NULL,
        cycle               INTEGER NOT NULL,
        layer               INTEGER NOT NULL,
        status              TEXT,
        objective           REAL,
        solve_time_ms       REAL,
        iterations          INTEGER
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cv_ctrl_name_cycle ON cv_timeseries(controller, cv_name, cycle)",
    "CREATE INDEX IF NOT EXISTS idx_mv_ctrl_name_cycle ON mv_timeseries(controller, mv_name, cycle)",
    "CREATE INDEX IF NOT EXISTS idx_dv_ctrl_name_cycle ON dv_timeseries(controller, dv_name, cycle)",
    "CREATE INDEX IF NOT EXISTS idx_state_ctrl_cycle ON controller_state(controller, cycle)",
    "CREATE INDEX IF NOT EXISTS idx_solver_ctrl_layer_cycle ON solver_log(controller, layer, cycle)",
]


# ---------------------------------------------------------------------------
@dataclass
class IngestRecord:
    """One cycle's worth of data, posted by apc_runtime.

    The shape mirrors what ``apc_runtime.log_writer.build_cycle_record``
    produces; we just add the controller name as a top-level field so
    one historian can serve many controllers.
    """
    controller: str
    timestamp_ms: int
    cycle: int
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

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "IngestRecord":
        return cls(
            controller=d["controller"],
            timestamp_ms=int(d.get("timestamp_ms", int(time.time() * 1000))),
            cycle=int(d["cycle"]),
            duration_ms=float(d.get("duration_ms", 0.0)),
            engine_ok=bool(d.get("engine_ok", True)),
            engine_error=str(d.get("engine_error", "")),
            n_reads_ok=int(d.get("n_reads_ok", 0)),
            n_reads_failed=int(d.get("n_reads_failed", 0)),
            n_writes_ok=int(d.get("n_writes_ok", 0)),
            n_writes_failed=int(d.get("n_writes_failed", 0)),
            bad_variables=list(d.get("bad_variables", [])),
            cv=list(d.get("cv", [])),
            mv=list(d.get("mv", [])),
            dv=list(d.get("dv", [])),
            solver=dict(d.get("solver", {})),
        )


# ---------------------------------------------------------------------------
class HistorianStore:
    """Thread-safe shared SQLite store for many controllers."""

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            for stmt in _SCHEMA:
                cur.execute(stmt)
            self._conn.commit()

    # ==================================================================
    # Ingestion
    # ==================================================================
    def ingest(self, record: IngestRecord) -> None:
        """Append one cycle's rows for a single controller."""
        with self._lock:
            cur = self._conn.cursor()
            try:
                # Upsert into controllers
                cur.execute(
                    """INSERT INTO controllers(controller, first_seen, last_seen,
                                                n_cv, n_mv, n_dv)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(controller) DO UPDATE
                       SET last_seen = excluded.last_seen,
                           n_cv      = excluded.n_cv,
                           n_mv      = excluded.n_mv,
                           n_dv      = excluded.n_dv""",
                    (record.controller, record.timestamp_ms, record.timestamp_ms,
                     len(record.cv), len(record.mv), len(record.dv)),
                )

                # CV rows
                for i, cv in enumerate(record.cv):
                    cur.execute(
                        "INSERT INTO cv_timeseries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            record.controller, record.timestamp_ms, record.cycle,
                            i, cv["tag"],
                            _f(cv.get("value")),
                            _f(cv.get("setpoint")),
                            _f(cv.get("setpoint")),       # ss_target placeholder
                            _f(cv.get("value")),          # predicted placeholder
                            _f(cv.get("lo_limit")),
                            _f(cv.get("hi_limit")),
                            _f(cv.get("error")),
                        ),
                    )

                # MV rows
                for i, mv in enumerate(record.mv):
                    cur.execute(
                        "INSERT INTO mv_timeseries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            record.controller, record.timestamp_ms, record.cycle,
                            i, mv["tag"],
                            _f(mv.get("value")),
                            _f(mv.get("value")),          # ss_target placeholder
                            _f(mv.get("du")),
                            _f(mv.get("lo_limit")),
                            _f(mv.get("hi_limit")),
                            None,                         # rate_limit not in payload
                            int(bool(mv.get("at_lo"))),
                            int(bool(mv.get("at_hi"))),
                        ),
                    )

                # DV rows
                for i, dv in enumerate(record.dv):
                    cur.execute(
                        "INSERT INTO dv_timeseries VALUES (?,?,?,?,?,?)",
                        (
                            record.controller, record.timestamp_ms, record.cycle,
                            i, dv["tag"], _f(dv.get("value")),
                        ),
                    )

                # Solver log
                solver = record.solver or {}
                for layer, key in [(1, "layer1_ms"), (2, "layer2_ms")]:
                    cur.execute(
                        "INSERT INTO solver_log VALUES (?,?,?,?,?,?,?,?)",
                        (
                            record.controller, record.timestamp_ms, record.cycle,
                            layer,
                            "OK" if record.engine_ok else "ERROR",
                            None,
                            _f(solver.get(key, 0.0)),
                            None,
                        ),
                    )

                # Controller state (one row per cycle)
                diag = {
                    "n_reads_ok": record.n_reads_ok,
                    "n_reads_failed": record.n_reads_failed,
                    "n_writes_ok": record.n_writes_ok,
                    "n_writes_failed": record.n_writes_failed,
                    "bad_variables": record.bad_variables,
                    "engine_error": record.engine_error,
                }
                cur.execute(
                    "INSERT OR REPLACE INTO controller_state "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        record.controller, record.timestamp_ms, record.cycle,
                        "AUTO" if record.engine_ok else "ERROR",
                        record.duration_ms,
                        json.dumps(diag),
                    ),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ==================================================================
    # Queries
    # ==================================================================
    def list_controllers(self) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT controller, first_seen, last_seen, n_cv, n_mv, n_dv "
                "FROM controllers ORDER BY last_seen DESC"
            )
            rows = cur.fetchall()
        return [
            {
                "controller": r[0],
                "first_seen_ms": r[1],
                "last_seen_ms": r[2],
                "n_cv": r[3], "n_mv": r[4], "n_dv": r[5],
            }
            for r in rows
        ]

    def query_cv(
        self, controller: str, cv_name: str, *,
        field_name: str = "measured", limit: int = 1000,
        since_ms: Optional[int] = None,
    ) -> List[Tuple[int, float]]:
        allowed = {"measured", "setpoint", "ss_target", "predicted",
                    "lo_limit", "hi_limit", "error"}
        if field_name not in allowed:
            raise ValueError(f"unknown CV field: {field_name}")
        with self._lock:
            cur = self._conn.cursor()
            if since_ms is not None:
                cur.execute(
                    f"SELECT timestamp_ms, {field_name} FROM cv_timeseries "
                    f"WHERE controller = ? AND cv_name = ? AND timestamp_ms >= ? "
                    f"ORDER BY timestamp_ms ASC LIMIT ?",
                    (controller, cv_name, since_ms, limit),
                )
            else:
                cur.execute(
                    f"SELECT timestamp_ms, {field_name} FROM cv_timeseries "
                    f"WHERE controller = ? AND cv_name = ? "
                    f"ORDER BY timestamp_ms DESC LIMIT ?",
                    (controller, cv_name, limit),
                )
            rows = cur.fetchall()
        return [(int(ts), float(v) if v is not None else 0.0) for ts, v in rows]

    def query_mv(
        self, controller: str, mv_name: str, *,
        field_name: str = "value", limit: int = 1000,
        since_ms: Optional[int] = None,
    ) -> List[Tuple[int, float]]:
        allowed = {"value", "ss_target", "du", "lo_limit", "hi_limit",
                    "rate_limit"}
        if field_name not in allowed:
            raise ValueError(f"unknown MV field: {field_name}")
        with self._lock:
            cur = self._conn.cursor()
            if since_ms is not None:
                cur.execute(
                    f"SELECT timestamp_ms, {field_name} FROM mv_timeseries "
                    f"WHERE controller = ? AND mv_name = ? AND timestamp_ms >= ? "
                    f"ORDER BY timestamp_ms ASC LIMIT ?",
                    (controller, mv_name, since_ms, limit),
                )
            else:
                cur.execute(
                    f"SELECT timestamp_ms, {field_name} FROM mv_timeseries "
                    f"WHERE controller = ? AND mv_name = ? "
                    f"ORDER BY timestamp_ms DESC LIMIT ?",
                    (controller, mv_name, limit),
                )
            rows = cur.fetchall()
        return [(int(ts), float(v) if v is not None else 0.0) for ts, v in rows]

    def list_cv_tags(self, controller: str) -> List[str]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT DISTINCT cv_name FROM cv_timeseries "
                "WHERE controller = ? ORDER BY cv_index",
                (controller,),
            )
            return [r[0] for r in cur.fetchall()]

    def list_mv_tags(self, controller: str) -> List[str]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT DISTINCT mv_name FROM mv_timeseries "
                "WHERE controller = ? ORDER BY mv_index",
                (controller,),
            )
            return [r[0] for r in cur.fetchall()]

    def latest_cycle(self, controller: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT timestamp_ms, cycle, mode, total_solve_ms, "
                "diagnostics_json FROM controller_state "
                "WHERE controller = ? ORDER BY cycle DESC LIMIT 1",
                (controller,),
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
                "timestamp_ms": ts, "cycle": cycle, "mode": mode,
                "total_solve_ms": total_ms, "diagnostics": diag,
            }

    def cycle_count(self, controller: Optional[str] = None) -> int:
        with self._lock:
            cur = self._conn.cursor()
            if controller is None:
                cur.execute("SELECT COUNT(*) FROM controller_state")
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM controller_state WHERE controller = ?",
                    (controller,),
                )
            return int(cur.fetchone()[0])

    # ==================================================================
    # Retention + maintenance
    # ==================================================================
    def purge_older_than(self, timestamp_ms: int) -> Dict[str, int]:
        """Delete records below a cutoff timestamp. Returns row counts."""
        deleted: Dict[str, int] = {}
        with self._lock:
            cur = self._conn.cursor()
            for table in ("cv_timeseries", "mv_timeseries", "dv_timeseries",
                          "solver_log", "controller_state"):
                cur.execute(
                    f"DELETE FROM {table} WHERE timestamp_ms < ?",
                    (timestamp_ms,),
                )
                deleted[table] = cur.rowcount
            self._conn.commit()
        return deleted

    def compact(self) -> None:
        """Reclaim space (VACUUM). Slow on large DBs."""
        with self._lock:
            self._conn.execute("VACUUM")

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
def _f(v: Any) -> Optional[float]:
    """Coerce to float or None for SQLite."""
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None
