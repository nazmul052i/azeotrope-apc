"""Tags tab -- bind CSV columns to controller variable roles.

Each row of the column table is one CSV column from the loaded
DataFrame. Two editable cells:
  * Role     -- combo: Ignore / MV / CV / DV
  * Tag      -- the controller variable tag (e.g. "FIC-101.SP")

Auto-Assign sets the first half of the columns as MV, the rest as
CV, and pre-fills the controller-tag column with the same name as
the CSV column. The user can edit any cell. The MV/CV/DV count is
shown live so the user knows when they have enough to identify.

Stat columns (mean / std / NaN%) come from the loaded DataFrame and
update whenever the Data tab loads new data.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from azeoapc.identification import TagAssignment

from ..session import IdentSession
from ..theme import SILVER


_ROLES = ["Ignore", "MV", "CV", "DV"]


class TagsTab(QWidget):
    config_changed = Signal()

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._combos: List[QComboBox] = []
        self._build()
        self._refresh_from_session()

    # ==================================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Top bar
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.auto_btn = QPushButton("Auto-Assign")
        self.auto_btn.setToolTip(
            "First half of columns as MV, second half as CV "
            "(controller_tag = csv column)")
        self.auto_btn.clicked.connect(self._on_auto_assign)
        bar.addWidget(self.auto_btn)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._on_clear_all)
        bar.addWidget(self.clear_btn)

        bar.addStretch()

        self.summary = QLabel("MV: 0  |  CV: 0  |  DV: 0")
        self.summary.setStyleSheet(
            f"color: {SILVER['text_secondary']}; font-weight: 600;"
            f" padding-right: 8px;")
        bar.addWidget(self.summary)

        root.addLayout(bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "CSV Column", "Role", "Controller Tag", "Mean", "Std", "NaN %",
        ])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table, 1)

        self.hint = QLabel(
            "Load a CSV in the Data tab to populate this table.")
        self.hint.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 9pt;"
            f" padding: 6px;")
        self.hint.setAlignment(Qt.AlignCenter)
        root.addWidget(self.hint)

    # ==================================================================
    def refresh_from_data(self):
        """Called when the Data tab loads a new DataFrame."""
        df = self.session.df
        if df is None:
            self._refresh_from_session()
            return

        # Build the union of CSV columns + already-saved tag assignments,
        # preserving the order from the dataframe.
        existing = {t.column: t for t in self.session.project.tag_assignments}
        new_assignments: List[TagAssignment] = []
        for col in df.columns:
            if col in existing:
                new_assignments.append(existing[col])
            else:
                new_assignments.append(TagAssignment(column=col))
        self.session.project.tag_assignments = new_assignments
        self._refresh_from_session()

    # ------------------------------------------------------------------
    def _refresh_from_session(self):
        df = self.session.df
        assigns = self.session.project.tag_assignments

        self.table.blockSignals(True)
        # Drop any leftover combos so they get recreated on row count change
        self._combos.clear()
        self.table.setRowCount(len(assigns))

        for r, ta in enumerate(assigns):
            self._set_text(r, 0, ta.column, editable=False, bold=True)

            combo = QComboBox()
            combo.addItems(_ROLES)
            combo.setCurrentText(ta.role)
            combo.currentTextChanged.connect(
                lambda new, row=r: self._on_role_changed(row, new))
            self.table.setCellWidget(r, 1, combo)
            self._combos.append(combo)

            self._set_text(r, 2, ta.controller_tag, editable=True)

            if df is not None and ta.column in df.columns:
                series = pd.to_numeric(df[ta.column], errors="coerce")
                mean = f"{series.mean():.4g}" if series.notna().any() else "-"
                std  = f"{series.std():.4g}"  if series.notna().any() else "-"
                nan_pct = f"{series.isna().mean() * 100:.1f}%"
            else:
                mean = std = nan_pct = "-"
            self._set_text(r, 3, mean, editable=False, align_center=True)
            self._set_text(r, 4, std,  editable=False, align_center=True)
            self._set_text(r, 5, nan_pct, editable=False, align_center=True)

        self.table.blockSignals(False)

        if df is None:
            self.hint.show()
        else:
            self.hint.hide()

        self._update_summary()

    def _set_text(self, row, col, text, *, editable=True, bold=False,
                   align_center=False):
        item = QTableWidgetItem(text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        if bold:
            f = item.font(); f.setBold(True); item.setFont(f)
        if align_center:
            item.setTextAlignment(Qt.AlignCenter)
        if not editable and col == 0:
            item.setBackground(QColor(SILVER["bg_panel"]))
        self.table.setItem(row, col, item)

    # ------------------------------------------------------------------
    def _on_role_changed(self, row: int, new_role: str):
        if 0 <= row < len(self.session.project.tag_assignments):
            self.session.project.tag_assignments[row].role = new_role
            # When the user picks a real role and the tag column is
            # empty, default to the CSV column name (sensible).
            ta = self.session.project.tag_assignments[row]
            if new_role != "Ignore" and not ta.controller_tag:
                ta.controller_tag = ta.column
                self.table.blockSignals(True)
                self._set_text(row, 2, ta.column, editable=True)
                self.table.blockSignals(False)
            self._update_summary()
            self.config_changed.emit()

    def _on_item_changed(self, item: QTableWidgetItem):
        r = item.row()
        c = item.column()
        if c != 2:   # only the controller-tag column is editable through cells
            return
        if 0 <= r < len(self.session.project.tag_assignments):
            self.session.project.tag_assignments[r].controller_tag = item.text().strip()
            self.config_changed.emit()

    # ------------------------------------------------------------------
    def _on_auto_assign(self):
        df = self.session.df
        if df is None:
            return
        cols = list(df.columns)
        n = len(cols)
        n_mv = max(1, n // 2)
        new_assignments = []
        for i, col in enumerate(cols):
            role = "MV" if i < n_mv else "CV"
            new_assignments.append(TagAssignment(
                column=col, role=role, controller_tag=col))
        self.session.project.tag_assignments = new_assignments
        self._refresh_from_session()
        self.config_changed.emit()

    def _on_clear_all(self):
        for ta in self.session.project.tag_assignments:
            ta.role = "Ignore"
            ta.controller_tag = ""
        self._refresh_from_session()
        self.config_changed.emit()

    # ------------------------------------------------------------------
    def _update_summary(self):
        n_mv = sum(1 for t in self.session.project.tag_assignments
                    if t.role == "MV")
        n_cv = sum(1 for t in self.session.project.tag_assignments
                    if t.role == "CV")
        n_dv = sum(1 for t in self.session.project.tag_assignments
                    if t.role == "DV")
        ok = n_mv >= 1 and n_cv >= 1
        color = SILVER["accent_green"] if ok else SILVER["accent_orange"]
        self.summary.setText(f"MV: {n_mv}  |  CV: {n_cv}  |  DV: {n_dv}")
        self.summary.setStyleSheet(
            f"color: {color}; font-weight: 600; padding-right: 8px;")

    def on_project_loaded(self):
        self._refresh_from_session()
