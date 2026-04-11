"""Recent .apcident files persistence -- per-user QSettings.

Same logic as apc_architect's RecentFiles but with its own QSettings
application name so the two studios don't share their lists.
"""
from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import QSettings


class RecentFiles:
    KEY = "recent_files"

    def __init__(self, max_entries: int = 10):
        self.max_entries = max_entries
        self._settings = QSettings("Azeotrope", "APC Ident")

    def get(self) -> List[str]:
        raw = self._settings.value(self.KEY, [], type=list)
        if not isinstance(raw, list):
            return []
        return [p for p in raw if isinstance(p, str) and os.path.exists(p)]

    def add(self, path: str) -> None:
        if not path:
            return
        abs_path = os.path.abspath(path)
        existing = [p for p in self.get() if os.path.abspath(p) != abs_path]
        existing.insert(0, abs_path)
        self._settings.setValue(self.KEY, existing[: self.max_entries])
        self._settings.sync()

    def clear(self) -> None:
        self._settings.setValue(self.KEY, [])
        self._settings.sync()
