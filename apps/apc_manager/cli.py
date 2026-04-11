"""apc-manager CLI.

Usage:

    apc-manager [--runtime-url http://localhost:8765]
                [--historian-url http://localhost:8770]
                [--host 127.0.0.1] [--port 8780]
                [--log-level info]
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
from typing import List

from .rest_server import serve


_LOG = logging.getLogger("apc_manager.cli")


def parse_argv(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="apc-manager",
        description="Operator console for apc_runtime + apc_historian")
    p.add_argument("--runtime-url", default="http://127.0.0.1:8765",
                    help="apc_runtime REST URL")
    p.add_argument("--historian-url", default="http://127.0.0.1:8770",
                    help="apc_historian REST URL")
    p.add_argument("--host", default="127.0.0.1",
                    help="Manager bind address")
    p.add_argument("--port", type=int, default=8780,
                    help="Manager port")
    p.add_argument("--log-level", default="info",
                    choices=["debug", "info", "warning", "error"])
    return p.parse_args(argv)


def main(argv: List[str] = None) -> int:
    args = parse_argv(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )

    def _shutdown(signum, frame):
        _LOG.info("received signal %d, exiting", signum)
        sys.exit(0)
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    _LOG.info("apc-manager starting on http://%s:%d", args.host, args.port)
    _LOG.info("  runtime  : %s", args.runtime_url)
    _LOG.info("  historian: %s", args.historian_url)
    try:
        serve(args.runtime_url, args.historian_url,
              host=args.host, port=args.port,
              log_level=args.log_level)
    except KeyboardInterrupt:
        pass
    return 0
