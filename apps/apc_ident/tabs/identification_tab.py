"""Identification tab -- configure + run FIR identification.

Layout:

  ┌─────────────────────────┬─────────────────────────────────────┐
  │ IDENTIFICATION CONFIG   │ STATUS                              │
  │  Model length     [60]  │  Conditioning report                │
  │  Sample period  [60.0s] │  ----                               │
  │  Method  [DLS|COR|RIDGE]│  Last identification summary        │
  │  Smoothing [pipeline]   │  Gain matrix                        │
  │  Ridge alpha   [1.000]  │  Channel fits                       │
  │  Detrend       [x]      │                                     │
  │  Prewhiten     [ ]      │                                     │
  │  Remove mean   [x]      │                                     │
  │  Clip sigma    [4.0]    │                                     │
  │  Holdout %     [20]     │                                     │
  │                         │                                     │
  │  [▶  IDENTIFY MODEL]    │                                     │
  │  [████████████████]     │                                     │
  └─────────────────────────┴─────────────────────────────────────┘

The Run button dispatches to a QThread so the GUI stays responsive
on large identifications. Progress is indeterminate (spinner) until
the worker emits ``finished`` carrying an ``IdentResult``.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QProgressBar, QPushButton, QSpinBox, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)

from azeoapc.identification import (
    ConditioningConfig, DataConditioner, FIRIdentifier, IdentConfig,
    IdentMethod, IdentResult, SmoothMethod,
)

from ..session import IdentSession
from ..theme import SILVER


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------
class _IdentWorker(QObject):
    finished = Signal(object)         # IdentResult
    error    = Signal(str)
    progress = Signal(str)

    def __init__(self, u, y, ident_config: IdentConfig):
        super().__init__()
        self.u = u
        self.y = y
        self.ident_config = ident_config

    @Slot()
    def run(self):
        try:
            self.progress.emit("Building regression matrix...")
            ident = FIRIdentifier(self.ident_config)
            self.progress.emit("Solving identification...")
            result = ident.identify(self.u, self.y)
            self.progress.emit("Done")
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Tab body
# ---------------------------------------------------------------------------
class IdentificationTab(QWidget):
    config_changed = Signal()
    ident_completed = Signal(object)   # IdentResult

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._thread: Optional[QThread] = None
        self._worker: Optional[_IdentWorker] = None
        self._build()
        self._refresh_from_session()

    # ==================================================================
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_config_panel())
        splitter.addWidget(self._build_status_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([380, 800])
        root.addWidget(splitter)

    # ------------------------------------------------------------------
    def _build_config_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        box = QGroupBox("IDENTIFICATION CONFIG")
        form = QFormLayout(box)
        form.setSpacing(6)

        self.spin_n = QSpinBox()
        self.spin_n.setRange(5, 500)
        self.spin_n.setValue(60)
        self.spin_n.valueChanged.connect(self._on_field_changed)
        form.addRow("Model Length (n_coeff)", self.spin_n)

        self.spin_dt = QDoubleSpinBox()
        self.spin_dt.setRange(0.1, 86400.0)
        self.spin_dt.setValue(60.0)
        self.spin_dt.setSuffix(" s")
        self.spin_dt.setDecimals(2)
        self.spin_dt.valueChanged.connect(self._on_field_changed)
        form.addRow("Sample Period", self.spin_dt)

        self.combo_method = QComboBox()
        self.combo_method.addItems(["dls", "cor", "ridge"])
        self.combo_method.setToolTip(
            "DLS  - Direct Least Squares (open-loop tests)\n"
            "COR  - Correlation method (closed-loop tolerant)\n"
            "Ridge - L2-regularised LS (collinear inputs)"
        )
        self.combo_method.currentTextChanged.connect(self._on_field_changed)
        form.addRow("Method", self.combo_method)

        self.combo_smooth = QComboBox()
        self.combo_smooth.addItems(
            ["pipeline", "exponential", "savgol", "asymptotic", "none"])
        self.combo_smooth.currentTextChanged.connect(self._on_field_changed)
        form.addRow("Smoothing", self.combo_smooth)

        self.spin_alpha = QDoubleSpinBox()
        self.spin_alpha.setRange(0.001, 10000.0)
        self.spin_alpha.setValue(1.0)
        self.spin_alpha.setDecimals(3)
        self.spin_alpha.valueChanged.connect(self._on_field_changed)
        form.addRow("Ridge \u03b1", self.spin_alpha)

        self.chk_detrend = QCheckBox()
        self.chk_detrend.setChecked(True)
        self.chk_detrend.toggled.connect(self._on_field_changed)
        form.addRow("Detrend", self.chk_detrend)

        self.chk_remove_mean = QCheckBox()
        self.chk_remove_mean.setChecked(True)
        self.chk_remove_mean.toggled.connect(self._on_field_changed)
        form.addRow("Remove Mean", self.chk_remove_mean)

        self.chk_prewhiten = QCheckBox()
        self.chk_prewhiten.toggled.connect(self._on_field_changed)
        form.addRow("Prewhiten (\u0394)", self.chk_prewhiten)

        lay.addWidget(box)

        cond_box = QGroupBox("DATA CONDITIONING")
        cf = QFormLayout(cond_box)
        cf.setSpacing(6)

        self.spin_clip = QDoubleSpinBox()
        self.spin_clip.setRange(0.0, 20.0)
        self.spin_clip.setValue(4.0)
        self.spin_clip.setDecimals(1)
        self.spin_clip.setSuffix(" \u03c3")
        self.spin_clip.valueChanged.connect(self._on_field_changed)
        cf.addRow("Outlier Clip", self.spin_clip)

        self.spin_holdout = QDoubleSpinBox()
        self.spin_holdout.setRange(0.0, 0.5)
        self.spin_holdout.setValue(0.2)
        self.spin_holdout.setSingleStep(0.05)
        self.spin_holdout.setDecimals(2)
        self.spin_holdout.valueChanged.connect(self._on_field_changed)
        cf.addRow("Hold-out Fraction", self.spin_holdout)

        lay.addWidget(cond_box)

        self.run_btn = QPushButton("\u25B6  IDENTIFY MODEL")
        self.run_btn.clicked.connect(self._on_run)
        self.run_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_blue']};"
            f" color: white; font-weight: 700; font-size: 11pt;"
            f" padding: 12px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: #5CB0FF; }}"
            f"QPushButton:disabled {{ background: {SILVER['bg_secondary']};"
            f" color: {SILVER['text_muted']}; }}")
        lay.addWidget(self.run_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 9pt;")
        self.status_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.status_label)

        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    def _build_status_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        cond_box = QGroupBox("CONDITIONING REPORT")
        cl = QVBoxLayout(cond_box)
        self.cond_text = QTextEdit()
        self.cond_text.setReadOnly(True)
        self.cond_text.setMaximumHeight(160)
        self.cond_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; color: {SILVER['text_primary']};"
            f" font-family: Consolas; font-size: 9pt;")
        self.cond_text.setText("(no run yet)")
        cl.addWidget(self.cond_text)
        lay.addWidget(cond_box)

        ident_box = QGroupBox("LAST IDENTIFICATION")
        il = QVBoxLayout(ident_box)
        self.ident_text = QTextEdit()
        self.ident_text.setReadOnly(True)
        self.ident_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; color: {SILVER['text_primary']};"
            f" font-family: Consolas; font-size: 9pt;")
        self.ident_text.setText("(no run yet)")
        il.addWidget(self.ident_text)
        lay.addWidget(ident_box, 1)

        return w

    # ==================================================================
    # Field <-> project sync
    # ==================================================================
    def _refresh_from_session(self):
        c = self.session.project.ident
        self._block_all(True)
        self.spin_n.setValue(c.n_coeff)
        self.spin_dt.setValue(c.dt)
        self.combo_method.setCurrentText(c.method.value)
        self.combo_smooth.setCurrentText(c.smooth.value)
        self.spin_alpha.setValue(c.ridge_alpha)
        self.chk_detrend.setChecked(c.detrend)
        self.chk_remove_mean.setChecked(c.remove_mean)
        self.chk_prewhiten.setChecked(c.prewhiten)
        self.spin_clip.setValue(self.session.project.conditioning.clip_sigma)
        self.spin_holdout.setValue(
            self.session.project.conditioning.holdout_fraction)
        self._block_all(False)

    def _block_all(self, b: bool):
        for w in [self.spin_n, self.spin_dt, self.combo_method,
                  self.combo_smooth, self.spin_alpha, self.chk_detrend,
                  self.chk_remove_mean, self.chk_prewhiten, self.spin_clip,
                  self.spin_holdout]:
            w.blockSignals(b)

    def _on_field_changed(self, *_):
        c = self.session.project.ident
        c.n_coeff = self.spin_n.value()
        c.dt = self.spin_dt.value()
        c.method = IdentMethod(self.combo_method.currentText())
        c.smooth = SmoothMethod(self.combo_smooth.currentText())
        c.ridge_alpha = self.spin_alpha.value()
        c.detrend = self.chk_detrend.isChecked()
        c.remove_mean = self.chk_remove_mean.isChecked()
        c.prewhiten = self.chk_prewhiten.isChecked()
        cond = self.session.project.conditioning
        cond.clip_sigma = self.spin_clip.value()
        cond.holdout_fraction = self.spin_holdout.value()
        self.config_changed.emit()

    # ==================================================================
    # Run
    # ==================================================================
    def _on_run(self):
        if self.session.df is None:
            QMessageBox.information(
                self, "Identify",
                "Load a CSV in the Data tab first.")
            return
        mv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "MV"]
        cv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "CV"]
        if not mv_cols or not cv_cols:
            QMessageBox.information(
                self, "Identify",
                "Assign at least one MV and one CV in the Tags tab.")
            return

        # Condition the data first (synchronous; usually < 100 ms)
        try:
            cond_result = DataConditioner().run(
                self.session.df, mv_cols, cv_cols,
                segments=self.session.project.segments or None,
                config=self.session.project.conditioning,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Conditioning",
                f"Conditioning failed:\n{type(e).__name__}: {e}")
            return

        n_train = cond_result.u_train.shape[0]
        n_min = self.session.project.ident.n_coeff + 10
        if n_train < n_min:
            QMessageBox.warning(
                self, "Insufficient Data",
                f"Only {n_train} training samples after conditioning,\n"
                f"need at least {n_min} for n_coeff="
                f"{self.session.project.ident.n_coeff}.\n\n"
                f"Reduce model length, lower the holdout fraction,\n"
                f"or load more data.")
            return

        self.session.cond_result = cond_result
        self.cond_text.setText(cond_result.report.summary())

        # Hand off to the worker thread
        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Identifying...")

        self._thread = QThread()
        self._worker = _IdentWorker(
            cond_result.u_train, cond_result.y_train,
            self.session.project.ident,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    @Slot(object)
    def _on_finished(self, result: IdentResult):
        self.session.ident_result = result
        self.session.bundle = None    # invalidate any prior bundle
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        self.status_label.setText("OK")
        self.ident_text.setText(result.summary())
        self.ident_completed.emit(result)
        self.config_changed.emit()

    @Slot(str)
    def _on_error(self, msg: str):
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        self.status_label.setText("Error")
        QMessageBox.critical(self, "Identification failed", msg)

    # ==================================================================
    def on_project_loaded(self):
        self._refresh_from_session()
        self.cond_text.setText("(no run yet)")
        self.ident_text.setText("(no run yet)")
