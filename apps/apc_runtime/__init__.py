"""APC Runtime -- headless production controller cycle loop.

Loads a controller .apcproj file, builds a SimEngine, and runs the
DeploymentRuntime cycle loop unattended. Designed to be the production
twin of apc_architect's Simulation tab.

Modules:
  runner.py        -- single-controller Runner (loads cfg, runs cycles)
  multi_runner.py  -- MultiRunner orchestrating several controllers
  log_writer.py    -- JSON-lines cycle log + latest.json snapshot
  historian.py     -- SQLite store matching core/include/azeoapc/storage.h
  rest_server.py   -- FastAPI control surface (optional dep)
  prometheus.py    -- /metrics in Prometheus text format
  cli.py           -- argparse + entry point for `apc-runtime`
  app.py           -- main() invoked by the script entry

Lifecycle of a single Runner:
  1. load_config(.apcproj) -> SimConfig
  2. SimEngine(cfg)        -- builds plant + MPC controller
  3. DeploymentRuntime(engine, deployment_cfg) on a worker thread
  4. Each cycle: read PVs, run engine.step(), write SPs, log to disk
  5. SIGHUP -> re-read tuning sections from the same file
  6. SIGINT -> graceful stop, flush logs, close historian

The runtime intentionally does NOT depend on PySide6 -- the runner
loop uses only stdlib threads + signals so it runs on a headless
server with no Qt installed.
"""
from .runner import Runner, RunnerStatus, RunnerSnapshot
from .log_writer import CycleLogWriter, CycleRecord
from .historian import Historian

__all__ = [
    "Runner", "RunnerStatus", "RunnerSnapshot",
    "CycleLogWriter", "CycleRecord",
    "Historian",
]
