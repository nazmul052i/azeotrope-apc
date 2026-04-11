"""apc-runtime CLI.

Usage:

    apc-runtime path/to/controller.apcproj [more.apcproj ...]
        --runs-dir runs/
        --rest-host 127.0.0.1
        --rest-port 8765
        --no-rest
        --no-historian
        --no-embedded
        --wall-period 1.0
        --log-level info

Lifecycle:
  1. Parse argv -> list of .apcproj paths + options
  2. Build a MultiRunner with one Runner per project
  3. start_all() spawns one worker thread per controller
  4. Install signal handlers:
       SIGINT  -> graceful stop_all + exit
       SIGTERM -> graceful stop_all + exit
       SIGHUP  -> reload_all (Unix only; ignored on Windows)
  5. If --rest is enabled, build the FastAPI app and serve forever
     (uvicorn blocks the main thread). Otherwise, sleep until SIGINT.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from typing import List

from .multi_runner import MultiRunner


_LOG = logging.getLogger("apc_runtime.cli")


def parse_argv(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="apc-runtime",
        description="Headless production controller cycle loop")
    p.add_argument("projects", nargs="+",
                    help="One or more .apcproj files to run")
    p.add_argument("--runs-dir", default="runs",
                    help="Root directory for cycle logs + historian")
    p.add_argument("--rest-host", default="127.0.0.1",
                    help="REST server bind address")
    p.add_argument("--rest-port", type=int, default=8765,
                    help="REST server port")
    p.add_argument("--no-rest", action="store_true",
                    help="Skip the REST server (run headless only)")
    p.add_argument("--no-historian", action="store_true",
                    help="Disable the SQLite historian")
    p.add_argument("--no-embedded", action="store_true",
                    help="Do not start the embedded OPC UA server "
                          "(use this when pointing at a real plant)")
    p.add_argument("--historian-url", default=None,
                    help="POST cycle records to a remote apc_historian "
                          "service (e.g. http://localhost:8770)")
    p.add_argument("--wall-period", type=float, default=None,
                    help="Override the .apcproj sample_time for cycle "
                          "pacing (seconds). Useful for compressed-time tests.")
    p.add_argument("--log-level", default="info",
                    choices=["debug", "info", "warning", "error"],
                    help="Logging verbosity")
    return p.parse_args(argv)


def main(argv: List[str] = None) -> int:
    args = parse_argv(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    _LOG.info("apc-runtime starting with %d controller(s)", len(args.projects))

    # Build the multi-runner
    multi = MultiRunner(
        projects=args.projects,
        runs_root=args.runs_dir,
        use_embedded_server=not args.no_embedded,
        enable_historian=not args.no_historian,
        historian_url=args.historian_url,
    )

    # Apply wall_period override if requested
    if args.wall_period is not None:
        for r in multi.runners.values():
            r._wall_period_override = args.wall_period

    multi.start_all()
    _LOG.info("started %d runners: %s",
              len(multi.runners), list(multi.runners.keys()))

    # Signal handlers
    def _shutdown(signum, frame):
        _LOG.info("received signal %d, stopping all runners", signum)
        multi.stop_all(join_timeout=10.0)
        _LOG.info("all runners stopped")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    if hasattr(signal, "SIGHUP"):
        def _hup(signum, frame):
            _LOG.info("SIGHUP -- requesting tuning reload on all runners")
            multi.reload_all()
        signal.signal(signal.SIGHUP, _hup)

    # Serve REST or block on the runner threads
    if args.no_rest:
        _LOG.info("REST surface disabled; running headless")
        try:
            while multi.is_any_running():
                time.sleep(1.0)
        except KeyboardInterrupt:
            _shutdown(signal.SIGINT, None)
        return 0

    # REST surface (blocks main thread)
    try:
        from .rest_server import serve
    except RuntimeError as e:
        _LOG.error("REST disabled: %s", e)
        try:
            while multi.is_any_running():
                time.sleep(1.0)
        except KeyboardInterrupt:
            _shutdown(signal.SIGINT, None)
        return 0

    _LOG.info("REST listening on http://%s:%d", args.rest_host, args.rest_port)
    try:
        serve(multi, host=args.rest_host, port=args.rest_port,
              log_level=args.log_level)
    except KeyboardInterrupt:
        pass
    finally:
        multi.stop_all(join_timeout=10.0)
    return 0
