"""Multi-controller runner -- several Runners in one process.

Production sites typically host several controllers per box. The
MultiRunner owns a list of Runners (one per .apcproj path), starts
them all on independent threads, and exposes a unified snapshot for
the REST surface to expose. Each Runner already runs on its own
thread, so MultiRunner just orchestrates start/stop/snapshot.

Per-controller run dirs default to ``runs/<slug>/`` so the historian
files don't collide. Override by passing a list of (path, run_dir)
tuples instead of bare paths.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .runner import Runner, RunnerSnapshot, RunnerStatus


PathLike = Union[str, Tuple[str, str]]


class MultiRunner:
    """Container for several Runners. Thin orchestration wrapper."""

    def __init__(
        self,
        projects: Sequence[PathLike],
        *,
        runs_root: str = "runs",
        use_embedded_server: bool = True,
        enable_historian: bool = True,
        historian_url: Optional[str] = None,
    ):
        self.runs_root = os.path.abspath(runs_root)
        os.makedirs(self.runs_root, exist_ok=True)
        self.runners: Dict[str, Runner] = {}
        for entry in projects:
            if isinstance(entry, tuple):
                path, run_dir = entry
            else:
                path = entry
                run_dir = None
            r = self._make_runner(
                path, run_dir,
                use_embedded_server=use_embedded_server,
                enable_historian=enable_historian,
                historian_url=historian_url,
            )
            # Avoid name collisions when two .apcproj files have the same basename
            key = self._unique_key(os.path.splitext(os.path.basename(path))[0])
            self.runners[key] = r

    # ------------------------------------------------------------------
    def _make_runner(self, path: str, run_dir: Optional[str], **kwargs) -> Runner:
        if run_dir is None:
            slug = os.path.splitext(os.path.basename(path))[0]
            run_dir = os.path.join(self.runs_root, slug)
        return Runner(path, run_dir=run_dir, **kwargs)

    def _unique_key(self, base: str) -> str:
        if base not in self.runners:
            return base
        i = 2
        while f"{base}_{i}" in self.runners:
            i += 1
        return f"{base}_{i}"

    # ==================================================================
    def start_all(self) -> None:
        for r in self.runners.values():
            r.start()

    def stop_all(self, join_timeout: float = 10.0) -> None:
        for r in self.runners.values():
            r.stop(join_timeout=join_timeout)

    def pause_all(self) -> None:
        for r in self.runners.values():
            r.pause()

    def resume_all(self) -> None:
        for r in self.runners.values():
            r.resume()

    def reload_all(self) -> None:
        for r in self.runners.values():
            r.reload()

    # ==================================================================
    def snapshot_all(self) -> Dict[str, RunnerSnapshot]:
        return {key: r.snapshot() for key, r in self.runners.items()}

    def get(self, key: str) -> Optional[Runner]:
        return self.runners.get(key)

    def keys(self) -> List[str]:
        return list(self.runners.keys())

    def is_any_running(self) -> bool:
        return any(r.is_running() for r in self.runners.values())
