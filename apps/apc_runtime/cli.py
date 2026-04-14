"""apc-runtime CLI.

Two execution modes:

  * **GUI mode (default)** -- spawn a desktop window (Aspen Watch
    Maker style) showing every loaded controller in a table with
    Start / Stop / Pause / Resume actions. Positional .apcproj
    arguments are pre-loaded into the table; if none are given the
    user can add controllers from the File > Add Controller menu.
    The REST surface still runs in a background uvicorn thread so
    apc_manager can talk to us.

  * **Headless mode** (--headless) -- the original server-only path.
    Skips Qt entirely; runs MultiRunner + REST + signal handlers
    in the main thread. Use this on production boxes that just
    need the cycle loop without a window.

Usage:

    apc-runtime [path/to/controller.apcproj ...]
        [--headless]
        [--runs-dir runs/]
        [--rest-host 127.0.0.1]
        [--rest-port 8765]
        [--no-rest]
        [--no-historian]
        [--no-embedded]
        [--historian-url http://localhost:8770]
        [--wall-period 1.0]
        [--log-level info]
        [--auto-start]            (GUI: start each loaded controller
                                    immediately on window open)
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import List, Optional

from .multi_runner import MultiRunner


_LOG = logging.getLogger("apc_runtime.cli")


def parse_argv(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="apc-runtime",
        description=("Production controller cycle loop with desktop "
                      "manager (Aspen Watch Maker equivalent)"))
    p.add_argument("projects", nargs="*",
                    help="Zero or more .apcproj files to pre-load. "
                          "In GUI mode the user can also add controllers "
                          "via File > Add Controller.")
    p.add_argument("--headless", action="store_true",
                    help="Skip the desktop window and run as a "
                          "server-only process (production boxes).")
    p.add_argument("--auto-start", action="store_true",
                    help="GUI mode: immediately start every pre-loaded "
                          "controller on window open. Equivalent to the "
                          "user clicking Start All right after launch.")
    p.add_argument("--runs-dir", default="runs",
                    help="Root directory for cycle logs + historian")
    p.add_argument("--rest-host", default="127.0.0.1",
                    help="REST server bind address")
    p.add_argument("--rest-port", type=int, default=8765,
                    help="REST server port")
    p.add_argument("--no-rest", action="store_true",
                    help="Skip the REST server entirely")
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


# ---------------------------------------------------------------------------
def _build_multi(args: argparse.Namespace) -> MultiRunner:
    """Build the MultiRunner from CLI args (shared by GUI + headless)."""
    multi = MultiRunner(
        projects=args.projects,
        runs_root=args.runs_dir,
        use_embedded_server=not args.no_embedded,
        enable_historian=not args.no_historian,
        historian_url=args.historian_url,
    )
    if args.wall_period is not None:
        for r in multi.runners.values():
            r._wall_period_override = args.wall_period
    return multi


# ---------------------------------------------------------------------------
def _start_rest_in_thread(
    multi: MultiRunner, host: str, port: int, log_level: str,
) -> Optional[threading.Thread]:
    """Spin up uvicorn on a background thread so the GUI main thread
    stays free for Qt. Returns the thread (still running) or None if
    REST could not be enabled."""
    try:
        from .rest_server import build_app
        import uvicorn
    except (RuntimeError, ImportError) as e:
        _LOG.warning("REST surface disabled: %s", e)
        return None

    app = build_app(multi)
    config = uvicorn.Config(app, host=host, port=port,
                              log_level=log_level)
    server = uvicorn.Server(config)
    th = threading.Thread(
        target=server.run,
        name="apc-runtime-rest",
        daemon=True,
    )
    th.start()
    _LOG.info("REST listening on http://%s:%d (background thread)",
              host, port)
    # Stash the server on the thread so callers can request shutdown
    th.uvicorn_server = server   # type: ignore[attr-defined]
    return th


# ---------------------------------------------------------------------------
def _run_gui(args: argparse.Namespace) -> int:
    """Default mode: open the desktop manager window."""
    try:
        from PySide6.QtWidgets import QApplication
        from azeoapc.theme import apply_theme, set_window_icon
        from .main_window import RuntimeMainWindow
    except ImportError as e:
        _LOG.error(
            "GUI mode needs PySide6 + azeoapc.theme. "
            "Install with: pip install PySide6  --  or use --headless. "
            "Error: %s", e)
        return 1

    multi = _build_multi(args)
    if args.auto_start and multi.runners:
        multi.start_all()

    rest_thread = None
    rest_url = None
    if not args.no_rest:
        rest_thread = _start_rest_in_thread(
            multi, args.rest_host, args.rest_port, args.log_level)
        if rest_thread is not None:
            rest_url = f"http://{args.rest_host}:{args.rest_port}"

    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setApplicationName("APC Runtime")
    qapp.setOrganizationName("Azeotrope")
    apply_theme(qapp)
    set_window_icon(qapp, "runtime")

    window = RuntimeMainWindow(
        multi,
        rest_url=rest_url,
        historian_url=args.historian_url,
    )
    window.resize(1180, 640)
    window.show()

    rc = qapp.exec()

    # On window close: stop everything cleanly
    multi.stop_all(join_timeout=8.0)
    if rest_thread is not None:
        try:
            rest_thread.uvicorn_server.should_exit = True   # type: ignore
        except Exception:
            pass
    return rc


# ---------------------------------------------------------------------------
def _run_headless(args: argparse.Namespace) -> int:
    """Server-only mode (old behaviour) for production boxes."""
    if not args.projects:
        _LOG.error("--headless requires at least one .apcproj path")
        return 1

    multi = _build_multi(args)
    multi.start_all()
    _LOG.info("started %d runners: %s",
              len(multi.runners), list(multi.runners.keys()))

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

    if args.no_rest:
        _LOG.info("REST surface disabled; running headless")
        try:
            while multi.is_any_running():
                time.sleep(1.0)
        except KeyboardInterrupt:
            _shutdown(signal.SIGINT, None)
        return 0

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

    _LOG.info("REST listening on http://%s:%d",
              args.rest_host, args.rest_port)
    try:
        serve(multi, host=args.rest_host, port=args.rest_port,
              log_level=args.log_level)
    except KeyboardInterrupt:
        pass
    finally:
        multi.stop_all(join_timeout=10.0)
    return 0


# ---------------------------------------------------------------------------
def main(argv: List[str] = None) -> int:
    args = parse_argv(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    _LOG.info(
        "apc-runtime starting (%s mode) with %d pre-loaded controller(s)",
        "headless" if args.headless else "GUI",
        len(args.projects),
    )

    if args.headless:
        return _run_headless(args)
    return _run_gui(args)
