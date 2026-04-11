"""APC Manager -- the operator console (PCWS equivalent).

Web app that gives operators a unified live view of every controller
running in the box. Reads from BOTH apc_runtime (live status, push
tuning) and apc_historian (trends, KPIs).

Pages:
  /                          -- dashboard: controller grid + status badges
  /controllers/{key}         -- per-controller live table + actions
  /controllers/{key}/trends  -- Plotly trends from historian
  /controllers/{key}/tuning  -- operator tuning form

The manager is intentionally a thin layer -- it owns no state, just
proxies to the runtime + historian REST APIs and renders Jinja
templates. State of the world lives in the runtime/historian, not here.

Modules:
  services/runtime_client.py    -- async client for apc_runtime
  services/historian_client.py  -- async client for apc_historian
  rest_server.py                -- FastAPI app + Jinja templates
  cli.py                        -- argparse + entry point
  app.py                        -- main() symbol for pyproject scripts
"""
from .services.runtime_client import RuntimeClient
from .services.historian_client import HistorianClient

__all__ = ["RuntimeClient", "HistorianClient"]
