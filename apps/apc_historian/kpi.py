"""KPI calculator -- Aspen Watch role.

Computes a small set of process-control KPIs from a HistorianStore:

  * controller uptime (seconds since first cycle, fraction online)
  * cycles_per_minute (recent cycle count / wall time)
  * cv_on_control_pct  -- % cycles where |error| < tol*range, per CV
  * cv_at_limit_pct    -- % cycles touching the operating limits
  * mv_at_limit_pct    -- % cycles where MV pinned to lo or hi
  * solver_health      -- avg solve time, error rate, last error string

Each KPI is bounded to a recent window (default 1 hour). The Manager
calls this on demand and caches the result for the dashboard tile.

Math is straight SQL aggregations -- no numpy needed, so this module
runs even on a tiny historian box without scientific Python.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CvKpi:
    cv_name: str
    n_samples: int = 0
    on_control_pct: float = 0.0       # % cycles |err| < band
    at_lo_pct: float = 0.0
    at_hi_pct: float = 0.0
    avg_error: float = 0.0
    max_abs_error: float = 0.0


@dataclass
class MvKpi:
    mv_name: str
    n_samples: int = 0
    at_lo_pct: float = 0.0
    at_hi_pct: float = 0.0
    avg_value: float = 0.0
    avg_du: float = 0.0


@dataclass
class KpiSummary:
    controller: str
    window_ms: int
    n_cycles: int = 0
    cycles_per_minute: float = 0.0
    avg_solve_ms: float = 0.0
    error_pct: float = 0.0           # % cycles where engine_ok = False
    last_cycle_ms: int = 0
    last_error: str = ""
    cvs: List[CvKpi] = field(default_factory=list)
    mvs: List[MvKpi] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "controller": self.controller,
            "window_ms": self.window_ms,
            "n_cycles": self.n_cycles,
            "cycles_per_minute": round(self.cycles_per_minute, 2),
            "avg_solve_ms": round(self.avg_solve_ms, 3),
            "error_pct": round(self.error_pct, 2),
            "last_cycle_ms": self.last_cycle_ms,
            "last_error": self.last_error,
            "cvs": [{
                "cv": c.cv_name,
                "n": c.n_samples,
                "on_control_pct": round(c.on_control_pct, 1),
                "at_lo_pct": round(c.at_lo_pct, 1),
                "at_hi_pct": round(c.at_hi_pct, 1),
                "avg_error": round(c.avg_error, 4),
                "max_abs_error": round(c.max_abs_error, 4),
            } for c in self.cvs],
            "mvs": [{
                "mv": m.mv_name,
                "n": m.n_samples,
                "at_lo_pct": round(m.at_lo_pct, 1),
                "at_hi_pct": round(m.at_hi_pct, 1),
                "avg_value": round(m.avg_value, 4),
                "avg_du": round(m.avg_du, 4),
            } for m in self.mvs],
        }


# ---------------------------------------------------------------------------
def compute_kpis(
    store, controller: str, *, window_ms: int = 3_600_000,
    on_control_band_pct: float = 0.05,
) -> KpiSummary:
    """Aggregate KPIs for ``controller`` over the last ``window_ms`` ms.

    The store argument is a HistorianStore. We pull the few aggregates
    via direct SQL on the underlying connection -- no Python-side
    iteration over millions of rows.

    ``on_control_band_pct`` is what counts as "on control": |error| <
    band * (hi_limit - lo_limit). The Aspen Watch default is 5%.
    """
    summary = KpiSummary(controller=controller, window_ms=window_ms)

    # Locate the cutoff timestamp from the latest cycle
    latest = store.latest_cycle(controller)
    if latest is None:
        return summary
    summary.last_cycle_ms = latest["timestamp_ms"]
    cutoff = latest["timestamp_ms"] - window_ms
    diag = latest.get("diagnostics") or {}
    summary.last_error = str(diag.get("engine_error", ""))

    with store._lock:
        cur = store._conn.cursor()

        # ── Cycle count + solver stats ──
        cur.execute(
            """SELECT COUNT(*), AVG(total_solve_ms),
                      SUM(CASE WHEN mode = 'ERROR' THEN 1 ELSE 0 END),
                      MIN(timestamp_ms), MAX(timestamp_ms)
               FROM controller_state
               WHERE controller = ? AND timestamp_ms >= ?""",
            (controller, cutoff),
        )
        row = cur.fetchone()
        n_cycles, avg_ms, n_err, t_min, t_max = row
        summary.n_cycles = int(n_cycles or 0)
        summary.avg_solve_ms = float(avg_ms or 0.0)
        summary.error_pct = (
            100.0 * float(n_err or 0) / max(1, summary.n_cycles))
        if t_min and t_max and t_max > t_min:
            elapsed_min = (t_max - t_min) / 60_000.0
            summary.cycles_per_minute = (
                summary.n_cycles / elapsed_min if elapsed_min > 0 else 0.0)

        # ── Per-CV KPIs ──
        cur.execute(
            """SELECT DISTINCT cv_name FROM cv_timeseries
               WHERE controller = ? AND timestamp_ms >= ?""",
            (controller, cutoff),
        )
        cv_names = [r[0] for r in cur.fetchall()]
        for name in cv_names:
            cur.execute(
                """SELECT COUNT(*),
                          AVG(error),
                          MAX(ABS(error)),
                          AVG(CASE WHEN lo_limit IS NOT NULL
                                    AND measured <= lo_limit + 1e-6
                                   THEN 1.0 ELSE 0.0 END),
                          AVG(CASE WHEN hi_limit IS NOT NULL
                                    AND measured >= hi_limit - 1e-6
                                   THEN 1.0 ELSE 0.0 END),
                          AVG(CASE WHEN hi_limit IS NOT NULL
                                    AND lo_limit IS NOT NULL
                                    AND ABS(error) <
                                        ? * (hi_limit - lo_limit)
                                   THEN 1.0 ELSE 0.0 END)
                   FROM cv_timeseries
                   WHERE controller = ? AND cv_name = ?
                     AND timestamp_ms >= ?""",
                (on_control_band_pct, controller, name, cutoff),
            )
            n, avg_err, max_err, lo_p, hi_p, on_p = cur.fetchone()
            summary.cvs.append(CvKpi(
                cv_name=name,
                n_samples=int(n or 0),
                on_control_pct=100.0 * float(on_p or 0.0),
                at_lo_pct=100.0 * float(lo_p or 0.0),
                at_hi_pct=100.0 * float(hi_p or 0.0),
                avg_error=float(avg_err or 0.0),
                max_abs_error=float(max_err or 0.0),
            ))

        # ── Per-MV KPIs ──
        cur.execute(
            """SELECT DISTINCT mv_name FROM mv_timeseries
               WHERE controller = ? AND timestamp_ms >= ?""",
            (controller, cutoff),
        )
        mv_names = [r[0] for r in cur.fetchall()]
        for name in mv_names:
            cur.execute(
                """SELECT COUNT(*),
                          AVG(value), AVG(du),
                          AVG(CASE WHEN at_lo_limit > 0 THEN 1.0 ELSE 0.0 END),
                          AVG(CASE WHEN at_hi_limit > 0 THEN 1.0 ELSE 0.0 END)
                   FROM mv_timeseries
                   WHERE controller = ? AND mv_name = ?
                     AND timestamp_ms >= ?""",
                (controller, name, cutoff),
            )
            n, avg_v, avg_du, lo_p, hi_p = cur.fetchone()
            summary.mvs.append(MvKpi(
                mv_name=name,
                n_samples=int(n or 0),
                avg_value=float(avg_v or 0.0),
                avg_du=float(avg_du or 0.0),
                at_lo_pct=100.0 * float(lo_p or 0.0),
                at_hi_pct=100.0 * float(hi_p or 0.0),
            ))

    return summary
