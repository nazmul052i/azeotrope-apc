"""Sidebar navigation for APC Architect -- matches the ident app style.

Workflow steps for controller configuration and deployment:
  Configure → Optimize → Calculate → Simulate → Deploy
"""
from __future__ import annotations

import os
from typing import Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget,
)

from azeoapc.theme.ident_theme import THEME

_BG = THEME.BG_SIDEBAR
_BG_HOVER = THEME.BG_SIDEBAR_HOVER
_BG_ACTIVE = THEME.BG_SIDEBAR_ACTIVE
_TEXT = THEME.TEXT_ON_SIDEBAR
_TEXT_ACTIVE = THEME.TEXT_ON_SIDEBAR_ACTIVE
_DONE = THEME.STEP_DONE
_CURRENT = THEME.STEP_CURRENT
_PENDING = THEME.STEP_PENDING

ARCHITECT_STEPS = [
    {"id": "config",    "icon": "\u2630", "label": "Configure",
     "tip": "Variables, limits, feedback filters, subcontrollers"},
    {"id": "optimize",  "icon": "\u2699", "label": "Optimize",
     "tip": "Layer 1 QP, Layer 2 LP/QP, Layer 3 NLP tuning"},
    {"id": "calculate", "icon": "\u0192", "label": "Calculate",
     "tip": "Pre/post-MPC Python calculation scripts"},
    {"id": "simulate",  "icon": "\u25B6", "label": "Simulate",
     "tip": "Interactive closed-loop what-if simulation"},
    {"id": "deploy",    "icon": "\u26A1", "label": "Deploy",
     "tip": "OPC UA runtime, IO tags, online validation"},
]


class SidebarStep(QFrame):
    clicked = Signal(str)
    context_requested = Signal(str, object)

    def __init__(self, step_def: dict, parent=None):
        super().__init__(parent)
        self.step_id = step_def["id"]
        self._label = step_def["label"]
        self._icon = step_def["icon"]
        self._tip = step_def["tip"]
        self._state = "pending"
        self.setFixedHeight(44)
        self.setToolTip(self._tip)
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(10)

        self.dot = QLabel("\u25CF")
        self.dot.setFixedWidth(14)
        self.dot.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.dot)

        self.icon_label = QLabel(self._icon)
        self.icon_label.setFixedWidth(20)
        self.icon_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon_label)

        self.text_label = QLabel(self._label)
        lay.addWidget(self.text_label, 1)

        self._apply_style()

    def set_state(self, state: str):
        self._state = state
        self._apply_style()

    def _apply_style(self):
        dot_colors = {"done": _DONE, "current": _CURRENT, "pending": _PENDING}
        dot_color = dot_colors.get(self._state, _PENDING)
        if self._state == "current":
            bg, tc, fw = _BG_ACTIVE, _TEXT_ACTIVE, "bold"
            border = f"border-left: 3px solid {THEME.ACCENT_HOVER};"
        else:
            bg, tc, fw = _BG, _TEXT, "normal"
            border = "border-left: 3px solid transparent;"
        self.setStyleSheet(f"SidebarStep {{ background-color: {bg}; {border} }}")
        self.dot.setStyleSheet(f"color: {dot_color}; background: transparent; font-size: 8pt;")
        self.icon_label.setStyleSheet(f"color: {tc}; background: transparent; font-size: 13pt;")
        self.text_label.setStyleSheet(
            f"color: {tc}; background: transparent; font-size: 10pt; font-weight: {fw};")

    def enterEvent(self, event):
        if self._state != "current":
            self.setStyleSheet(
                f"SidebarStep {{ background-color: {_BG_HOVER}; "
                f"border-left: 3px solid transparent; }}")

    def leaveEvent(self, event):
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.step_id)

    def contextMenuEvent(self, event):
        self.context_requested.emit(self.step_id, event.globalPos())


class SidebarFileItem(QFrame):
    clicked = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, filename: str, filepath: str, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(38, 0, 10, 0)
        lay.setSpacing(6)
        icon = QLabel("\U0001F4C4")
        icon.setFixedWidth(14)
        icon.setStyleSheet(f"color: {_TEXT}; background: transparent; font-size: 8pt;")
        lay.addWidget(icon)
        label = QLabel(filename)
        label.setStyleSheet(
            f"color: {_TEXT_ACTIVE}; background: transparent; "
            f"font-size: 8pt; font-style: italic;")
        label.setToolTip(filepath)
        lay.addWidget(label, 1)
        self.setStyleSheet(f"background-color: {_BG};")

    def enterEvent(self, event):
        self.setStyleSheet(f"background-color: {_BG_HOVER};")

    def leaveEvent(self, event):
        self.setStyleSheet(f"background-color: {_BG};")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.filepath)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #EBECF1; color: #1A1C24; border: 1px solid #9AA5B4; }"
            "QMenu::item { padding: 5px 24px 5px 12px; }"
            "QMenu::item:selected { background: #2B5EA7; color: white; }")
        act = menu.addAction("Remove")
        act.triggered.connect(lambda: self.remove_requested.emit(self.filepath))
        menu.exec(event.globalPos())


class ArchitectSidebar(QFrame):
    step_clicked = Signal(str)
    context_requested = Signal(str, object)
    file_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ArchSidebar")
        self.setFixedWidth(200)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(_BG))
        self.setPalette(pal)
        self.setStyleSheet(
            f"#ArchSidebar {{ background-color: {_BG}; "
            f"border-right: 1px solid {THEME.CHROME_DARK}; }}")
        self._steps: List[SidebarStep] = []
        self._step_containers: Dict[str, tuple] = {}
        self._file_items: List[SidebarFileItem] = []
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Branding
        brand = QFrame()
        brand.setFixedHeight(56)
        brand.setStyleSheet(
            f"background-color: {_BG}; border-bottom: 1px solid {_BG_HOVER};")
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(2)
        title = QLabel("APC ARCHITECT")
        title.setStyleSheet(
            f"color: {_TEXT_ACTIVE}; background: transparent; "
            f"font-size: 13pt; font-weight: bold; letter-spacing: 2px;")
        bl.addWidget(title)
        sub = QLabel("Controller Configuration Studio")
        sub.setStyleSheet(f"color: {_TEXT}; background: transparent; font-size: 7pt;")
        bl.addWidget(sub)
        lay.addWidget(brand)

        wf = QLabel("  WORKFLOW")
        wf.setFixedHeight(30)
        wf.setStyleSheet(
            f"color: {_PENDING}; background-color: {_BG}; "
            f"font-size: 7pt; font-weight: bold; letter-spacing: 2px; padding-top: 10px;")
        lay.addWidget(wf)

        for step_def in ARCHITECT_STEPS:
            step = SidebarStep(step_def)
            step.clicked.connect(self._on_step_clicked)
            step.context_requested.connect(self.context_requested.emit)
            self._steps.append(step)
            lay.addWidget(step)

            container = QWidget()
            container.setStyleSheet(f"background-color: {_BG};")
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0)
            container.setVisible(False)
            self._step_containers[step_def["id"]] = (container, cl)
            lay.addWidget(container)

        lay.addStretch()

        ver = QLabel("v0.2.0")
        ver.setAlignment(Qt.AlignCenter)
        ver.setFixedHeight(24)
        ver.setStyleSheet(f"color: {_PENDING}; background: transparent; font-size: 7pt;")
        lay.addWidget(ver)

    def _on_step_clicked(self, step_id: str):
        self.set_current(step_id)
        self.step_clicked.emit(step_id)

    def set_current(self, step_id: str):
        ids = [s["id"] for s in ARCHITECT_STEPS]
        try:
            current_idx = ids.index(step_id)
        except ValueError:
            current_idx = 0
        for i, step in enumerate(self._steps):
            if step.step_id == step_id:
                step.set_state("current")
            elif i < current_idx:
                step.set_state("done")
            else:
                step.set_state("pending")

    def mark_done(self, step_id: str):
        for step in self._steps:
            if step.step_id == step_id and step._state != "current":
                step.set_state("done")

    def add_file(self, step_id: str, filepath: str):
        if step_id not in self._step_containers:
            return
        container, layout = self._step_containers[step_id]
        for item in self._file_items:
            if item.filepath == filepath:
                return
        filename = os.path.basename(filepath)
        item = SidebarFileItem(filename, filepath)
        item.clicked.connect(self.file_clicked.emit)
        self._file_items.append(item)
        layout.addWidget(item)
        container.setVisible(True)

    def set_file(self, step_id: str, filepath: str):
        self.clear_files(step_id)
        if filepath:
            self.add_file(step_id, filepath)

    def clear_files(self, step_id: str):
        if step_id not in self._step_containers:
            return
        container, layout = self._step_containers[step_id]
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                self._file_items = [f for f in self._file_items if f is not child.widget()]
                child.widget().deleteLater()
        container.setVisible(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(_BG))
        painter.end()
        super().paintEvent(event)
