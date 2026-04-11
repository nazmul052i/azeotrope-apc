"""REST control surface (FastAPI optional dep).

Endpoints:
  GET  /                  -- API root, lists controllers
  GET  /controllers       -- list of controller keys + summary
  GET  /controllers/{key}/status     -- RunnerSnapshot
  GET  /controllers/{key}/latest     -- last cycle record (from latest.json)
  GET  /controllers/{key}/cv/{name}  -- last N CV samples (from historian)
  GET  /controllers/{key}/mv/{name}  -- last N MV samples
  POST /controllers/{key}/pause
  POST /controllers/{key}/resume
  POST /controllers/{key}/reload     -- request tuning reload
  POST /controllers/{key}/stop
  POST /pause-all
  POST /resume-all
  POST /stop-all
  GET  /healthz                       -- liveness probe
  GET  /metrics                       -- Prometheus text-format metrics

The server is built lazily so importing this module does NOT require
fastapi to be installed -- you only need it if you actually want the
control surface. The CLI checks for fastapi at startup and skips REST
gracefully if missing.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .multi_runner import MultiRunner
from .prometheus import build_metrics_text


_LOG = logging.getLogger("apc_runtime.rest_server")


def build_app(multi: MultiRunner):
    """Construct the FastAPI app bound to a MultiRunner instance.

    Imported lazily so apc_runtime works without fastapi installed.
    """
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
    except ImportError as e:
        raise RuntimeError(
            "FastAPI is required for the REST surface. "
            "Install it: pip install 'fastapi[standard]' uvicorn"
        ) from e

    from azeoapc.theme import SILVER

    app = FastAPI(
        title="Azeotrope APC Runtime",
        version="0.1.0",
        description="Headless control surface for apc_runtime",
    )

    # ── Discovery ──────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def root():
        """HTML landing page so 'Open in Browser' from the launcher
        shows something useful instead of raw JSON. Lists every
        controller currently loaded with a status badge and the URLs
        the operator can hit, plus a live link to the JSON API."""
        rows = []
        for key, runner in multi.runners.items():
            snap = runner.snapshot()
            badge_color = {
                "RUNNING":  SILVER["accent_green"],
                "PAUSED":   SILVER["accent_orange"],
                "STOPPED":  SILVER["text_muted"],
                "STOPPING": SILVER["text_muted"],
                "ERROR":    SILVER["accent_red"],
                "STARTING": SILVER["accent_cyan"],
            }.get(snap.status, SILVER["bg_panel"])
            rows.append(f"""
            <tr>
              <td><strong>{key}</strong></td>
              <td>{snap.controller_name or "—"}</td>
              <td><span class="badge" style="background:{badge_color}">{snap.status}</span></td>
              <td>{snap.cycle}</td>
              <td>{snap.last_cycle_ms:.1f} ms</td>
              <td>
                <a href="/controllers/{key}/status">status</a> ·
                <a href="/controllers/{key}/latest">latest</a>
              </td>
            </tr>
            """)
        body = "".join(rows) or """
            <tr><td colspan="6" style="text-align:center;padding:20px;color:#707070">
            No controllers loaded.</td></tr>
        """
        return _runtime_index_html(body, multi=multi)

    @app.get("/api", include_in_schema=False)
    def api_root():
        return {
            "name": "Azeotrope APC Runtime",
            "version": "0.1.0",
            "controllers": multi.keys(),
        }

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "controllers": len(multi.runners),
                "any_running": multi.is_any_running()}

    @app.get("/controllers")
    def list_controllers():
        out = []
        for key, runner in multi.runners.items():
            snap = runner.snapshot()
            out.append({
                "key": key,
                "name": snap.controller_name,
                "status": snap.status,
                "cycle": snap.cycle,
                "n_cv": snap.n_cv,
                "n_mv": snap.n_mv,
                "n_dv": snap.n_dv,
                "last_cycle_ms": snap.last_cycle_ms,
                "avg_cycle_ms": snap.avg_cycle_ms,
                "last_error": snap.last_error,
            })
        return {"controllers": out}

    # ── Per-controller endpoints ───────────────────────────────────
    def _get(key: str):
        runner = multi.get(key)
        if runner is None:
            raise HTTPException(status_code=404, detail=f"unknown controller: {key}")
        return runner

    @app.get("/controllers/{key}/status")
    def status(key: str):
        runner = _get(key)
        snap = runner.snapshot()
        return {
            "key": key,
            "name": snap.controller_name,
            "project_path": snap.project_path,
            "status": snap.status,
            "cycle": snap.cycle,
            "total_cycles": snap.total_cycles,
            "last_cycle_ms": snap.last_cycle_ms,
            "avg_cycle_ms": snap.avg_cycle_ms,
            "started_at": snap.started_at,
            "n_cv": snap.n_cv,
            "n_mv": snap.n_mv,
            "n_dv": snap.n_dv,
            "bad_variables": snap.bad_variables,
            "last_error": snap.last_error,
        }

    @app.get("/controllers/{key}/latest")
    def latest(key: str):
        runner = _get(key)
        if runner.log_writer is None:
            raise HTTPException(status_code=503,
                                 detail="runner not started")
        payload = runner.log_writer.read_latest()
        if payload is None:
            raise HTTPException(status_code=404,
                                 detail="no cycle record yet")
        return payload

    @app.get("/controllers/{key}/cv/{cv_name}")
    def cv_history(key: str, cv_name: str, field: str = "measured",
                    limit: int = 100):
        runner = _get(key)
        if runner.historian is None:
            raise HTTPException(status_code=503,
                                 detail="historian disabled")
        try:
            rows = runner.historian.query_cv(cv_name, field, limit=limit)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"cv": cv_name, "field": field,
                "samples": [{"ts": ts, "value": v} for ts, v in rows]}

    @app.get("/controllers/{key}/mv/{mv_name}")
    def mv_history(key: str, mv_name: str, field: str = "value",
                    limit: int = 100):
        runner = _get(key)
        if runner.historian is None:
            raise HTTPException(status_code=503,
                                 detail="historian disabled")
        try:
            rows = runner.historian.query_mv(mv_name, field, limit=limit)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"mv": mv_name, "field": field,
                "samples": [{"ts": ts, "value": v} for ts, v in rows]}

    @app.post("/controllers/{key}/pause")
    def pause(key: str):
        runner = _get(key)
        runner.pause()
        return {"ok": True, "key": key, "status": runner.snapshot().status}

    @app.post("/controllers/{key}/resume")
    def resume(key: str):
        runner = _get(key)
        runner.resume()
        return {"ok": True, "key": key, "status": runner.snapshot().status}

    @app.post("/controllers/{key}/reload")
    def reload_(key: str):
        runner = _get(key)
        runner.reload()
        return {"ok": True, "key": key,
                "message": "tuning reload requested"}

    @app.post("/controllers/{key}/stop")
    def stop(key: str):
        runner = _get(key)
        runner.stop(join_timeout=5.0)
        return {"ok": True, "key": key, "status": runner.snapshot().status}

    # ── Operator actions (called from apc_manager) ────────────────
    @app.post("/controllers/{key}/cv/{cv_tag}/setpoint")
    def set_cv_setpoint(key: str, cv_tag: str, payload: Dict[str, Any]):
        runner = _get(key)
        sp = payload.get("setpoint")
        if sp is None:
            raise HTTPException(status_code=400, detail="missing setpoint")
        ok = runner.set_cv_setpoint(cv_tag, float(sp))
        if not ok:
            raise HTTPException(status_code=404, detail=f"unknown CV: {cv_tag}")
        return {"ok": True, "cv": cv_tag, "setpoint": float(sp)}

    @app.post("/controllers/{key}/cv/{cv_tag}/limits")
    def set_cv_limits(key: str, cv_tag: str, payload: Dict[str, Any]):
        runner = _get(key)
        lo = payload.get("lo")
        hi = payload.get("hi")
        if lo is None and hi is None:
            raise HTTPException(status_code=400,
                                 detail="payload must include lo and/or hi")
        ok = runner.set_cv_limits(cv_tag,
                                    lo=float(lo) if lo is not None else None,
                                    hi=float(hi) if hi is not None else None)
        if not ok:
            raise HTTPException(status_code=404, detail=f"unknown CV: {cv_tag}")
        return {"ok": True, "cv": cv_tag, "lo": lo, "hi": hi}

    @app.post("/controllers/{key}/mv/{mv_tag}/limits")
    def set_mv_limits(key: str, mv_tag: str, payload: Dict[str, Any]):
        runner = _get(key)
        lo = payload.get("lo")
        hi = payload.get("hi")
        if lo is None and hi is None:
            raise HTTPException(status_code=400,
                                 detail="payload must include lo and/or hi")
        ok = runner.set_mv_limits(mv_tag,
                                    lo=float(lo) if lo is not None else None,
                                    hi=float(hi) if hi is not None else None)
        if not ok:
            raise HTTPException(status_code=404, detail=f"unknown MV: {mv_tag}")
        return {"ok": True, "mv": mv_tag, "lo": lo, "hi": hi}

    @app.post("/controllers/{key}/mv/{mv_tag}/move-suppress")
    def set_mv_move_suppress(key: str, mv_tag: str, payload: Dict[str, Any]):
        runner = _get(key)
        v = payload.get("value")
        if v is None:
            raise HTTPException(status_code=400, detail="missing value")
        ok = runner.set_mv_move_suppress(mv_tag, float(v))
        if not ok:
            raise HTTPException(status_code=404, detail=f"unknown MV: {mv_tag}")
        return {"ok": True, "mv": mv_tag, "move_suppress": float(v)}

    # ── Bulk operations ────────────────────────────────────────────
    @app.post("/pause-all")
    def pause_all():
        multi.pause_all()
        return {"ok": True, "message": f"paused {len(multi.runners)} controllers"}

    @app.post("/resume-all")
    def resume_all():
        multi.resume_all()
        return {"ok": True, "message": f"resumed {len(multi.runners)} controllers"}

    @app.post("/stop-all")
    def stop_all():
        multi.stop_all(join_timeout=5.0)
        return {"ok": True, "message": f"stopped {len(multi.runners)} controllers"}

    # ── Prometheus metrics ─────────────────────────────────────────
    @app.get("/metrics")
    def metrics():
        return PlainTextResponse(build_metrics_text(multi),
                                  media_type="text/plain; version=0.0.4")

    return app


def _runtime_index_html(rows_html: str, *, multi) -> str:
    """Render the runtime landing page in DeltaV Live Silver chrome.

    Kept inline (no Jinja2 dependency) so apc_runtime stays lean -- the
    runtime is the headless production loop and shouldn't drag the
    full template engine in just for one info page.
    """
    from azeoapc.theme import SILVER
    n = len(multi.runners)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>APC Runtime</title>
<meta http-equiv="refresh" content="5">
<style>
  :root {{
    --bg: {SILVER['bg_primary']}; --panel: {SILVER['bg_secondary']};
    --header: {SILVER['bg_header']}; --border: {SILVER['border']};
    --text: {SILVER['text_primary']}; --text2: {SILVER['text_secondary']};
    --muted: {SILVER['text_muted']}; --blue: {SILVER['accent_blue']};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font-family: 'Segoe UI', sans-serif; font-size: 13px;
  }}
  .topbar {{
    display: flex; align-items: center; gap: 18px;
    padding: 12px 28px; background: var(--header);
    border-bottom: 1px solid var(--border);
  }}
  .logo {{ color: var(--blue); font-size: 18pt; font-weight: bold; }}
  .brand {{ font-weight: 700; letter-spacing: 1.5px; font-size: 13pt; }}
  .sep {{ color: var(--muted); }}
  .subtitle {{ color: var(--text2); }}
  main {{ padding: 20px 28px; max-width: 1300px; margin: 0 auto; }}
  h1 {{ font-size: 16pt; margin: 8px 0 18px; color: var(--text); }}
  table {{
    width: 100%; border-collapse: collapse;
    background: white; border: 1px solid var(--border);
    margin-bottom: 22px;
  }}
  th {{
    background: var(--header); color: var(--text2);
    padding: 8px 12px; text-align: left;
    font-size: 9pt; text-transform: uppercase; letter-spacing: 1px;
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 8px 12px; border-bottom: 1px solid var(--border);
  }}
  .badge {{
    display: inline-block; padding: 2px 10px; border-radius: 2px;
    color: white; font-weight: 700; letter-spacing: 1px;
    font-size: 9pt;
  }}
  .endpoint-list {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 10px; margin-top: 12px;
  }}
  .endpoint {{
    background: white; border: 1px solid var(--border);
    border-left: 3px solid var(--blue); padding: 10px 14px;
    border-radius: 2px;
  }}
  .endpoint code {{
    color: var(--blue); font-family: Consolas, monospace;
    font-weight: 600;
  }}
  .endpoint span {{
    display: block; color: var(--muted); font-size: 9pt;
    margin-top: 3px;
  }}
  a {{ color: var(--blue); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .subtle {{ color: var(--muted); font-size: 9pt; }}
</style>
</head><body>
<div class="topbar">
  <span class="logo">&#x25C6;</span>
  <span class="brand">APC RUNTIME</span>
  <span class="sep">|</span>
  <span class="subtitle">{n} controller(s) loaded</span>
</div>
<main>
  <h1>Loaded controllers</h1>
  <table>
    <thead><tr>
      <th>Key</th><th>Name</th><th>Status</th><th>Cycle</th>
      <th>Last cycle</th><th>Endpoints</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>

  <h1>REST endpoints</h1>
  <div class="endpoint-list">
    <div class="endpoint"><code>GET /healthz</code><span>liveness probe</span></div>
    <div class="endpoint"><code>GET /controllers</code><span>list of loaded controllers</span></div>
    <div class="endpoint"><code>GET /controllers/{{key}}/status</code><span>full snapshot</span></div>
    <div class="endpoint"><code>GET /controllers/{{key}}/latest</code><span>latest cycle record</span></div>
    <div class="endpoint"><code>GET /controllers/{{key}}/cv/{{tag}}</code><span>CV trend (from local SQLite)</span></div>
    <div class="endpoint"><code>GET /controllers/{{key}}/mv/{{tag}}</code><span>MV trend</span></div>
    <div class="endpoint"><code>POST /controllers/{{key}}/pause</code><span>pause cycle loop</span></div>
    <div class="endpoint"><code>POST /controllers/{{key}}/resume</code><span>resume cycle loop</span></div>
    <div class="endpoint"><code>POST /controllers/{{key}}/reload</code><span>reload tuning from .apcproj</span></div>
    <div class="endpoint"><code>POST /controllers/{{key}}/stop</code><span>graceful stop</span></div>
    <div class="endpoint"><code>GET /metrics</code><span>Prometheus text format</span></div>
    <div class="endpoint"><code>GET /api</code><span>JSON discovery (machine-readable root)</span></div>
  </div>

  <p class="subtle">Auto-refreshes every 5 seconds. For an operator console
    with live trends and tuning forms, run <strong>apc-manager</strong>
    and point it at this runtime.</p>
</main>
</body></html>
"""


def serve(multi: MultiRunner, host: str = "127.0.0.1", port: int = 8765,
           log_level: str = "warning") -> None:
    """Run the REST server with uvicorn (blocking)."""
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError(
            "uvicorn is required to serve the REST surface. "
            "Install it: pip install uvicorn"
        ) from e
    app = build_app(multi)
    uvicorn.run(app, host=host, port=port, log_level=log_level)
