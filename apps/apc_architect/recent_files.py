"""Recent-files persistence backed by QSettings.

Stores under organization "Azeotrope" / application "APC Architect" so the
list survives across runs and is naturally per-user. Paths are kept in
most-recently-used order, capped at ``max_entries``, and dead paths are
filtered out on read so a missing file never reaches the menu.
"""
from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import QSettings


class RecentFiles:
    """A small wrapper around QSettings for the File > Open Recent menu."""

    KEY = "recent_files"

    def __init__(self, max_entries: int = 10):
        self.max_entries = max_entries
        self._settings = QSettings("Azeotrope", "APC Architect")

    # ------------------------------------------------------------------
    def get(self) -> List[str]:
        """Return the list of recent file paths, freshest first.

        Drops paths that no longer exist on disk.
        """
        raw = self._settings.value(self.KEY, [], type=list)
        if not isinstance(raw, list):
            return []
        out: List[str] = []
        for p in raw:
            if isinstance(p, str) and os.path.exists(p):
                out.append(p)
        return out

    # ------------------------------------------------------------------
    def add(self, path: str) -> None:
        """Push a path to the front of the list, deduping."""
        if not path:
            return
        abs_path = os.path.abspath(path)
        existing = [p for p in self.get() if os.path.abspath(p) != abs_path]
        existing.insert(0, abs_path)
        self._settings.setValue(self.KEY, existing[: self.max_entries])
        self._settings.sync()

    # ------------------------------------------------------------------
    def clear(self) -> None:
        self._settings.setValue(self.KEY, [])
        self._settings.sync()
