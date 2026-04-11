"""apc-historian CLI.

Usage:

    apc-historian [--db-path historian.db]
                  [--host 127.0.0.1] [--port 8770]
                  [--retention-days 30]
                  [--log-level info]

Lifecycle:
  1. Open / create the SQLite store
  2. (Optional) start a background retention thread
  3. Run the FastAPI app via uvicorn (blocks)
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from typing import List

from .rest_server import build_app
from .store import HistorianStore


_LOG = logging.getLogger("apc_historian.cli")


def parse_argv(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="apc-historian",
        description="Centralised cycle store + query service")
    p.add_argument("--db-path", default="runs/historian/historian.db",
                    help="SQLite file path")
    p.add_argument("--host", default="127.0.0.1",
                    help="REST server bind address")
    p.add_argument("--port", type=int, default=8770,
                    help="REST server port")
    p.add_argument("--retention-days", type=int, default=30,
                    help="Auto-purge records older than this many days "
                          "(0 disables)")
    p.add_argument("--retention-interval-min", type=int, default=60,
                    help="How often the retention thread runs")
    p.add_argument("--log-level", default="info",
                    choices=["debug", "info", "warning", "error"])
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
def _retention_loop(store: HistorianStore, days: int, interval_min: int,
                     stop_event: threading.Event) -> None:
    """Background thread: purge old records on a schedule."""
    while not stop_event.is_set():
        # Sleep first so we don't purge immediately on startup
        if stop_event.wait(interval_min * 60):
            return
        cutoff = int(time.time() * 1000) - days * 86_400_000
        try:
            deleted = store.purge_older_than(cutoff)
            total = sum(deleted.values())
            if total > 0:
                _LOG.info("retention purged %d rows (cutoff=%d): %s",
                          total, cutoff, deleted)
        except Exception as e:
            _LOG.warning("retention purge failed: %s", e)


# ---------------------------------------------------------------------------
def main(argv: List[str] = None) -> int:
    args = parse_argv(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    _LOG.info("apc-historian opening %s", args.db_path)
    store = HistorianStore(args.db_path)

    # Optional retention thread
    retention_stop = threading.Event()
    retention_thread = None
    if args.retention_days > 0:
        retention_thread = threading.Thread(
            target=_retention_loop,
            args=(store, args.retention_days,
                  args.retention_interval_min, retention_stop),
            name="apc-historian-retention",
            daemon=True,
        )
        retention_thread.start()
        _LOG.info("retention thread started: %d days, every %d min",
                  args.retention_days, args.retention_interval_min)

    # Signal handlers
    def _shutdown(signum, frame):
        _LOG.info("received signal %d, closing store", signum)
        retention_stop.set()
        store.close()
        sys.exit(0)
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Serve REST (blocks)
    try:
        import uvicorn
    except ImportError:
        _LOG.error("uvicorn not installed; install fastapi + uvicorn")
        store.close()
        return 1

    app = build_app(store)
    _LOG.info("REST listening on http://%s:%d", args.host, args.port)
    try:
        uvicorn.run(app, host=args.host, port=args.port,
                    log_level=args.log_level)
    finally:
        retention_stop.set()
        store.close()
    return 0
