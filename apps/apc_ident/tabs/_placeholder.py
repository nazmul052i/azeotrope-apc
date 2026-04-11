"""Shared placeholder widget used by every C3 tab.

Each tab in the C3 shell renders a centred heading + descriptive blurb.
C4 will replace these placeholder bodies with the real Data /
Identification / Results / Validation widgets, so the rest of the
studio shell (project lifecycle, dirty tracking, recent files) can be
exercised first.
"""
from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..theme import SILVER


class TabPlaceholder(QWidget):
    """Vertical column with a title, subtitle, and bullet list of features."""

    def __init__(
        self, title: str, subtitle: str, bullets: Iterable[str], parent=None,
    ):
        super().__init__(parent)
        self._build(title, subtitle, list(bullets))

    def _build(self, title: str, subtitle: str, bullets: list):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {SILVER['accent_blue']}; font-size: 22pt;"
            f" font-weight: 700; letter-spacing: 1px;")
        root.addWidget(title_lbl)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(
            f"color: {SILVER['text_secondary']}; font-size: 11pt;")
        sub_lbl.setWordWrap(True)
        root.addWidget(sub_lbl)

        rule = QFrame()
        rule.setFrameShape(QFrame.HLine)
        rule.setStyleSheet(f"color: {SILVER['border']}; max-height: 1px;")
        root.addWidget(rule)

        coming = QLabel("Coming in C4")
        coming.setStyleSheet(
            f"color: {SILVER['accent_orange']}; font-size: 9pt;"
            f" font-weight: 600; letter-spacing: 2px; text-transform: uppercase;")
        root.addWidget(coming)

        for b in bullets:
            item = QLabel(f"  \u2022  {b}")
            item.setStyleSheet(
                f"color: {SILVER['text_primary']}; font-size: 10pt;"
                f" padding: 2px 0;")
            item.setWordWrap(True)
            root.addWidget(item)

        root.addStretch()
