"""Validation tab -- compare an identified model against test data.

Layout (C5):

  ┌──────────────────────────────────────────────────────────────────┐
  │ Test data: [Hold-out tail v]  [Run]   |  Open R^2: +0.84  /  ... │
  │ ! warning banner (only when MV variance is too low to be useful) │
  ├──────────────────────────────────────────────────────────────────┤
  │ ACTUAL VS PREDICTED                                              │
  │   one stacked panel per CV with linked X axes                    │
  │   (orange = measured, blue = open-loop, green dashed = one-step) │
  ├──────────────────────────────────────────────────────────────────┤
  │ PER-CV METRICS                                                   │
  │   CV  | open R^2 | one-step R^2 | open RMSE | NRMSE | Bias       │
  │   ... per CV row                                                 │
  └──────────────────────────────────────────────────────────────────┘

Three test data sources:
  - "Hold-out tail"     -- session.cond_result.u_holdout/y_holdout
  - "Full training set" -- session.cond_result.u_train/y_train (overfit check)
  - "Load CSV..."       -- pick an external file, condition with current
                           settings, then validate
"""
from __future__ import annotations

import os
from typing import List, Optional

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from azeoapc.identification import (
    ConditioningConfig, DataConditioner, DualValidationReport, from_fir,
    validate_model_dual,
)

from ..session import IdentSession
from ..theme import SILVER


# ---------------------------------------------------------------------------
class ValidationTab(QWidget):
    config_changed = Signal()

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._last_report: Optional[DualValidationReport] = None
        # Cached test arrays for the current source selection
        self._u_test: Optional[np.ndarray] = None
        self._y_test: Optional[np.ndarray] = None
        self._test_label: str = ""
        self._build()
        self._refresh_from_session()

    # ==================================================================
    # UI construction
    # ==================================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Top bar ──
        bar = QHBoxLayout()
        bar.setSpacing(6)

        bar.addWidget(QLabel("Test data:"))

        self.source_combo = QComboBox()
        self.source_combo.addItems([
            "Hold-out tail",
            "Full training set",
            "Load CSV...",
        ])
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        bar.addWidget(self.source_combo)

        self.run_btn = QPushButton("Run Validation")
        self.run_btn.clicked.connect(self._on_run)
        bar.addWidget(self.run_btn)

        self.status_label = QLabel("(no validation run yet)")
        self.status_label.setStyleSheet(
            f"color: {SILVER['text_muted']}; padding-left: 10px;")
        bar.addWidget(self.status_label, 1)

        self.r2_banner = QLabel("")
        self.r2_banner.setStyleSheet(
            f"color: {SILVER['text_secondary']}; font-weight: 600;"
            f" padding-right: 10px;")
        bar.addWidget(self.r2_banner)

        root.addLayout(bar)

        # ── Excitation warning banner ──
        self.warning_frame = QFrame()
        self.warning_frame.setStyleSheet(
            f"QFrame {{ background: #4A2A1A; border: 1px solid"
            f" {SILVER['accent_orange']}; border-radius: 3px; padding: 6px; }}")
        wlay = QHBoxLayout(self.warning_frame)
        wlay.setContentsMargins(8, 4, 8, 4)
        warn_icon = QLabel("\u26A0")
        warn_icon.setStyleSheet(
            f"color: {SILVER['accent_orange']}; font-size: 14pt;"
            f" font-weight: bold;")
        wlay.addWidget(warn_icon)
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet(
            f"color: {SILVER['text_primary']}; font-size: 9pt;")
        self.warning_label.setWordWrap(True)
        wlay.addWidget(self.warning_label, 1)
        self.warning_frame.setVisible(False)
        root.addWidget(self.warning_frame)

        # ── Main split: plots / metrics ──
        splitter = QSplitter(Qt.Vertical)

        plot_box = QGroupBox("ACTUAL VS PREDICTED")
        pl = QVBoxLayout(plot_box)
        pl.setContentsMargins(8, 18, 8, 8)
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground(SILVER["plot_bg"])
        pl.addWidget(self.plot_widget)
        splitter.addWidget(plot_box)

        metric_box = QGroupBox("PER-CV METRICS")
        ml = QVBoxLayout(metric_box)
        ml.setContentsMargins(8, 18, 8, 8)
        self.metric_table = QTableWidget()
        self.metric_table.setColumnCount(6)
        self.metric_table.setHorizontalHeaderLabels([
            "CV", "Open R\u00b2", "One-Step R\u00b2",
            "Open RMSE", "NRMSE", "Bias",
        ])
        self.metric_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.metric_table.verticalHeader().setVisible(False)
        ml.addWidget(self.metric_table)
        splitter.addWidget(metric_box)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([550, 200])
        root.addWidget(splitter, 1)

    # ==================================================================
    # Test-data selection
    # ==================================================================
    def _on_source_changed(self, text: str):
        # Clear cached test arrays so the next Run pulls fresh data
        self._u_test = None
        self._y_test = None
        self._last_report = None
        self._refresh_from_session()
        if text == "Load CSV...":
            self._load_external_csv()

    def _load_external_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Test CSV", self._examples_dir(),
            "CSV (*.csv);;Parquet (*.parquet);;All Files (*)")
        if not path:
            self.source_combo.blockSignals(True)
            self.source_combo.setCurrentText("Hold-out tail")
            self.source_combo.blockSignals(False)
            return
        try:
            df = self._read_dataframe(path)
        except Exception as e:
            QMessageBox.critical(self, "Load CSV", f"Failed to load:\n{e}")
            return

        # Reuse the project's tag bindings + conditioning settings
        mv_cols = self.session.project.mv_columns()
        cv_cols = self.session.project.cv_columns()
        if not mv_cols or not cv_cols:
            QMessageBox.warning(
                self, "Load CSV",
                "Assign tags in the Tags tab first; the external CSV "
                "will be conditioned with those bindings.")
            return
        missing = [c for c in mv_cols + cv_cols if c not in df.columns]
        if missing:
            QMessageBox.critical(
                self, "Load CSV",
                f"External CSV is missing required columns:\n{missing}\n\n"
                f"Columns in file: {list(df.columns)}")
            return

        try:
            cond = DataConditioner().run(
                df, mv_cols, cv_cols,
                config=ConditioningConfig(
                    clip_sigma=self.session.project.conditioning.clip_sigma,
                    holdout_fraction=0.0,
                ),
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Conditioning", f"Failed to condition test data:\n{e}")
            return

        self._u_test = cond.u_train
        self._y_test = cond.y_train
        self._test_label = f"external: {os.path.basename(path)} ({len(self._u_test)} samples)"
        self.status_label.setText(self._test_label)

    @staticmethod
    def _read_dataframe(path: str) -> pd.DataFrame:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path)
        if len(df.columns) > 0:
            first = df.columns[0]
            try:
                df[first] = pd.to_datetime(df[first])
                df = df.set_index(first)
            except (ValueError, TypeError):
                pass
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def _examples_dir(self) -> str:
        ex = os.path.join(os.path.dirname(__file__), "..", "examples")
        return os.path.abspath(ex) if os.path.isdir(ex) else os.getcwd()

    # ------------------------------------------------------------------
    def _select_test_arrays(self):
        """Pull (u_test, y_test, label) for the current source choice."""
        cond = self.session.cond_result
        choice = self.source_combo.currentText()
        if choice == "Hold-out tail":
            if cond is None or cond.u_holdout is None:
                return None, None, None
            return cond.u_holdout, cond.y_holdout, (
                f"hold-out tail ({cond.u_holdout.shape[0]} samples)")
        if choice == "Full training set":
            if cond is None:
                return None, None, None
            return cond.u_train, cond.y_train, (
                f"full training set ({cond.u_train.shape[0]} samples)")
        if choice == "Load CSV...":
            if self._u_test is None:
                return None, None, None
            return self._u_test, self._y_test, self._test_label
        return None, None, None

    # ==================================================================
    def _refresh_from_session(self):
        cond = self.session.cond_result
        result = self.session.ident_result
        ready = result is not None and cond is not None
        self.run_btn.setEnabled(ready)
        if not ready:
            if result is None:
                self.status_label.setText(
                    "Run identification first (Identification tab).")
            else:
                self.status_label.setText("(no conditioning result yet)")
            self.plot_widget.clear()
            self.metric_table.setRowCount(0)
            self.r2_banner.setText("")
            self.warning_frame.setVisible(False)
            return

        # Hold-out tail unavailable -> auto-fall to training set
        if (self.source_combo.currentText() == "Hold-out tail"
                and cond.u_holdout is None):
            self.status_label.setText(
                "No hold-out window in conditioning result -- raise the "
                "holdout fraction or pick a different source.")
            return

        u, y, label = self._select_test_arrays()
        if u is not None:
            self.status_label.setText(label)

    # ==================================================================
    def _on_run(self):
        result = self.session.ident_result
        if result is None:
            return
        u_test, y_test, label = self._select_test_arrays()
        if u_test is None:
            QMessageBox.information(
                self, "Validation",
                "No test data available for the selected source.")
            return

        cv_names = [t.controller_tag or t.column
                    for t in self.session.project.tag_assignments
                    if t.role == "CV"]
        mv_names = [t.controller_tag or t.column
                    for t in self.session.project.tag_assignments
                    if t.role == "MV"]

        # Pick the best model representation:
        # 1. Bundle SS (already quality-controlled at build time)
        # 2. Stable-order ERA from the FIR
        # 3. Pure FIR (no SS at all -> open-loop falls back to FIR convolution)
        cm = None
        if self.session.bundle is not None:
            try:
                cm = self.session.bundle.to_control_model()
            except Exception:
                cm = None
        if cm is None or cm.ss is None:
            cm = self._stable_era_from_ident(result)
        if cm is None or cm.ss is None:
            QMessageBox.warning(
                self, "Validation",
                "Could not build a stable state-space realisation for "
                "open-loop validation. Falling back to one-step only.")
            return

        try:
            dual = validate_model_dual(
                cm, u_test, y_test,
                cv_names=cv_names, mv_names=mv_names)
        except Exception as e:
            QMessageBox.critical(
                self, "Validation",
                f"Validation failed:\n{type(e).__name__}: {e}")
            return

        self._last_report = dual
        self._render_report(dual, dt=result.config.dt, label=label)

    @staticmethod
    def _stable_era_from_ident(result):
        n_coeff = result.n_coeff
        max_order = max(1, (n_coeff - 1) // 2)
        cm_fir = from_fir(result.fir, dt=result.config.dt)
        for order in range(min(12, max_order), 0, -1):
            try:
                cm = cm_fir.to_ss_from_fir(method="era", order=order)
                if cm.is_stable():
                    return cm
            except Exception:
                continue
        return None

    # ==================================================================
    # Rendering
    # ==================================================================
    def _render_report(self, dual: DualValidationReport, dt: float, label: str):
        self.plot_widget.clear()

        ol = dual.open_loop
        os_ = dual.one_step
        ny = ol.y_test.shape[1]

        # Two simulations have different warmup; trim the open-loop
        # arrays to the one-step length so the time axes line up
        # cleanly when overlaid. (We need at least the open-loop arrays
        # so we can plot something even if one-step has fewer samples.)
        n_one = os_.y_test.shape[0]
        n_open = ol.y_test.shape[0]
        n_min = min(n_open, n_one)
        # The one-step arrays start ``os_.n_warmup`` samples after the
        # raw test array; the open-loop arrays start at sample 0. Slice
        # the open-loop tail so its sample 0 aligns with one-step's.
        ol_offset = max(0, n_open - n_min)
        os_offset = max(0, n_one - n_min)

        t = np.arange(n_min) * dt

        plots = []
        for i in range(ny):
            p = self.plot_widget.addPlot(row=i, col=0)
            p.showGrid(x=True, y=True, alpha=0.15)
            ax_color = SILVER["plot_axis"]
            for an in ("left", "bottom"):
                ax = p.getAxis(an)
                ax.setPen(pg.mkPen(ax_color, width=1))
                ax.setTextPen(pg.mkPen(ax_color))
                ax.setStyle(tickFont=QFont("Segoe UI", 8))
            label_i = (ol.metrics[i].cv_name
                        if i < len(ol.metrics) and ol.metrics[i].cv_name
                        else f"CV{i}")
            p.setLabel("left", label_i, color=SILVER["text_secondary"])

            # measured (orange, thick)
            p.plot(t, ol.y_test[ol_offset:ol_offset + n_min, i],
                    pen=pg.mkPen(SILVER["accent_orange"], width=2))
            # open-loop predicted (blue, dashed)
            p.plot(t, ol.y_pred[ol_offset:ol_offset + n_min, i],
                    pen=pg.mkPen(SILVER["accent_blue"], width=1.5,
                                  style=Qt.DashLine))
            # one-step predicted (green, dotted)
            p.plot(t, os_.y_pred[os_offset:os_offset + n_min, i],
                    pen=pg.mkPen(SILVER["accent_green"], width=1.5,
                                  style=Qt.DotLine))

            if i > 0:
                p.setXLink(plots[0])
            plots.append(p)

        # Per-CV metric table -- both R^2 columns side by side
        rows = max(len(ol.metrics), len(os_.metrics))
        self.metric_table.setRowCount(rows)
        for r in range(rows):
            ol_m = ol.metrics[r] if r < len(ol.metrics) else None
            os_m = os_.metrics[r] if r < len(os_.metrics) else None
            name = (ol_m.cv_name if ol_m and ol_m.cv_name
                    else os_m.cv_name if os_m and os_m.cv_name
                    else f"CV{r}")
            cells = [
                name,
                self._fmt_r2(ol_m.r_squared if ol_m else None),
                self._fmt_r2(os_m.r_squared if os_m else None),
                self._fmt_num(ol_m.rmse if ol_m else None),
                self._fmt_num(ol_m.nrmse if ol_m else None, fmt="{:.4f}"),
                self._fmt_num(ol_m.bias if ol_m else None, fmt="{:+.4g}"),
            ]
            for c, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignCenter)
                if c == 1 and ol_m is not None:
                    item.setForeground(QColor(self._r2_color(ol_m.r_squared)))
                if c == 2 and os_m is not None:
                    item.setForeground(QColor(self._r2_color(os_m.r_squared)))
                self.metric_table.setItem(r, c, item)

        # Banner -- show both numbers
        ol_r2 = ol.overall_r2
        os_r2 = os_.overall_r2
        self.r2_banner.setText(
            f"Open-loop R\u00b2: {ol_r2:+.4f}   |   "
            f"One-step R\u00b2: {os_r2:+.4f}")
        self.r2_banner.setStyleSheet(
            f"color: {self._r2_color(ol_r2)};"
            f" font-weight: 700; padding-right: 10px;")

        self.status_label.setText(f"validated on {label}, mode=ss+fir")

        # Excitation warning
        self._update_excitation_warning(dual)

    def _update_excitation_warning(self, dual: DualValidationReport):
        if dual.is_window_excited:
            self.warning_frame.setVisible(False)
            return
        # All MVs sat still -- the metrics are dominated by noise
        quiet = [d for d in dual.excitation if not d.is_excited]
        names = ", ".join(d.mv_name for d in quiet)
        self.warning_label.setText(
            f"<b>Test window has minimal MV movement.</b> All MVs "
            f"({names}) have a relative standard deviation below 0.5%, "
            f"so the validation metrics are dominated by measurement "
            f"noise rather than model fit. Consider raising the holdout "
            f"fraction or carving a different segment that contains "
            f"actual step changes.")
        self.warning_frame.setVisible(True)

    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_r2(val):
        if val is None or not np.isfinite(val):
            return "FAIL" if val is not None else "-"
        return f"{val:+.4f}"

    @staticmethod
    def _fmt_num(val, fmt="{:.4g}"):
        if val is None or not np.isfinite(val):
            return "FAIL" if val is not None else "-"
        return fmt.format(val)

    @staticmethod
    def _r2_color(r2):
        if not np.isfinite(r2):
            return SILVER["accent_red"]
        if r2 > 0.9:
            return SILVER["accent_green"]
        if r2 > 0.7:
            return SILVER["accent_orange"]
        return SILVER["accent_red"]

    # ==================================================================
    def on_tab_activated(self):
        self._refresh_from_session()
        if (self.session.ident_result is not None
                and self.session.cond_result is not None
                and self._last_report is None):
            # Auto-run on first activation
            self._on_run()

    def on_ident_completed(self, result):
        self._last_report = None
        self._u_test = None
        self._y_test = None
        self._refresh_from_session()

    def on_project_loaded(self):
        self._last_report = None
        self._u_test = None
        self._y_test = None
        self._refresh_from_session()
