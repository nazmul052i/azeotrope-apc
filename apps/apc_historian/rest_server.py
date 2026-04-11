"""apc_historian REST server.

Endpoints:

  POST /ingest                       -- one cycle record from a runner
  POST /ingest/batch                 -- list of cycle records (replay)

  GET  /healthz                      -- liveness
  GET  /controllers                  -- list of known controllers
  GET  /controllers/{ctrl}           -- summary + tags
  GET  /controllers/{ctrl}/cv/{tag}  -- trend (?field=measured&limit=...&since_ms=...)
  GET  /controllers/{ctrl}/mv/{tag}  -- trend
  GET  /controllers/{ctrl}/latest    -- last cycle row
  GET  /controllers/{ctrl}/kpi       -- KPI summary (?window_min=60)

  POST /admin/purge?older_than_ms=N
  POST /admin/compact

The ingest payload is exactly what apc_runtime's ``CycleRecord`` JSONs
to today, with the controller name as the top-level ``controller`` key.
The runtime forwards a copy of every cycle record here.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .kpi import compute_kpis
from .store import HistorianStore, IngestRecord


_LOG = logging.getLogger("apc_historian.rest")


def build_app(store: HistorianStore):
    """Construct the FastAPI app bound to a HistorianStore."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError as e:
        raise RuntimeError(
            "FastAPI is required. Install with: pip install fastapi uvicorn"
        ) from e

    app = FastAPI(
        title="Azeotrope APC Historian",
        version="0.1.0",
        description="Centralised cycle store + query service",
    )

    # ── Health + discovery ────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    def root():
        """HTML landing page so 'Open in Browser' from the launcher
        shows something useful instead of raw JSON. Lists every
        controller currently stored with cycle counts and links to
        the JSON endpoints + KPI summary."""
        return _historian_index_html(store)

    @app.get("/api", include_in_schema=False)
    def api_root():
        return {
            "name": "Azeotrope APC Historian",
            "version": "0.1.0",
            "controllers": [c["controller"] for c in store.list_controllers()],
            "db_size_bytes": store.database_size(),
        }

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "controllers": len(store.list_controllers()),
                "db_size_bytes": store.database_size()}

    # ── Ingestion ────────────────────────────────────────────────
    @app.post("/ingest")
    def ingest(payload: Dict[str, Any]):
        try:
            rec = IngestRecord.from_dict(payload)
        except Exception as e:
            raise HTTPException(status_code=400,
                                 detail=f"bad payload: {e}")
        try:
            store.ingest(rec)
        except Exception as e:
            _LOG.exception("ingest failed")
            raise HTTPException(status_code=500, detail=str(e))
        return {"ok": True, "controller": rec.controller, "cycle": rec.cycle}

    @app.post("/ingest/batch")
    def ingest_batch(payload: Dict[str, Any]):
        records = payload.get("records") or []
        n_ok = 0
        n_err = 0
        for raw in records:
            try:
                store.ingest(IngestRecord.from_dict(raw))
                n_ok += 1
            except Exception:
                n_err += 1
        return {"ok": True, "ingested": n_ok, "failed": n_err}

    # ── Per-controller queries ───────────────────────────────────
    @app.get("/controllers")
    def list_controllers():
        return {"controllers": store.list_controllers()}

    @app.get("/controllers/{controller}")
    def get_controller(controller: str):
        items = [c for c in store.list_controllers()
                 if c["controller"] == controller]
        if not items:
            raise HTTPException(status_code=404,
                                 detail=f"unknown controller: {controller}")
        info = items[0]
        info["cv_tags"] = store.list_cv_tags(controller)
        info["mv_tags"] = store.list_mv_tags(controller)
        info["latest"] = store.latest_cycle(controller)
        info["cycle_count"] = store.cycle_count(controller)
        return info

    @app.get("/controllers/{controller}/cv/{cv_name}")
    def query_cv(controller: str, cv_name: str,
                  field: str = "measured", limit: int = 1000,
                  since_ms: Optional[int] = None):
        try:
            rows = store.query_cv(controller, cv_name, field_name=field,
                                   limit=limit, since_ms=since_ms)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "controller": controller, "cv": cv_name, "field": field,
            "samples": [{"ts": ts, "value": v} for ts, v in rows],
        }

    @app.get("/controllers/{controller}/mv/{mv_name}")
    def query_mv(controller: str, mv_name: str,
                  field: str = "value", limit: int = 1000,
                  since_ms: Optional[int] = None):
        try:
            rows = store.query_mv(controller, mv_name, field_name=field,
                                   limit=limit, since_ms=since_ms)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "controller": controller, "mv": mv_name, "field": field,
            "samples": [{"ts": ts, "value": v} for ts, v in rows],
        }

    @app.get("/controllers/{controller}/latest")
    def latest(controller: str):
        row = store.latest_cycle(controller)
        if row is None:
            raise HTTPException(status_code=404,
                                 detail=f"no cycles for {controller}")
        return row

    @app.get("/controllers/{controller}/kpi")
    def kpi(controller: str, window_min: int = 60,
             on_control_band_pct: float = 0.05):
        items = [c for c in store.list_controllers()
                 if c["controller"] == controller]
        if not items:
            raise HTTPException(status_code=404,
                                 detail=f"unknown controller: {controller}")
        summary = compute_kpis(
            store, controller,
            window_ms=window_min * 60_000,
            on_control_band_pct=on_control_band_pct,
        )
        return summary.to_dict()

    # ── Admin ────────────────────────────────────────────────────
    @app.post("/admin/purge")
    def purge(older_than_ms: int):
        deleted = store.purge_older_than(older_than_ms)
        return {"ok": True, "deleted": deleted}

    @app.post("/admin/compact")
    def compact():
        store.compact()
        return {"ok": True, "db_size_bytes": store.database_size()}

    return app


def _historian_index_html(store: HistorianStore) -> str:
    """Render the historian landing page in DeltaV Live Silver chrome.

    Inline (no Jinja2) so the historian stays a single-file dependency
    on top of FastAPI.
    """
    from azeoapc.theme import SILVER

    controllers = store.list_controllers()
    n = len(controllers)
    db_kb = store.database_size() / 1024.0

    rows = []
    for c in controllers:
        name = c["controller"]
        cycles = store.cycle_count(name)
        rows.append(f"""
        <tr>
          <td><strong>{name}</strong></td>
          <td>{c['n_cv']}/{c['n_mv']}/{c['n_dv']}</td>
          <td>{cycles}</td>
          <td>
            <a href="/controllers/{name}">detail</a> ·
            <a href="/controllers/{name}/latest">latest</a> ·
            <a href="/controllers/{name}/kpi">kpi</a>
          </td>
        </tr>
        """)
    rows_html = "".join(rows) or """
        <tr><td colspan="4" style="text-align:center;padding:20px;color:#707070">
        No controllers have streamed in yet. Start an apc_runtime
        with --historian-url pointing here.</td></tr>
    """

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>APC Historian</title>
<meta http-equiv="refresh" content="10">
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
  .stats {{
    display: flex; gap: 10px; margin-bottom: 18px;
  }}
  .stat {{
    background: white; border: 1px solid var(--border);
    padding: 10px 18px; border-radius: 2px;
  }}
  .stat span {{
    display: block; color: var(--muted); font-size: 9pt;
    text-transform: uppercase; letter-spacing: 1px;
  }}
  .stat strong {{ display: block; font-size: 16pt; }}
  a {{ color: var(--blue); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .subtle {{ color: var(--muted); font-size: 9pt; }}
</style>
</head><body>
<div class="topbar">
  <span class="logo">&#x25C6;</span>
  <span class="brand">APC HISTORIAN</span>
  <span class="sep">|</span>
  <span class="subtitle">{n} controller(s) ingested</span>
</div>
<main>
  <div class="stats">
    <div class="stat"><span>Controllers</span><strong>{n}</strong></div>
    <div class="stat"><span>Database size</span><strong>{db_kb:.1f} KB</strong></div>
  </div>

  <h1>Stored controllers</h1>
  <table>
    <thead><tr>
      <th>Controller</th><th>CV/MV/DV</th><th>Cycles stored</th><th>Endpoints</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>

  <h1>REST endpoints</h1>
  <div class="endpoint-list">
    <div class="endpoint"><code>GET /healthz</code><span>liveness</span></div>
    <div class="endpoint"><code>GET /controllers</code><span>list of stored controllers</span></div>
    <div class="endpoint"><code>GET /controllers/{{name}}</code><span>summary + tag list</span></div>
    <div class="endpoint"><code>GET /controllers/{{name}}/latest</code><span>last cycle row</span></div>
    <div class="endpoint"><code>GET /controllers/{{name}}/cv/{{tag}}</code><span>CV trend</span></div>
    <div class="endpoint"><code>GET /controllers/{{name}}/mv/{{tag}}</code><span>MV trend</span></div>
    <div class="endpoint"><code>GET /controllers/{{name}}/kpi</code><span>KPI summary</span></div>
    <div class="endpoint"><code>POST /ingest</code><span>cycle record (called by apc_runtime)</span></div>
    <div class="endpoint"><code>POST /admin/purge</code><span>delete old records</span></div>
    <div class="endpoint"><code>POST /admin/compact</code><span>VACUUM database</span></div>
    <div class="endpoint"><code>GET /api</code><span>JSON discovery (machine-readable root)</span></div>
  </div>

  <p class="subtle">Auto-refreshes every 10 seconds. For interactive
    trends and operator tuning, run <strong>apc-manager</strong>
    pointed at this historian.</p>
</main>
</body></html>
"""


def serve(store: HistorianStore, host: str = "127.0.0.1", port: int = 8770,
           log_level: str = "warning") -> None:
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError(
            "uvicorn is required. Install with: pip install uvicorn"
        ) from e
    app = build_app(store)
    uvicorn.run(app, host=host, port=port, log_level=log_level)
