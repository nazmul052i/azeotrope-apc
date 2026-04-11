"""Results tab -- inspect the identified model and export a bundle.

Layout:

  ┌─────────────────────────┬──────────────────────────────────────┐
  │ STEP RESPONSE MATRIX    │ GAIN MATRIX                          │
  │ (StepResponseGrid)      │ (table, copyable)                    │
  │                         ├──────────────────────────────────────┤
  │                         │ CHANNEL FITS                         │
  │                         │ (R^2 / RMSE / Ljung-Box per channel) │
  │                         ├──────────────────────────────────────┤
  │                         │ [Export Model Bundle...]             │
  │                         │ Bundle path : ...                    │
  └─────────────────────────┴──────────────────────────────────────┘
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from azeoapc.identification import (
    BUNDLE_EXT, ModelBundle, bundle_from_ident, save_model_bundle,
)

from ..session import IdentSession
from ..theme import SILVER
from ..widgets import StepResponseGrid


class ResultsTab(QWidget):
    config_changed = Signal()
    bundle_exported = Signal(str)    # path

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._build()
        self._refresh_from_session()

    # ==================================================================
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_grid_panel())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([900, 400])
        root.addWidget(splitter)

    # ------------------------------------------------------------------
    def _build_grid_panel(self):
        box = QGroupBox("STEP RESPONSE MATRIX")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 18, 8, 8)
        self.grid = StepResponseGrid()
        lay.addWidget(self.grid)
        return box

    # ------------------------------------------------------------------
    def _build_side_panel(self):
        side = QWidget()
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        gain_box = QGroupBox("GAIN MATRIX")
        gl = QVBoxLayout(gain_box)
        gl.setContentsMargins(8, 18, 8, 8)
        self.gain_table = QTableWidget()
        self.gain_table.verticalHeader().setVisible(True)
        self.gain_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.gain_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        gl.addWidget(self.gain_table)
        lay.addWidget(gain_box, 1)

        fit_box = QGroupBox("CHANNEL FITS")
        fl = QVBoxLayout(fit_box)
        fl.setContentsMargins(8, 18, 8, 8)
        self.fit_table = QTableWidget()
        self.fit_table.setColumnCount(4)
        self.fit_table.setHorizontalHeaderLabels(
            ["CV", "R\u00b2", "RMSE", "LB-p"])
        self.fit_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.fit_table.verticalHeader().setVisible(False)
        fl.addWidget(self.fit_table)
        lay.addWidget(fit_box, 1)

        export_box = QGroupBox("EXPORT")
        el = QVBoxLayout(export_box)
        el.setContentsMargins(8, 18, 8, 8)

        self.export_btn = QPushButton("Export Model Bundle...")
        self.export_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_green']};"
            f" color: #1A1A2A; font-weight: 700; padding: 10px;"
            f" border-radius: 4px; }}"
            f"QPushButton:hover {{ background: #5BE8A0; }}"
            f"QPushButton:disabled {{ background: {SILVER['bg_secondary']};"
            f" color: {SILVER['text_muted']}; }}")
        self.export_btn.clicked.connect(self._on_export)
        el.addWidget(self.export_btn)

        self.bundle_label = QLabel("(not exported)")
        self.bundle_label.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 9pt;")
        self.bundle_label.setWordWrap(True)
        el.addWidget(self.bundle_label)

        lay.addWidget(export_box)
        return side

    # ==================================================================
    # Population
    # ==================================================================
    def _refresh_from_session(self):
        result = self.session.ident_result
        if result is None:
            self.grid.clear_plots()
            self.grid.set_status("No model loaded -- run identification first")
            self.gain_table.setRowCount(0)
            self.gain_table.setColumnCount(0)
            self.fit_table.setRowCount(0)
            self.export_btn.setEnabled(False)
            self._update_bundle_label()
            return

        mv_tags, cv_tags = self._get_tag_lists()
        self.grid.plot_result(
            result, mv_tags, cv_tags, dt=result.config.dt)
        self._populate_gain_table(result, mv_tags, cv_tags)
        self._populate_fit_table(result, cv_tags)
        self.export_btn.setEnabled(True)
        self._update_bundle_label()

    # ------------------------------------------------------------------
    def _get_tag_lists(self):
        """Return (mv_tags, cv_tags) using controller_tag if set, else column."""
        mv_tags = []
        cv_tags = []
        for ta in self.session.project.tag_assignments:
            if ta.role == "MV":
                mv_tags.append(ta.controller_tag or ta.column)
            elif ta.role == "CV":
                cv_tags.append(ta.controller_tag or ta.column)
        return mv_tags, cv_tags

    # ------------------------------------------------------------------
    def _populate_gain_table(self, result, mv_tags, cv_tags):
        gain = result.gain_matrix()
        ny, nu = gain.shape
        self.gain_table.setRowCount(ny)
        self.gain_table.setColumnCount(nu)
        self.gain_table.setHorizontalHeaderLabels(mv_tags or [f"MV{j}" for j in range(nu)])
        self.gain_table.setVerticalHeaderLabels(cv_tags or [f"CV{i}" for i in range(ny)])
        for i in range(ny):
            for j in range(nu):
                item = QTableWidgetItem(f"{gain[i,j]:+.4g}")
                item.setTextAlignment(Qt.AlignCenter)
                # Colour cells by gain sign for quick scanning
                if gain[i, j] > 0:
                    item.setForeground(QColor(SILVER["accent_green"]))
                elif gain[i, j] < 0:
                    item.setForeground(QColor(SILVER["accent_orange"]))
                self.gain_table.setItem(i, j, item)

    def _populate_fit_table(self, result, cv_tags):
        # ChannelFit holds one entry per (CV,MV) but the R^2/RMSE/Ljung-Box
        # are computed per CV (the model is per CV, not per channel pair).
        # Show one row per CV by deduping.
        seen = {}
        for f in result.fits:
            seen.setdefault(f.cv_index, f)
        rows = sorted(seen.values(), key=lambda f: f.cv_index)
        self.fit_table.setRowCount(len(rows))
        for r, f in enumerate(rows):
            cv_name = (cv_tags[f.cv_index]
                       if f.cv_index < len(cv_tags) else f"CV{f.cv_index}")
            cells = [
                cv_name,
                f"{f.r_squared:+.4f}",
                f"{f.rmse:.4g}",
                f"{f.ljung_box_pvalue:.3f}",
            ]
            for c, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignCenter)
                if c == 1:    # R^2 colouring
                    if f.r_squared > 0.9:
                        item.setForeground(QColor(SILVER["accent_green"]))
                    elif f.r_squared > 0.7:
                        item.setForeground(QColor(SILVER["accent_orange"]))
                    else:
                        item.setForeground(QColor(SILVER["accent_red"]))
                if c == 3:    # Ljung-Box: white residuals if p > 0.05
                    if f.ljung_box_pvalue > 0.05:
                        item.setForeground(QColor(SILVER["accent_green"]))
                    else:
                        item.setForeground(QColor(SILVER["accent_orange"]))
                self.fit_table.setItem(r, c, item)

    # ==================================================================
    # Export bundle
    # ==================================================================
    def _on_export(self):
        result = self.session.ident_result
        if result is None:
            return
        mv_tags, cv_tags = self._get_tag_lists()

        # Default save location: project dir if known, else cwd
        suggested_dir = (
            os.path.dirname(self.session.project.source_path)
            if self.session.project.source_path
            else os.getcwd())
        suggested_name = (
            (self.session.project.metadata.name or "untitled")
            .lower().replace(" ", "_") + BUNDLE_EXT)
        suggested = os.path.join(suggested_dir, suggested_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Model Bundle", suggested,
            f"APC Model Bundle (*{BUNDLE_EXT});;All Files (*)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += BUNDLE_EXT

        # The model was identified on data with these means -- the
        # bundle's "operating point" is the mean of the training data
        # so the consumer (apc_architect) builds its plant with the
        # correct deviation reference. Without this, u0/y0 default to
        # zero and the controller treats every engineering-unit input
        # as a 100 BPH "deviation" from zero.
        u0 = None
        y0 = None
        if self.session.cond_result is not None:
            try:
                u0 = self.session.cond_result.u_train.mean(axis=0)
                y0 = self.session.cond_result.y_train.mean(axis=0)
            except Exception:
                u0 = y0 = None

        try:
            bundle = bundle_from_ident(
                result,
                name=self.session.project.metadata.name or "Untitled",
                mv_tags=mv_tags,
                cv_tags=cv_tags,
                u0=u0,
                y0=y0,
                source_csv=os.path.basename(self.session.df_path)
                            if self.session.df_path else "",
                source_project=os.path.basename(self.session.project.source_path)
                                if self.session.project.source_path else "",
            )
            save_model_bundle(bundle, path)
        except Exception as e:
            QMessageBox.critical(
                self, "Export Bundle",
                f"Failed to export bundle:\n{type(e).__name__}: {e}")
            return

        self.session.bundle = bundle
        self.session.project.last_bundle_path = (
            os.path.relpath(path,
                             os.path.dirname(self.session.project.source_path))
            if self.session.project.source_path else path)
        self._update_bundle_label()
        self.bundle_exported.emit(path)
        self.config_changed.emit()
        QMessageBox.information(
            self, "Export Bundle",
            f"Bundle exported successfully:\n{path}")

    def _update_bundle_label(self):
        bundle_path = self.session.project.last_bundle_path
        if bundle_path:
            self.bundle_label.setText(f"Last export: {bundle_path}")
            self.bundle_label.setStyleSheet(
                f"color: {SILVER['accent_green']}; font-size: 9pt;")
        else:
            self.bundle_label.setText("(not exported)")
            self.bundle_label.setStyleSheet(
                f"color: {SILVER['text_muted']}; font-size: 9pt;")

    # ==================================================================
    def on_ident_completed(self, result):
        self._refresh_from_session()

    def on_project_loaded(self):
        self._refresh_from_session()
