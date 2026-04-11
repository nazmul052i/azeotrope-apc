"""APC Historian -- centralized timeseries store + query service.

Plays the data-layer role in the architecture diagram (the layer that
sits between RTE Service and PCWS / Aspen Watch). Owns one shared
SQLite database covering ALL controllers running on the box, exposes
a REST API for trend queries and KPI summaries, and applies a
configurable retention policy.

Architecture:

    apc_runtime ──HTTP POST──> apc_historian ──REST──> apc_manager
       (writer)                    (store)              (reader)

  * apc_runtime keeps its OWN local SQLite for crash recovery -- the
    historian is best-effort. If the historian is down, the runtime
    just queues records in memory and retries.
  * apc_historian owns the long-lived shared store and the query API.
    A second runtime can come online and start writing immediately --
    no shared-DB race because writes are HTTP-serialized.

Modules:
  store.py        -- HistorianStore: shared SQLite + WAL + retention
  rest_server.py  -- FastAPI app: ingest + query + KPI endpoints
  kpi.py          -- KPI calculator (CV-on-control %, solver stats)
  cli.py          -- argparse + entry point
  app.py          -- main() symbol for pyproject scripts
"""
from .store import HistorianStore, IngestRecord
from .kpi import KpiSummary, compute_kpis

__all__ = [
    "HistorianStore", "IngestRecord",
    "KpiSummary", "compute_kpis",
]
