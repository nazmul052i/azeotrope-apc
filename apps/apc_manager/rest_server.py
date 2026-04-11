"""apc_manager FastAPI app -- the operator console.

Server-side rendered (Jinja2) so the operator pages work in any
browser without a build step. The trend page is the only one that
fetches data client-side via fetch + Plotly.

Routes:
  GET  /                                  -- dashboard
  GET  /controllers                       -- alias for /
  GET  /controllers/{key}                 -- live status table
  GET  /controllers/{key}/trends          -- Plotly trends
  GET  /controllers/{key}/tuning          -- operator tuning form
  POST /controllers/{key}/pause           -- forwards to runtime
  POST /controllers/{key}/resume          -- forwards to runtime
  POST /controllers/{key}/tune-cv         -- form submission
  POST /controllers/{key}/tune-mv         -- form submission

  GET  /api/trend/{key}/cv/{tag}          -- JSON for the Plotly client
  GET  /api/trend/{key}/mv/{tag}          -- JSON for the Plotly client
  GET  /healthz                           -- liveness
"""
# NOTE: deliberately NOT using `from __future__ import annotations` -- FastAPI's
# signature inspection needs real type objects (not stringified annotations) to
# recognise Request, Form, etc. With PEP 563 enabled it falls back to treating
# every parameter as a query field and 422s on the first request.
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .services.historian_client import HistorianClient
from .services.runtime_client import RuntimeClient


_LOG = logging.getLogger("apc_manager.rest")
_HERE = os.path.dirname(os.path.abspath(__file__))


def build_app(
    runtime_url: str,
    historian_url: str,
    *,
    runtime_client: Optional[RuntimeClient] = None,
    historian_client: Optional[HistorianClient] = None,
):
    """Construct the manager FastAPI app.

    Optional client overrides exist so tests can inject in-process
    fakes; the production CLI uses the URL-based defaults.
    """
    try:
        from fastapi import FastAPI, Form, HTTPException, Request
        from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except ImportError as e:
        raise RuntimeError(
            "FastAPI + jinja2 are required. "
            "Install with: pip install fastapi uvicorn jinja2"
        ) from e

    runtime = runtime_client or RuntimeClient(runtime_url)
    historian = historian_client or HistorianClient(historian_url)

    app = FastAPI(
        title="Azeotrope APC Manager",
        version="0.1.0",
        description="Operator console (PCWS equivalent)",
    )

    templates = Jinja2Templates(directory=os.path.join(_HERE, "templates"))
    app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")),
              name="static")

    # ------------------------------------------------------------------
    def _ctx(request: Request, **extra) -> Dict[str, Any]:
        runtime_ok = False
        historian_ok = False
        try:
            runtime.healthz()
            runtime_ok = True
        except Exception:
            pass
        try:
            historian.healthz()
            historian_ok = True
        except Exception:
            pass
        ctx = {
            "request": request,
            "runtime_ok": runtime_ok,
            "historian_ok": historian_ok,
        }
        ctx.update(extra)
        return ctx

    # ── Health ────────────────────────────────────────────────────
    @app.get("/healthz")
    def healthz():
        return {"ok": True, "runtime": runtime.base_url,
                "historian": historian.base_url}

    # ── Dashboard ────────────────────────────────────────────────
    def _dashboard(request: Request):
        try:
            controllers = runtime.list_controllers()
            error = None
        except Exception as e:
            controllers = []
            error = f"runtime unreachable: {e}"
        return templates.TemplateResponse(
            "dashboard.html",
            _ctx(request, controllers=controllers, error=error),
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard_root(request: Request):
        return _dashboard(request)

    @app.get("/controllers", response_class=HTMLResponse)
    def dashboard_alias(request: Request):
        return _dashboard(request)

    # ── Per-controller live view ─────────────────────────────────
    @app.get("/controllers/{key}", response_class=HTMLResponse)
    def controller_live(request: Request, key: str):
        try:
            status_obj = runtime.status(key)
        except Exception as e:
            return templates.TemplateResponse(
                "controller.html",
                _ctx(request, key=key, name=key, status="ERROR",
                     status_obj={}, cvs=[], mvs=[], dvs=[],
                     kpi=None, kpi_cvs={},
                     error=f"runtime: {e}"),
            )
        try:
            latest = runtime.latest(key)
        except Exception as e:
            latest = {"cv": [], "mv": [], "dv": []}

        # Pull KPIs from historian (best-effort)
        kpi = None
        kpi_cvs: Dict[str, Any] = {}
        try:
            kpi = historian.kpi(status_obj["name"], window_min=60)
            kpi_cvs = {c["cv"]: c for c in kpi.get("cvs", [])}
        except Exception:
            pass

        return templates.TemplateResponse(
            "controller.html",
            _ctx(request,
                 key=key,
                 name=status_obj.get("name") or key,
                 status=status_obj.get("status") or "UNKNOWN",
                 status_obj=status_obj,
                 cvs=latest.get("cv", []),
                 mvs=latest.get("mv", []),
                 dvs=latest.get("dv", []),
                 kpi=kpi,
                 kpi_cvs=kpi_cvs,
                 error=None),
        )

    # ── Trends page ──────────────────────────────────────────────
    @app.get("/controllers/{key}/trends", response_class=HTMLResponse)
    def controller_trends(request: Request, key: str):
        try:
            status_obj = runtime.status(key)
            latest = runtime.latest(key)
            cv_tags = [c["tag"] for c in latest.get("cv", [])]
            mv_tags = [m["tag"] for m in latest.get("mv", [])]
        except Exception as e:
            return templates.TemplateResponse(
                "trends.html",
                _ctx(request, key=key, name=key,
                     cv_tags=[], mv_tags=[],
                     error=f"runtime: {e}"),
            )
        return templates.TemplateResponse(
            "trends.html",
            _ctx(request, key=key,
                 name=status_obj.get("name") or key,
                 cv_tags=cv_tags, mv_tags=mv_tags,
                 error=None),
        )

    # ── Tuning page ──────────────────────────────────────────────
    @app.get("/controllers/{key}/tuning", response_class=HTMLResponse)
    def controller_tuning(request: Request, key: str,
                           message: Optional[str] = None):
        try:
            status_obj = runtime.status(key)
            latest = runtime.latest(key)
        except Exception as e:
            return templates.TemplateResponse(
                "tuning.html",
                _ctx(request, key=key, name=key, cvs=[], mvs=[],
                     error=f"runtime: {e}", message=None),
            )
        cvs = latest.get("cv", [])
        mvs = latest.get("mv", [])
        # Backfill move_suppress from a default since the cycle record
        # doesn't include it (cosmetic display only).
        for mv in mvs:
            mv.setdefault("move_suppress", "")
        return templates.TemplateResponse(
            "tuning.html",
            _ctx(request, key=key,
                 name=status_obj.get("name") or key,
                 cvs=cvs, mvs=mvs, error=None, message=message),
        )

    # ── Form submissions ─────────────────────────────────────────
    @app.post("/controllers/{key}/pause")
    def pause(key: str):
        try:
            runtime.pause(key)
        except Exception as e:
            _LOG.warning("pause failed: %s", e)
        return RedirectResponse(f"/controllers/{key}", status_code=303)

    @app.post("/controllers/{key}/resume")
    def resume(key: str):
        try:
            runtime.resume(key)
        except Exception as e:
            _LOG.warning("resume failed: %s", e)
        return RedirectResponse(f"/controllers/{key}", status_code=303)

    @app.post("/controllers/{key}/tune-cv")
    def tune_cv(key: str,
                 cv_tag: str = Form(...),
                 setpoint: Optional[float] = Form(None),
                 lo_limit: Optional[float] = Form(None),
                 hi_limit: Optional[float] = Form(None)):
        msgs: List[str] = []
        try:
            if setpoint is not None:
                runtime.set_cv_setpoint(key, cv_tag, setpoint)
                msgs.append(f"{cv_tag}.setpoint = {setpoint}")
            if lo_limit is not None or hi_limit is not None:
                runtime.set_cv_limits(key, cv_tag,
                                       lo=lo_limit, hi=hi_limit)
                msgs.append(f"{cv_tag} limits lo={lo_limit} hi={hi_limit}")
        except Exception as e:
            msgs.append(f"ERROR: {e}")
        return RedirectResponse(
            f"/controllers/{key}/tuning?message=" +
            "+".join(msgs).replace(" ", "+"),
            status_code=303)

    @app.post("/controllers/{key}/tune-mv")
    def tune_mv(key: str,
                 mv_tag: str = Form(...),
                 lo_limit: Optional[float] = Form(None),
                 hi_limit: Optional[float] = Form(None),
                 move_suppress: Optional[float] = Form(None)):
        msgs: List[str] = []
        try:
            if lo_limit is not None or hi_limit is not None:
                runtime.set_mv_limits(key, mv_tag, lo=lo_limit, hi=hi_limit)
                msgs.append(f"{mv_tag} limits lo={lo_limit} hi={hi_limit}")
            if move_suppress is not None:
                runtime.set_mv_move_suppress(key, mv_tag, move_suppress)
                msgs.append(f"{mv_tag}.move_suppress = {move_suppress}")
        except Exception as e:
            msgs.append(f"ERROR: {e}")
        return RedirectResponse(
            f"/controllers/{key}/tuning?message=" +
            "+".join(msgs).replace(" ", "+"),
            status_code=303)

    # ── JSON endpoints used by the trends page ──────────────────
    @app.get("/api/trend/{key}/cv/{tag}")
    def api_cv_trend(key: str, tag: str, window_min: int = 60):
        try:
            status_obj = runtime.status(key)
            ctrl_name = status_obj.get("name") or key
            since_ms = int(time.time() * 1000) - window_min * 60_000
            data = historian.cv_trend(ctrl_name, tag,
                                        limit=2000, since_ms=since_ms)
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({"error": str(e), "samples": []},
                                 status_code=502)

    @app.get("/api/trend/{key}/mv/{tag}")
    def api_mv_trend(key: str, tag: str, window_min: int = 60):
        try:
            status_obj = runtime.status(key)
            ctrl_name = status_obj.get("name") or key
            since_ms = int(time.time() * 1000) - window_min * 60_000
            data = historian.mv_trend(ctrl_name, tag,
                                        limit=2000, since_ms=since_ms)
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({"error": str(e), "samples": []},
                                 status_code=502)

    return app


def serve(runtime_url: str, historian_url: str, *,
           host: str = "127.0.0.1", port: int = 8780,
           log_level: str = "warning") -> None:
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError(
            "uvicorn is required. Install with: pip install uvicorn"
        ) from e
    app = build_app(runtime_url, historian_url)
    uvicorn.run(app, host=host, port=port, log_level=log_level)
