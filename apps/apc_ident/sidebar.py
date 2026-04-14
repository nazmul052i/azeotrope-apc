"""Sidebar navigation with workflow steps and expandable data file tree.

When files are loaded, they appear as child nodes under the Data step.
"""
from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget,
)

from azeoapc.theme.ident_theme import THEME, WORKFLOW_STEPS

_BG = THEME.BG_SIDEBAR
_BG_HOVER = THEME.BG_SIDEBAR_HOVER
_BG_ACTIVE = THEME.BG_SIDEBAR_ACTIVE
_TEXT = THEME.TEXT_ON_SIDEBAR
_TEXT_ACTIVE = THEME.TEXT_ON_SIDEBAR_ACTIVE
_DONE = THEME.STEP_DONE
_CURRENT = THEME.STEP_CURRENT
_PENDING = THEME.STEP_PENDING


# ---------------------------------------------------------------------------
# Sub-item (file node under a step)
# ---------------------------------------------------------------------------
class SidebarFileItem(QFrame):
    """A child node showing a loaded file under a workflow step."""

    clicked = Signal(str)           # file path
    remove_requested = Signal(str)  # file path
    export_requested = Signal(str)  # file path
    reveal_requested = Signal(str)  # file path
    rename_requested = Signal(str)  # file path

    def __init__(self, filename: str, filepath: str, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.filename = filename
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
            "QMenu { background: #EBECF1; color: #1A1C24; "
            "border: 1px solid #9AA5B4; }"
            "QMenu::item { padding: 5px 24px 5px 12px; }"
            "QMenu::item:selected { background: #2B5EA7; color: white; }"
            "QMenu::separator { height: 1px; background: #C8CDD8; margin: 4px 8px; }")

        act = menu.addAction(f"\U0001F4C4  {self.filename}")
        act.setEnabled(False)  # header, not clickable
        menu.addSeparator()

        menu.addAction("Rename...").triggered.connect(
            lambda: self.rename_requested.emit(self.filepath))
        menu.addSeparator()
        menu.addAction("Remove from project").triggered.connect(
            lambda: self.remove_requested.emit(self.filepath))
        menu.addAction("Export data to CSV...").triggered.connect(
            lambda: self.export_requested.emit(self.filepath))
        menu.addAction("Reveal in file manager").triggered.connect(
            lambda: self.reveal_requested.emit(self.filepath))

        menu.exec(event.globalPos())


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------
class SidebarStep(QFrame):
    """One clickable workflow step."""

    clicked = Signal(str)
    context_requested = Signal(str, object)

    def __init__(self, step_def: dict, parent=None):
        super().__init__(parent)
        self.step_id = step_def["id"]
        self._icon = step_def["icon"]
        self._label = step_def["label"]
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
            bg, text_color, fw = _BG_ACTIVE, _TEXT_ACTIVE, "bold"
            border = f"border-left: 3px solid {THEME.ACCENT_HOVER};"
        else:
            bg, text_color, fw = _BG, _TEXT, "normal"
            border = "border-left: 3px solid transparent;"

        self.setStyleSheet(f"SidebarStep {{ background-color: {bg}; {border} }}")
        self.dot.setStyleSheet(f"color: {dot_color}; background: transparent; font-size: 8pt;")
        self.icon_label.setStyleSheet(f"color: {text_color}; background: transparent; font-size: 13pt;")
        self.text_label.setStyleSheet(
            f"color: {text_color}; background: transparent; "
            f"font-size: 10pt; font-weight: {fw};")

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


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
class Sidebar(QFrame):
    """Vertical sidebar with branding, workflow steps, and file tree."""

    step_clicked = Signal(str)
    context_requested = Signal(str, object)
    file_clicked = Signal(str)            # file path
    file_remove_requested = Signal(str)   # file path
    file_export_requested = Signal(str)   # file path
    file_reveal_requested = Signal(str)   # file path
    file_rename_requested = Signal(str)   # file path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AppSidebar")
        self.setFixedWidth(200)
        self.setAutoFillBackground(True)

        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(_BG))
        self.setPalette(pal)
        self.setStyleSheet(
            f"#AppSidebar {{ background-color: {_BG}; "
            f"border-right: 1px solid {THEME.CHROME_DARK}; }}")

        self._steps: List[SidebarStep] = []
        self._step_containers: dict = {}  # step_id -> QVBoxLayout for children
        self._file_items: List[SidebarFileItem] = []
        self._current_step = ""
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
        title = QLabel("APC IDENT")
        title.setStyleSheet(
            f"color: {_TEXT_ACTIVE}; background: transparent; "
            f"font-size: 14pt; font-weight: bold; letter-spacing: 2px;")
        bl.addWidget(title)
        sub = QLabel("Model Identification Studio")
        sub.setStyleSheet(f"color: {_TEXT}; background: transparent; font-size: 7pt;")
        bl.addWidget(sub)
        lay.addWidget(brand)

        # Workflow label
        wf = QLabel("  WORKFLOW")
        wf.setFixedHeight(30)
        wf.setStyleSheet(
            f"color: {_PENDING}; background-color: {_BG}; "
            f"font-size: 7pt; font-weight: bold; letter-spacing: 2px; padding-top: 10px;")
        lay.addWidget(wf)

        # Steps + child containers
        for step_def in WORKFLOW_STEPS:
            step = SidebarStep(step_def)
            step.clicked.connect(self._on_step_clicked)
            step.context_requested.connect(self.context_requested.emit)
            self._steps.append(step)
            lay.addWidget(step)

            # Child container (for file items, etc.)
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
        self._current_step = step_id
        ids = [s["id"] for s in WORKFLOW_STEPS]
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

    # ── File tree management ──
    def add_file(self, step_id: str, filepath: str):
        """Add a file node under a workflow step."""
        if step_id not in self._step_containers:
            return

        container, layout = self._step_containers[step_id]
        filename = os.path.basename(filepath)

        # Don't add duplicates
        for item in self._file_items:
            if item.filepath == filepath:
                return

        item = SidebarFileItem(filename, filepath)
        item.clicked.connect(self.file_clicked.emit)
        item.remove_requested.connect(self.file_remove_requested.emit)
        item.rename_requested.connect(self.file_rename_requested.emit)
        item.export_requested.connect(self.file_export_requested.emit)
        item.reveal_requested.connect(self.file_reveal_requested.emit)
        self._file_items.append(item)
        layout.addWidget(item)
        container.setVisible(True)

    def clear_files(self, step_id: str):
        """Remove all file nodes from a step."""
        if step_id not in self._step_containers:
            return
        container, layout = self._step_containers[step_id]
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                self._file_items = [
                    f for f in self._file_items if f is not child.widget()]
                child.widget().deleteLater()
        container.setVisible(False)

    def set_file(self, step_id: str, filepath: str):
        """Set a single file for a step (clear existing, add new)."""
        self.clear_files(step_id)
        if filepath:
            self.add_file(step_id, filepath)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(_BG))
        painter.end()
        super().paintEvent(event)
