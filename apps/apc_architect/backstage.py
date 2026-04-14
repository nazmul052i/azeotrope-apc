"""Backstage screen -- the landing page before entering the workflow.

Shows when no project is loaded or when the user clicks the app title
in the sidebar. Provides quick access to:
- Recent projects
- New from template
- Import model bundle
- Open project file
- App info
"""
from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from azeoapc.theme.ident_theme import THEME


class RecentProjectCard(QFrame):
    """Clickable card for a recent project."""

    clicked = Signal(str)  # path

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(64)
        self.setStyleSheet(
            f"QFrame {{ background: {THEME.BG_INPUT}; "
            f"border: 1px solid {THEME.CHROME_BORDER}; border-radius: 6px; }}"
            f"QFrame:hover {{ border-color: {THEME.ACCENT}; "
            f"background: {THEME.ACCENT_LIGHT}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(2)

        name = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
        title = QLabel(name)
        title.setStyleSheet(
            f"color: {THEME.ACCENT}; font-size: 11pt; font-weight: 600; "
            f"background: transparent; border: none;")
        lay.addWidget(title)

        loc = QLabel(os.path.dirname(path))
        loc.setStyleSheet(
            f"color: {THEME.TEXT_DISABLED}; font-size: 8pt; "
            f"background: transparent; border: none;")
        loc.setWordWrap(True)
        lay.addWidget(loc)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.path)


class ActionCard(QFrame):
    """Clickable action card (New, Import, Open)."""

    clicked = Signal(str)  # action id

    def __init__(self, action_id: str, icon: str, title: str,
                 description: str, parent=None):
        super().__init__(parent)
        self.action_id = action_id
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(220, 140)
        self.setStyleSheet(
            f"QFrame {{ background: {THEME.BG_INPUT}; "
            f"border: 1px solid {THEME.CHROME_BORDER}; border-radius: 8px; }}"
            f"QFrame:hover {{ border-color: {THEME.ACCENT}; "
            f"background: {THEME.ACCENT_LIGHT}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size: 28pt; color: {THEME.ACCENT}; "
            f"background: transparent; border: none;")
        lay.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 11pt; font-weight: 600; color: {THEME.TEXT_PRIMARY}; "
            f"background: transparent; border: none;")
        lay.addWidget(title_lbl)

        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"font-size: 8pt; color: {THEME.TEXT_SECONDARY}; "
            f"background: transparent; border: none;")
        lay.addWidget(desc_lbl)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.action_id)


class BackstageScreen(QWidget):
    """Full-screen landing page."""

    action_triggered = Signal(str)    # "new", "open", "import", "template_xxx"
    recent_opened = Signal(str)       # file path

    def __init__(self, recent_paths: List[str] = None, parent=None):
        super().__init__(parent)
        self._recent_paths = recent_paths or []
        self.setStyleSheet(f"background: {THEME.BG_WINDOW};")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Hero banner ──
        hero = QFrame()
        hero.setFixedHeight(160)
        hero.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {THEME.BG_SIDEBAR}, stop:1 #1A2A3A); "
            f"border: none;")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(60, 30, 60, 20)
        hl.setSpacing(6)

        title = QLabel("APC ARCHITECT")
        title.setStyleSheet(
            f"color: white; font-size: 28pt; font-weight: bold; "
            f"letter-spacing: 3px; background: transparent;")
        hl.addWidget(title)

        subtitle = QLabel("Controller Configuration & Simulation Studio")
        subtitle.setStyleSheet(
            f"color: {THEME.TEXT_ON_SIDEBAR}; font-size: 12pt; "
            f"background: transparent;")
        hl.addWidget(subtitle)

        version = QLabel("Azeotrope APC  |  v0.2.0")
        version.setStyleSheet(
            f"color: {THEME.STEP_PENDING}; font-size: 9pt; "
            f"background: transparent;")
        hl.addWidget(version)

        root.addWidget(hero)

        # ── Content area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {THEME.BG_WINDOW}; }}")

        content = QWidget()
        content.setStyleSheet(f"background: {THEME.BG_WINDOW};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(60, 30, 60, 30)
        cl.setSpacing(30)

        # ── Actions row ──
        actions_label = QLabel("GET STARTED")
        actions_label.setStyleSheet(
            f"color: {THEME.TEXT_SECONDARY}; font-size: 9pt; "
            f"font-weight: bold; letter-spacing: 2px; background: transparent;")
        cl.addWidget(actions_label)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(16)

        cards = [
            ("new", "\U0001F4C4", "New Project",
             "Create a blank controller configuration"),
            ("open", "\U0001F4C2", "Open Project",
             "Open an existing .apcproj file"),
            ("import", "\U0001F4E5", "Import Model",
             "Import a .apcmodel bundle from APC Ident"),
            ("template_heater", "\U0001F525", "Heater Template",
             "Start from a fired heater template"),
            ("template_column", "\U0001F9EA", "Column Template",
             "Start from a distillation column template"),
        ]

        for action_id, icon, title, desc in cards:
            card = ActionCard(action_id, icon, title, desc)
            card.clicked.connect(self.action_triggered.emit)
            actions_row.addWidget(card)

        actions_row.addStretch()
        cl.addLayout(actions_row)

        # ── Recent projects ──
        if self._recent_paths:
            recent_label = QLabel("RECENT PROJECTS")
            recent_label.setStyleSheet(
                f"color: {THEME.TEXT_SECONDARY}; font-size: 9pt; "
                f"font-weight: bold; letter-spacing: 2px; background: transparent;")
            cl.addWidget(recent_label)

            for path in self._recent_paths[:8]:
                if os.path.exists(path):
                    card = RecentProjectCard(path)
                    card.clicked.connect(self.recent_opened.emit)
                    cl.addWidget(card)

        # ── Info section ──
        cl.addSpacing(20)
        info_label = QLabel("ABOUT")
        info_label.setStyleSheet(
            f"color: {THEME.TEXT_SECONDARY}; font-size: 9pt; "
            f"font-weight: bold; letter-spacing: 2px; background: transparent;")
        cl.addWidget(info_label)

        info_text = QLabel(
            "APC Architect is part of the Azeotrope Advanced Process Control stack.\n\n"
            "Workflow: Import identified model → Configure variables & limits → "
            "Tune optimizer (Layer 1 QP, Layer 2 LP, Layer 3 NLP) → "
            "Simulate closed-loop → Deploy via OPC UA\n\n"
            "Features: DMC3-style what-if simulator, 3-layer optimization, "
            "Python calculation scripts, OPC UA deployment runtime, "
            "process templates, recipe management."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet(
            f"color: {THEME.TEXT_SECONDARY}; font-size: 10pt; "
            f"line-height: 1.5; background: transparent;")
        cl.addWidget(info_text)

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def update_recent(self, paths: List[str]):
        """Rebuild with updated recent paths."""
        self._recent_paths = paths
        # Clear and rebuild (simple approach)
        layout = self.layout()
        if layout:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        self._build()
