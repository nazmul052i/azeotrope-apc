"""Forwarder: push cycle records to a remote apc_historian service.

Lives next to the local Historian (which is a per-controller SQLite
file). The forwarder is the bridge between the Runner and an
optional centralised apc_historian service. Best-effort: if the
historian is unreachable, records are dropped after a short retry
window so the cycle loop is never blocked. The local Historian
remains the authoritative store for crash recovery.

Usage:
    fwd = HistorianForwarder("http://localhost:8770")
    fwd.start()
    fwd.enqueue(record_dict)   # called from the cycle thread
    ...
    fwd.stop()
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any, Dict, Optional


_LOG = logging.getLogger("apc_runtime.forwarder")


class HistorianForwarder:
    """Background thread that POSTs cycle records to apc_historian.

    Uses a bounded queue so a slow historian can never make the cycle
    loop block or run out of memory. When the queue is full, the
    oldest records are dropped (drop-old policy) and a counter is
    incremented for diagnostics.
    """

    def __init__(
        self,
        historian_url: str,
        *,
        max_queue: int = 1000,
        timeout_sec: float = 2.0,
        retry_seconds: float = 5.0,
    ):
        self.url = historian_url.rstrip("/") + "/ingest"
        self.max_queue = max_queue
        self.timeout_sec = timeout_sec
        self.retry_seconds = retry_seconds
        self._q: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=max_queue)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.dropped: int = 0
        self.posted: int = 0
        self.failed: int = 0
        self.last_error: str = ""

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="apc-runtime-forwarder", daemon=True)
        self._thread.start()

    def stop(self, join_timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
            self._thread = None

    # ------------------------------------------------------------------
    def enqueue(self, record_dict: Dict[str, Any]) -> None:
        """Non-blocking: drop the oldest record if the queue is full."""
        try:
            self._q.put_nowait(record_dict)
        except queue.Full:
            try:
                self._q.get_nowait()  # drop oldest
                self.dropped += 1
                self._q.put_nowait(record_dict)
            except (queue.Empty, queue.Full):
                pass

    # ------------------------------------------------------------------
    def _run(self) -> None:
        """Drain the queue, POSTing records as fast as the historian accepts."""
        try:
            import urllib.request
            import urllib.error
        except ImportError:
            _LOG.error("urllib unavailable -- forwarder cannot run")
            return

        backoff_until = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now < backoff_until:
                # We're in a backoff window after a failure -- sleep
                # in chunks so stop is responsive.
                self._stop.wait(min(0.5, backoff_until - now))
                continue

            try:
                record = self._q.get(timeout=0.5)
            except queue.Empty:
                continue

            data = json.dumps(record).encode("utf-8")
            req = urllib.request.Request(
                self.url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as r:
                    if 200 <= r.status < 300:
                        self.posted += 1
                    else:
                        raise RuntimeError(f"HTTP {r.status}")
            except urllib.error.URLError as e:
                self.failed += 1
                self.last_error = f"{type(e).__name__}: {e}"
                backoff_until = time.monotonic() + self.retry_seconds
                _LOG.debug("forwarder POST failed: %s -- backoff %.1fs",
                           self.last_error, self.retry_seconds)
            except Exception as e:
                self.failed += 1
                self.last_error = f"{type(e).__name__}: {e}"
                _LOG.debug("forwarder unexpected error: %s", self.last_error)

    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "posted": self.posted,
            "failed": self.failed,
            "dropped": self.dropped,
            "queue_size": self._q.qsize(),
            "last_error": self.last_error,
        }
