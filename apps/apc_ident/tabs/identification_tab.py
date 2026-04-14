"""Identification tab -- configure + run FIR / Subspace identification.

Now includes:
- FIR identification (DLS/COR/Ridge) with smoothing
- Subspace identification (N4SID/MOESP/CVA) with expert mode
- Multi-trial: run multiple parameter sets, compare side-by-side
- Ramp/Pseudoramp CV type selection per CV
- Calculated vectors (formula editor)
- Data conditioning config

Layout:

  ┌──────────────────────────────┬─────────────────────────────────────┐
  │ METHOD  [FIR ▼] [Subspace ▼]│ STATUS                              │
  │                              │  Conditioning report                │
  │ ─── FIR CONFIG ───           │  ────                               │
  │  Model length     [60]       │  Last identification summary        │
  │  Sample period  [60.0s]      │  Gain matrix                        │
  │  Method  [DLS|COR|RIDGE]     │  Channel fits                       │
  │  Smoothing [pipeline]        │                                     │
  │  Ridge alpha   [1.000]       │                                     │
  │                              │                                     │
  │ ─── SUBSPACE CONFIG ───      │                                     │
  │  Method [N4SID|MOESP|CVA]    │                                     │
  │  Model order  [auto / 4]     │                                     │
  │  Future horizon [20]         │                                     │
  │  Expert: diff, oversample    │                                     │
  │                              │                                     │
  │ ─── PREPROCESSING ───        │                                     │
  │  Detrend [x]  Mean [x]       │                                     │
  │  Clip sigma [4.0]            │                                     │
  │  Holdout [0.2]               │                                     │
  │                              │                                     │
  │ ─── CV TYPES ───             │                                     │
  │  CV1: [Normal ▼]             │                                     │
  │  CV2: [Ramp ▼]               │                                     │
  │                              │                                     │
  │ ─── MULTI-TRIAL ───          │                                     │
  │  [x] Run multiple trials     │                                     │
  │  Vary: n_coeff [40,60,80]    │                                     │
  │                              │                                     │
  │  [▶  IDENTIFY]               │                                     │
  └──────────────────────────────┴─────────────────────────────────────┘
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from azeoapc.identification import (
    ConditioningConfig, DataConditioner, FIRIdentifier, IdentConfig,
    IdentMethod, IdentResult, SmoothMethod,
    SubspaceIdentifier, SubspaceConfig, SubspaceMethod, SubspaceResult,
)
from azeoapc.identification.ramp_cv import (
    CVType, preprocess_cv, ramp_to_step,
)
from azeoapc.identification.multi_trial import (
    define_trials, run_trials_fir, select_best_trial,
)
from azeoapc.identification.calculated_vectors import (
    CalculatedTag, add_calculated_tags,
)
from azeoapc.identification.smart_config import smart_configure

from ..session import IdentSession
from ..theme import SILVER, TRACE_COLORS


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------
class _FIRWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, u, y, config: IdentConfig):
        super().__init__()
        self.u, self.y, self.config = u, y, config

    @Slot()
    def run(self):
        try:
            self.progress.emit("Building regression matrix...")
            ident = FIRIdentifier(self.config)
            self.progress.emit("Solving FIR identification...")
            result = ident.identify(self.u, self.y)
            self.progress.emit("Done")
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")


class _SubspaceWorker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, u, y, config: SubspaceConfig):
        super().__init__()
        self.u, self.y, self.config = u, y, config

    @Slot()
    def run(self):
        try:
            self.progress.emit("Building Hankel matrices...")
            ident = SubspaceIdentifier(self.config)
            self.progress.emit("Running subspace identification...")
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
    ident_completed = Signal(object)   # IdentResult or SubspaceResult

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._thread: Optional[QThread] = None
        self._worker = None
        self._build()
        self._refresh_from_session()

    # ==================================================================
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: config panel (scrollable) ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {SILVER['bg_primary']}; }}")
        config_widget = self._build_config_panel()
        scroll.setWidget(config_widget)
        splitter.addWidget(scroll)

        # ── Right: status panel ──
        splitter.addWidget(self._build_status_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([420, 780])
        root.addWidget(splitter)

    # ------------------------------------------------------------------
    def _build_config_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        # ── Smart Config + Method selector ──
        method_box = QGroupBox("IDENTIFICATION METHOD")
        ml = QVBoxLayout(method_box)

        smart_row = QHBoxLayout()
        self.smart_btn = QPushButton("\u26A1 Smart Config")
        self.smart_btn.setToolTip(
            "Analyze data and auto-set all identification parameters.\n"
            "Detects: sample period, settling time, integrators,\n"
            "excitation quality, input correlation, data quality.")
        self.smart_btn.clicked.connect(self._on_smart_config)
        self.smart_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_orange']};"
            f" color: white; font-weight: 700; padding: 8px;"
            f" border-radius: 4px; font-size: 10pt; }}"
            f"QPushButton:hover {{ background: #E8A040; }}")
        smart_row.addWidget(self.smart_btn)
        ml.addLayout(smart_row)

        engine_row = QHBoxLayout()
        self.combo_engine = QComboBox()
        self.combo_engine.addItems(["FIR", "Subspace"])
        self.combo_engine.currentTextChanged.connect(self._on_engine_changed)
        engine_row.addWidget(QLabel("Engine:"))
        engine_row.addWidget(self.combo_engine, 1)
        ml.addLayout(engine_row)
        lay.addWidget(method_box)

        # ── Stacked config: FIR / Subspace ──
        self.config_tabs = QTabWidget()
        self.config_tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {SILVER['border']}; }}")

        self.config_tabs.addTab(self._build_fir_config(), "FIR Config")
        self.config_tabs.addTab(self._build_subspace_config(), "Subspace Config")
        lay.addWidget(self.config_tabs)

        # ── Preprocessing ──
        pre_box = QGroupBox("PREPROCESSING")
        pf = QFormLayout(pre_box)
        pf.setSpacing(4)

        self.chk_detrend = QCheckBox()
        self.chk_detrend.setChecked(True)
        self.chk_detrend.toggled.connect(self._on_field_changed)
        pf.addRow("Detrend", self.chk_detrend)

        self.chk_remove_mean = QCheckBox()
        self.chk_remove_mean.setChecked(True)
        self.chk_remove_mean.toggled.connect(self._on_field_changed)
        pf.addRow("Remove Mean", self.chk_remove_mean)

        self.chk_prewhiten = QCheckBox()
        self.chk_prewhiten.toggled.connect(self._on_field_changed)
        pf.addRow("Prewhiten (\u0394)", self.chk_prewhiten)

        self.spin_clip = QDoubleSpinBox()
        self.spin_clip.setRange(0.0, 20.0)
        self.spin_clip.setValue(4.0)
        self.spin_clip.setDecimals(1)
        self.spin_clip.setSuffix(" \u03c3")
        self.spin_clip.valueChanged.connect(self._on_field_changed)
        pf.addRow("Outlier Clip", self.spin_clip)

        self.spin_holdout = QDoubleSpinBox()
        self.spin_holdout.setRange(0.0, 0.5)
        self.spin_holdout.setValue(0.2)
        self.spin_holdout.setSingleStep(0.05)
        self.spin_holdout.setDecimals(2)
        self.spin_holdout.valueChanged.connect(self._on_field_changed)
        pf.addRow("Hold-out Fraction", self.spin_holdout)

        lay.addWidget(pre_box)

        # ── CV Types (ramp/pseudoramp) ──
        cv_box = QGroupBox("CV TYPES")
        self.cv_type_layout = QFormLayout(cv_box)
        self.cv_type_layout.setSpacing(4)
        self.cv_type_combos: List[QComboBox] = []
        # Populated dynamically when data is loaded
        self._cv_type_placeholder = QLabel("(assign CVs in Tags tab first)")
        self._cv_type_placeholder.setStyleSheet(f"color: {SILVER['text_muted']};")
        self.cv_type_layout.addRow(self._cv_type_placeholder)
        lay.addWidget(cv_box)

        # ── Calculated Vectors ──
        calc_box = QGroupBox("CALCULATED VECTORS")
        cl = QVBoxLayout(calc_box)
        cl.setSpacing(4)
        calc_hint = QLabel("Add derived variables (e.g. {TI101} - {TI102})")
        calc_hint.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 8pt;")
        cl.addWidget(calc_hint)

        self.calc_name = QLineEdit()
        self.calc_name.setPlaceholderText("Name (e.g. Delta_T)")
        cl.addWidget(self.calc_name)

        self.calc_expr = QLineEdit()
        self.calc_expr.setPlaceholderText("Expression (e.g. {TI101} - {TI102})")
        cl.addWidget(self.calc_expr)

        calc_btn_row = QHBoxLayout()
        self.calc_add_btn = QPushButton("+ Add")
        self.calc_add_btn.clicked.connect(self._on_add_calc_vector)
        calc_btn_row.addWidget(self.calc_add_btn)

        self.calc_list_label = QLabel("0 calculated vectors")
        self.calc_list_label.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 8pt;")
        calc_btn_row.addWidget(self.calc_list_label, 1)
        cl.addLayout(calc_btn_row)
        lay.addWidget(calc_box)

        # ── Multi-Trial ──
        trial_box = QGroupBox("MULTI-TRIAL")
        tl = QVBoxLayout(trial_box)
        tl.setSpacing(4)

        self.chk_multi_trial = QCheckBox("Run multiple parameter sets")
        tl.addWidget(self.chk_multi_trial)

        vary_row = QHBoxLayout()
        vary_row.addWidget(QLabel("Vary n_coeff:"))
        self.trial_values = QLineEdit("40, 60, 80, 120")
        self.trial_values.setPlaceholderText("comma-separated values")
        vary_row.addWidget(self.trial_values, 1)
        tl.addLayout(vary_row)

        lay.addWidget(trial_box)

        # ── Run button ──
        self.run_btn = QPushButton("\u25B6  IDENTIFY")
        self.run_btn.clicked.connect(self._on_run)
        self.run_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_blue']};"
            f" color: white; font-weight: 700; font-size: 11pt;"
            f" padding: 10px; border-radius: 4px; }}"
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
    def _build_fir_config(self):
        w = QWidget()
        form = QFormLayout(w)
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

        return w

    # ------------------------------------------------------------------
    def _build_subspace_config(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setSpacing(6)

        self.combo_ss_method = QComboBox()
        self.combo_ss_method.addItems(["n4sid", "moesp", "cva"])
        self.combo_ss_method.setToolTip(
            "N4SID - Numerical subspace (Van Overschee & De Moor)\n"
            "MOESP - Multivariable Output-Error State Space\n"
            "CVA   - Canonical Variate Analysis (Larimore)")
        form.addRow("Algorithm", self.combo_ss_method)

        self.spin_ss_dt = QDoubleSpinBox()
        self.spin_ss_dt.setRange(0.1, 86400.0)
        self.spin_ss_dt.setValue(60.0)
        self.spin_ss_dt.setSuffix(" s")
        self.spin_ss_dt.setDecimals(2)
        form.addRow("Sample Period", self.spin_ss_dt)

        self.chk_auto_order = QCheckBox("Auto")
        self.chk_auto_order.setChecked(True)
        self.chk_auto_order.toggled.connect(self._on_auto_order_toggled)
        self.spin_nx = QSpinBox()
        self.spin_nx.setRange(1, 50)
        self.spin_nx.setValue(4)
        self.spin_nx.setEnabled(False)
        nx_row = QHBoxLayout()
        nx_row.addWidget(self.chk_auto_order)
        nx_row.addWidget(self.spin_nx)
        form.addRow("Model Order (nx)", nx_row)

        self.spin_nx_max = QSpinBox()
        self.spin_nx_max.setRange(2, 50)
        self.spin_nx_max.setValue(20)
        form.addRow("Max Order", self.spin_nx_max)

        self.spin_f = QSpinBox()
        self.spin_f.setRange(2, 200)
        self.spin_f.setValue(20)
        form.addRow("Future Horizon (f)", self.spin_f)

        self.chk_force_stable = QCheckBox()
        form.addRow("Force Stability", self.chk_force_stable)

        self.chk_zero_d = QCheckBox()
        form.addRow("Force D = 0", self.chk_zero_d)

        # Expert mode
        sep = QLabel("─── Expert Mode ───")
        sep.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 8pt;")
        sep.setAlignment(Qt.AlignCenter)
        form.addRow(sep)

        self.chk_differencing = QCheckBox()
        form.addRow("Differencing", self.chk_differencing)

        self.chk_double_diff = QCheckBox()
        form.addRow("Double Diff", self.chk_double_diff)

        self.spin_oversample = QSpinBox()
        self.spin_oversample.setRange(1, 20)
        self.spin_oversample.setValue(1)
        form.addRow("Oversampling Ratio", self.spin_oversample)

        return w

    # ------------------------------------------------------------------
    def _build_status_panel(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # ── Live Preview (mini step response plot) ──
        preview_box = QGroupBox("LIVE PREVIEW")
        pl = QVBoxLayout(preview_box)
        pl.setContentsMargins(4, 14, 4, 4)

        self.preview_plot = pg.PlotWidget()
        self.preview_plot.setBackground(SILVER["plot_bg"])
        self.preview_plot.setMaximumHeight(200)
        self.preview_plot.showGrid(x=True, y=True, alpha=0.15)
        self.preview_plot.setLabel("left", "Step Response")
        self.preview_plot.setLabel("bottom", "Coefficient")
        for an in ("left", "bottom"):
            ax = self.preview_plot.getAxis(an)
            ax.setPen(pg.mkPen(SILVER["plot_axis"], width=1))
            ax.setStyle(tickFont=QFont("Segoe UI", 8))
        self.preview_plot.addItem(pg.InfiniteLine(
            pos=0, angle=0,
            pen=pg.mkPen(SILVER["text_muted"], width=1, style=Qt.DashLine)))

        self._preview_hint = QLabel(
            "Change n_coeff or smoothing to see live preview")
        self._preview_hint.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 8pt;")
        self._preview_hint.setAlignment(Qt.AlignCenter)

        pl.addWidget(self.preview_plot)
        pl.addWidget(self._preview_hint)
        lay.addWidget(preview_box)

        # Timer for debounced live preview
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)  # 300ms debounce
        self._preview_timer.timeout.connect(self._update_live_preview)

        # ── Conditioning report ──
        cond_box = QGroupBox("CONDITIONING REPORT")
        cl = QVBoxLayout(cond_box)
        cl.setContentsMargins(4, 14, 4, 4)
        self.cond_text = QTextEdit()
        self.cond_text.setReadOnly(True)
        self.cond_text.setMaximumHeight(120)
        self.cond_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; color: {SILVER['text_primary']};"
            f" font-family: Consolas; font-size: 9pt;")
        self.cond_text.setText("(no run yet)")
        cl.addWidget(self.cond_text)
        lay.addWidget(cond_box)

        # ── Identification result ──
        ident_box = QGroupBox("IDENTIFICATION RESULT")
        il = QVBoxLayout(ident_box)
        il.setContentsMargins(4, 14, 4, 4)
        self.ident_text = QTextEdit()
        self.ident_text.setReadOnly(True)
        self.ident_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; color: {SILVER['text_primary']};"
            f" font-family: Consolas; font-size: 9pt;")
        self.ident_text.setText("(no run yet)")
        il.addWidget(self.ident_text)
        lay.addWidget(ident_box, 1)

        # ── Scorecard (shown after identification) ──
        self.scorecard_box = QGroupBox("MODEL QUALITY SCORECARD")
        sl = QVBoxLayout(self.scorecard_box)
        sl.setContentsMargins(4, 14, 4, 4)
        self.scorecard_text = QTextEdit()
        self.scorecard_text.setReadOnly(True)
        self.scorecard_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; color: {SILVER['text_primary']};"
            f" font-family: Consolas; font-size: 9pt;")
        sl.addWidget(self.scorecard_text)
        self.scorecard_box.setVisible(False)
        lay.addWidget(self.scorecard_box)

        # ── Multi-trial comparison ──
        self.trial_box = QGroupBox("MULTI-TRIAL COMPARISON")
        tl = QVBoxLayout(self.trial_box)
        tl.setContentsMargins(4, 14, 4, 4)
        self.trial_text = QTextEdit()
        self.trial_text.setReadOnly(True)
        self.trial_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; color: {SILVER['text_primary']};"
            f" font-family: Consolas; font-size: 9pt;")
        tl.addWidget(self.trial_text)
        self.trial_box.setVisible(False)
        lay.addWidget(self.trial_box)

        return w

    # ==================================================================
    # Engine switching
    # ==================================================================
    def _on_engine_changed(self, engine: str):
        idx = 0 if engine == "FIR" else 1
        self.config_tabs.setCurrentIndex(idx)

    def _on_auto_order_toggled(self, checked: bool):
        self.spin_nx.setEnabled(not checked)

    # ==================================================================
    # CV type combos (populated when tags change)
    # ==================================================================
    def refresh_cv_types(self):
        """Rebuild CV type combos from current tag assignments."""
        # Clear existing
        for combo in self.cv_type_combos:
            combo.setParent(None)
            combo.deleteLater()
        self.cv_type_combos.clear()

        # Remove placeholder
        if self._cv_type_placeholder.isVisible():
            self._cv_type_placeholder.setVisible(False)

        # Clear layout
        while self.cv_type_layout.count():
            item = self.cv_type_layout.takeAt(0)
            if item.widget() and item.widget() != self._cv_type_placeholder:
                pass  # keep placeholder, remove others

        tags = self.session.project.tag_assignments
        cv_tags = [t for t in tags if t.role == "CV"]

        if not cv_tags:
            self._cv_type_placeholder.setVisible(True)
            self.cv_type_layout.addRow(self._cv_type_placeholder)
            return

        saved_types = self.session.project.cv_types or {}
        type_map = {"none": "Normal", "ramp": "Ramp", "pseudoramp": "Pseudoramp"}

        for t in cv_tags:
            combo = QComboBox()
            combo.addItems(["Normal", "Ramp", "Pseudoramp"])
            combo.setToolTip(
                "Normal: settling process\n"
                "Ramp: pure integrator (first-difference)\n"
                "Pseudoramp: slow integrator (detrend)")
            # Restore saved CV type
            saved = saved_types.get(t.column, "none")
            combo.setCurrentText(type_map.get(saved, "Normal"))
            combo.currentTextChanged.connect(self._on_cv_type_changed)
            self.cv_type_combos.append(combo)
            name = t.controller_tag or t.column
            self.cv_type_layout.addRow(name, combo)

    def _on_cv_type_changed(self, *_):
        """Persist CV type selections to project."""
        tags = self.session.project.tag_assignments
        cv_tags = [t for t in tags if t.role == "CV"]
        reverse_map = {"Normal": "none", "Ramp": "ramp", "Pseudoramp": "pseudoramp"}
        for idx, combo in enumerate(self.cv_type_combos):
            if idx < len(cv_tags):
                col = cv_tags[idx].column
                self.session.project.cv_types[col] = reverse_map.get(
                    combo.currentText(), "none")
        self.config_changed.emit()

    # ==================================================================
    # Calculated vectors
    # ==================================================================
    def _on_add_calc_vector(self):
        name = self.calc_name.text().strip()
        expr = self.calc_expr.text().strip()
        if not name or not expr:
            return

        df = self.session.df
        if df is None:
            QMessageBox.information(self, "Calculated Vector",
                                     "Load data first.")
            return

        tag = CalculatedTag(name=name, expression=expr)
        try:
            df_new = add_calculated_tags(df, [tag])
            self.session.df = df_new
            # Persist to project
            self.session.project.calculated_vectors.append({
                "name": name, "expression": expr, "unit": "",
            })
            self.calc_name.clear()
            self.calc_expr.clear()
            n_calc = len(self.session.project.calculated_vectors)
            self.calc_list_label.setText(
                f"{n_calc} calculated vector(s). Last: {name}")
            self.config_changed.emit()
        except Exception as e:
            QMessageBox.warning(self, "Calculated Vector",
                               f"Expression error:\n{e}")

    # ==================================================================
    # Field sync
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

        # Restore engine type
        engine = self.session.project.ident_engine or "fir"
        self.combo_engine.setCurrentText(engine.upper())

        # Restore subspace config
        sc = self.session.project.subspace_config
        if sc:
            self.combo_ss_method.setCurrentText(sc.get("method", "n4sid"))
            self.spin_ss_dt.setValue(sc.get("dt", c.dt))
            self.chk_auto_order.setChecked(sc.get("auto_order", True))
            self.spin_nx.setValue(sc.get("nx", 4))
            self.spin_nx_max.setValue(sc.get("nx_max", 20))
            self.spin_f.setValue(sc.get("f", 20))
            self.chk_force_stable.setChecked(sc.get("force_stability", False))
            self.chk_zero_d.setChecked(sc.get("force_zero_D", False))
            self.chk_differencing.setChecked(sc.get("differencing", False))
            self.chk_double_diff.setChecked(sc.get("double_diff", False))
            self.spin_oversample.setValue(sc.get("oversampling_ratio", 1))

        self._block_all(False)
        self.refresh_cv_types()

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

        # Persist engine type
        self.session.project.ident_engine = self.combo_engine.currentText().lower()

        # Persist subspace config
        self.session.project.subspace_config = {
            "method": self.combo_ss_method.currentText(),
            "dt": self.spin_ss_dt.value(),
            "auto_order": self.chk_auto_order.isChecked(),
            "nx": self.spin_nx.value(),
            "nx_max": self.spin_nx_max.value(),
            "f": self.spin_f.value(),
            "force_stability": self.chk_force_stable.isChecked(),
            "force_zero_D": self.chk_zero_d.isChecked(),
            "differencing": self.chk_differencing.isChecked(),
            "double_diff": self.chk_double_diff.isChecked(),
            "oversampling_ratio": self.spin_oversample.value(),
        }

        self.config_changed.emit()
        # Trigger debounced live preview
        self._preview_timer.start()

    # ==================================================================
    # Smart Config
    # ==================================================================
    def _on_smart_config(self):
        """Auto-detect all parameters from the loaded data."""
        df = self.session.df
        if df is None:
            QMessageBox.information(self, "Smart Config",
                                     "Load data first (Data tab).")
            return

        mv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "MV"]
        cv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "CV"]
        if not mv_cols or not cv_cols:
            QMessageBox.information(self, "Smart Config",
                                     "Assign MVs and CVs first (Tags tab).")
            return

        report = smart_configure(df, mv_cols, cv_cols)

        # Apply recommendations to the UI
        self._block_all(True)
        self.spin_n.setValue(report.n_coeff)
        self.spin_dt.setValue(report.dt)
        self.combo_method.setCurrentText(report.method)
        self.combo_smooth.setCurrentText(report.smooth)
        self.spin_alpha.setValue(report.ridge_alpha)
        self.chk_detrend.setChecked(report.detrend)
        self.chk_remove_mean.setChecked(report.remove_mean)
        self.chk_prewhiten.setChecked(report.prewhiten)
        self.spin_clip.setValue(report.clip_sigma)
        self.spin_holdout.setValue(report.holdout_fraction)
        self.spin_ss_dt.setValue(report.dt)
        self._block_all(False)

        # Sync to project
        self._on_field_changed()

        # Set CV types
        for idx, combo in enumerate(self.cv_type_combos):
            cv_name = cv_cols[idx] if idx < len(cv_cols) else ""
            cv_type = report.cv_types.get(cv_name, "none")
            type_map = {"none": "Normal", "ramp": "Ramp", "pseudoramp": "Pseudoramp"}
            combo.setCurrentText(type_map.get(cv_type, "Normal"))

        # Show report
        self.cond_text.setText(report.summary())
        self._preview_hint.setText(
            f"Smart Config applied: n={report.n_coeff}, dt={report.dt:.0f}s, "
            f"method={report.method}")

    # ==================================================================
    # Live Preview
    # ==================================================================
    def _update_live_preview(self):
        """Run a quick FIR identification and show step response preview."""
        if self.session.cond_result is None:
            return
        if self.combo_engine.currentText() != "FIR":
            return

        u = self.session.cond_result.u_train
        y = self.session.cond_result.y_train
        if u is None or y is None:
            return

        n_coeff = self.spin_n.value()
        if u.shape[0] < n_coeff + 10:
            return

        try:
            cfg = IdentConfig(
                n_coeff=n_coeff,
                dt=self.spin_dt.value(),
                method=IdentMethod(self.combo_method.currentText()),
                smooth=SmoothMethod(self.combo_smooth.currentText()),
                ridge_alpha=self.spin_alpha.value(),
                detrend=self.chk_detrend.isChecked(),
                remove_mean=self.chk_remove_mean.isChecked(),
                prewhiten=self.chk_prewhiten.isChecked(),
            )
            ident = FIRIdentifier(cfg)
            result = ident.identify(u, y)

            # Plot first CV/MV channel as preview
            self.preview_plot.clear()
            self.preview_plot.addItem(pg.InfiniteLine(
                pos=0, angle=0,
                pen=pg.mkPen(SILVER["text_muted"], width=1, style=Qt.DashLine)))

            n = result.n_coeff
            ny, nu = result.step[0].shape
            t = np.arange(n)

            # Show up to 4 channels
            n_show = min(ny * nu, 4)
            ch = 0
            for i in range(ny):
                for j in range(nu):
                    if ch >= n_show:
                        break
                    # Cumulative step
                    curve = np.zeros(n)
                    s = 0.0
                    for k in range(n):
                        s += result.step[k][i, j]
                        curve[k] = s

                    color = TRACE_COLORS[ch % len(TRACE_COLORS)]
                    self.preview_plot.plot(
                        t, curve,
                        pen=pg.mkPen(color, width=1.5))
                    ch += 1
                if ch >= n_show:
                    break

            r2_mean = np.mean([f.r_squared for f in result.fits])
            self._preview_hint.setText(
                f"Preview: n={n_coeff}, mean R\u00b2={r2_mean:.4f}  "
                f"({ny}x{nu} MIMO)")

        except Exception as e:
            self._preview_hint.setText(f"Preview failed: {e}")

    # ==================================================================
    # Scorecard (auto-generated after identification)
    # ==================================================================
    def _show_scorecard(self, result):
        """Build and display model quality scorecard."""
        from azeoapc.identification.quality_scorecard import build_scorecard

        mv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "MV"]
        cv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "CV"]

        scorecard = build_scorecard(
            ident_result=result,
            cond_result=self.session.cond_result,
            df=self.session.df,
            mv_cols=mv_cols,
            cv_cols=cv_cols,
        )
        self.scorecard_text.setText(scorecard.summary())
        self.scorecard_box.setVisible(True)

    # ==================================================================
    # Run identification
    # ==================================================================
    def _on_run(self):
        if self.session.df is None:
            QMessageBox.information(self, "Identify",
                                     "Load a CSV in the Data tab first.")
            return

        mv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "MV"]
        cv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "CV"]
        if not mv_cols or not cv_cols:
            QMessageBox.information(self, "Identify",
                                     "Assign at least one MV and one CV.")
            return

        # Condition data
        try:
            cond_result = DataConditioner().run(
                self.session.df, mv_cols, cv_cols,
                segments=self.session.project.segments or None,
                config=self.session.project.conditioning,
            )
        except Exception as e:
            QMessageBox.critical(self, "Conditioning",
                                 f"Failed:\n{type(e).__name__}: {e}")
            return

        self.session.cond_result = cond_result
        self.cond_text.setText(cond_result.report.summary())

        u_train = cond_result.u_train
        y_train = cond_result.y_train

        # Apply ramp/pseudoramp preprocessing per CV
        for idx, combo in enumerate(self.cv_type_combos):
            if idx >= y_train.shape[1]:
                break
            cv_type_str = combo.currentText().lower()
            if cv_type_str == "ramp":
                result = preprocess_cv(y_train[:, idx], CVType.RAMP)
                y_train[:, idx] = result.y_processed
            elif cv_type_str == "pseudoramp":
                result = preprocess_cv(y_train[:, idx], CVType.PSEUDORAMP)
                y_train[:, idx] = result.y_processed

        engine = self.combo_engine.currentText()

        if engine == "Subspace":
            self._run_subspace(u_train, y_train)
        elif self.chk_multi_trial.isChecked():
            self._run_multi_trial(u_train, y_train)
        else:
            self._run_fir(u_train, y_train)

    def _run_fir(self, u, y):
        n_train = u.shape[0]
        n_min = self.session.project.ident.n_coeff + 10
        if n_train < n_min:
            QMessageBox.warning(self, "Insufficient Data",
                                 f"Only {n_train} samples, need {n_min}.")
            return

        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("FIR identifying...")

        self._thread = QThread()
        self._worker = _FIRWorker(u, y, self.session.project.ident)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_fir_finished)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _run_subspace(self, u, y):
        nx = None if self.chk_auto_order.isChecked() else self.spin_nx.value()
        cfg = SubspaceConfig(
            method=SubspaceMethod(self.combo_ss_method.currentText()),
            nx=nx,
            nx_max=self.spin_nx_max.value(),
            f=self.spin_f.value(),
            dt=self.spin_ss_dt.value(),
            detrend=self.chk_detrend.isChecked(),
            remove_mean=self.chk_remove_mean.isChecked(),
            force_stability=self.chk_force_stable.isChecked(),
            force_zero_D=self.chk_zero_d.isChecked(),
            differencing=self.chk_differencing.isChecked(),
            double_diff=self.chk_double_diff.isChecked(),
            oversampling_ratio=self.spin_oversample.value(),
        )

        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText("Subspace identifying...")

        self._thread = QThread()
        self._worker = _SubspaceWorker(u, y, cfg)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_subspace_finished)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _run_multi_trial(self, u, y):
        """Run FIR with multiple n_coeff values."""
        try:
            values_str = self.trial_values.text()
            n_values = [int(v.strip()) for v in values_str.split(",") if v.strip()]
        except ValueError:
            QMessageBox.warning(self, "Multi-Trial",
                                 "Invalid trial values. Use comma-separated integers.")
            return

        base = {
            "n_coeff": self.spin_n.value(),
            "dt": self.spin_dt.value(),
            "method": self.combo_method.currentText(),
            "smooth": self.combo_smooth.currentText(),
            "ridge_alpha": self.spin_alpha.value(),
            "detrend": self.chk_detrend.isChecked(),
            "remove_mean": self.chk_remove_mean.isChecked(),
            "prewhiten": self.chk_prewhiten.isChecked(),
        }
        trials = define_trials(base, vary={"n_coeff": n_values})

        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status_label.setText(f"Running {len(trials)} trials...")
        # Process events so the UI updates before the sync call
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            comparison = run_trials_fir(u, y, trials)
            self.session.trial_comparison = comparison
            self.trial_box.setVisible(True)
            self.trial_text.setText(comparison.summary())

            best = select_best_trial(comparison)
            if best:
                self.session.ident_result = best.ident_result
                self.session.bundle = None
                self.ident_text.setText(best.ident_result.summary())
                self.ident_completed.emit(best.ident_result)
                self.status_label.setText(
                    f"Best trial: {best.name} (R²={best.mean_r2:.4f})")
            else:
                self.status_label.setText("All trials failed")
        except Exception as e:
            QMessageBox.critical(self, "Multi-Trial",
                                 f"{type(e).__name__}: {e}")
        finally:
            self.run_btn.setEnabled(True)
            self.progress.setVisible(False)
            self.config_changed.emit()

    # ==================================================================
    # Callbacks
    # ==================================================================
    @Slot(object)
    def _on_fir_finished(self, result: IdentResult):
        self.session.ident_result = result
        self.session.trial_comparison = None
        self.session.bundle = None
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        self.status_label.setText("FIR identification complete")
        self.ident_text.setText(result.summary())
        self.trial_box.setVisible(False)
        self._show_scorecard(result)
        self.ident_completed.emit(result)
        self.config_changed.emit()

    @Slot(object)
    def _on_subspace_finished(self, result: SubspaceResult):
        self.session.ident_result = result
        self.session.bundle = None
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)
        self.status_label.setText(
            f"Subspace complete: nx={result.nx}, stable={result.is_stable}")
        self.ident_text.setText(result.summary())
        self.trial_box.setVisible(False)
        self._show_scorecard(result)
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
        self.trial_box.setVisible(False)
        self.scorecard_box.setVisible(False)

        # Restore calculated vectors count
        n_calc = len(self.session.project.calculated_vectors)
        if n_calc > 0:
            self.calc_list_label.setText(f"{n_calc} calculated vector(s)")
        else:
            self.calc_list_label.setText("0 calculated vectors")
