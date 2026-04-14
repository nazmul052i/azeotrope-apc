"""Analysis tab -- cross-correlation, model uncertainty, gain matrix analysis.

Groups the three DMC3 analysis tools into one tab with sub-tabs:

  1. Cross-Correlation  -- MV auto/cross-correlation with quality grading
  2. Model Uncertainty  -- frequency/time domain uncertainty, A/B/C/D grades
  3. Gain Matrix        -- condition number, colinearity, sub-matrix scan, RGA

All analyses run against the current identification result stored in
the session.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget,
)

from azeoapc.identification.cross_correlation import (
    analyze_cross_correlation, CorrelationAnalysis,
)
from azeoapc.identification.model_uncertainty import (
    analyze_uncertainty, UncertaintyReport,
)
from azeoapc.identification.gain_matrix_analysis import (
    analyze_gain_matrix, GainMatrixReport, ScalingMethod,
)

from ..session import IdentSession
from ..theme import SILVER, TRACE_COLORS


class AnalysisTab(QWidget):
    """Analysis tab with sub-tabs for cross-correlation, uncertainty, gain matrix."""

    config_changed = Signal()

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)

        self.sub_tabs = QTabWidget()
        self.sub_tabs.addTab(self._build_xcorr_tab(), "Cross-Correlation")
        self.sub_tabs.addTab(self._build_uncertainty_tab(), "Model Uncertainty")
        self.sub_tabs.addTab(self._build_gainmatrix_tab(), "Gain Matrix")
        root.addWidget(self.sub_tabs)

    # ==================================================================
    # Cross-Correlation sub-tab
    # ==================================================================
    def _build_xcorr_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)

        # Controls
        ctrl = QHBoxLayout()
        self.xcorr_run_btn = QPushButton("Run Cross-Correlation")
        self.xcorr_run_btn.clicked.connect(self._on_run_xcorr)
        self.xcorr_run_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_blue']};"
            f" color: white; font-weight: 600; padding: 8px;"
            f" border-radius: 3px; }}")
        ctrl.addWidget(self.xcorr_run_btn)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        splitter = QSplitter(Qt.Horizontal)

        # Plot area
        self.xcorr_plot = pg.GraphicsLayoutWidget()
        self.xcorr_plot.setBackground(SILVER["plot_bg"])
        splitter.addWidget(self.xcorr_plot)

        # Results text
        self.xcorr_text = QTextEdit()
        self.xcorr_text.setReadOnly(True)
        self.xcorr_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; color: {SILVER['text_primary']};"
            f" font-family: Consolas; font-size: 9pt;")
        self.xcorr_text.setText("Click 'Run Cross-Correlation' to analyze MV signals.")
        splitter.addWidget(self.xcorr_text)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        lay.addWidget(splitter, 1)
        return w

    def _on_run_xcorr(self):
        df = self.session.df
        if df is None:
            QMessageBox.information(self, "Cross-Correlation",
                                     "Load data first.")
            return

        mv_cols = [t.column for t in self.session.project.tag_assignments
                   if t.role == "MV"]
        if len(mv_cols) < 1:
            QMessageBox.information(self, "Cross-Correlation",
                                     "Assign at least one MV in Tags tab.")
            return

        result = analyze_cross_correlation(df, mv_cols, max_lag=100)
        self.xcorr_text.setText(result.summary())

        # Plot auto-correlations
        self.xcorr_plot.clear()
        n_plots = len(result.auto_correlations) + len(result.cross_correlations)
        row = 0

        for name, ac in result.auto_correlations.items():
            p = self.xcorr_plot.addPlot(row=row, col=0, title=f"Auto: {name}")
            p.showGrid(x=True, y=True, alpha=0.15)
            color = TRACE_COLORS[row % len(TRACE_COLORS)]
            p.plot(ac.lags, ac.values, pen=pg.mkPen(color, width=1.5))
            p.addItem(pg.InfiniteLine(
                pos=np.exp(-1), angle=0,
                pen=pg.mkPen(SILVER["accent_orange"], width=1, style=Qt.DashLine)))
            p.addItem(pg.InfiniteLine(
                pos=-np.exp(-1), angle=0,
                pen=pg.mkPen(SILVER["accent_orange"], width=1, style=Qt.DashLine)))
            row += 1

        for (a, b), xc in result.cross_correlations.items():
            p = self.xcorr_plot.addPlot(
                row=row, col=0,
                title=f"Cross: {a} vs {b}  [{xc.grade}]")
            p.showGrid(x=True, y=True, alpha=0.15)

            # Color by grade
            grade_colors = {
                "IDEAL": SILVER["accent_green"],
                "ACCEPTABLE": SILVER["accent_blue"],
                "POOR": SILVER["accent_orange"],
                "UNACCEPTABLE": SILVER["accent_red"],
            }
            color = grade_colors.get(xc.grade, SILVER["text_primary"])
            p.plot(xc.lags, xc.values, pen=pg.mkPen(color, width=1.5))

            # Threshold lines
            for thresh in [0.3, -0.3, 0.5, -0.5]:
                p.addItem(pg.InfiniteLine(
                    pos=thresh, angle=0,
                    pen=pg.mkPen(SILVER["text_muted"], width=1, style=Qt.DotLine)))
            row += 1

    # ==================================================================
    # Model Uncertainty sub-tab
    # ==================================================================
    def _build_uncertainty_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)

        ctrl = QHBoxLayout()
        self.unc_run_btn = QPushButton("Run Uncertainty Analysis")
        self.unc_run_btn.clicked.connect(self._on_run_uncertainty)
        self.unc_run_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_blue']};"
            f" color: white; font-weight: 600; padding: 8px;"
            f" border-radius: 3px; }}")
        ctrl.addWidget(self.unc_run_btn)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        splitter = QSplitter(Qt.Horizontal)

        # Grade matrix table
        right = QVBoxLayout()
        grade_box = QGroupBox("UNCERTAINTY GRADES")
        gl = QVBoxLayout(grade_box)
        self.grade_table = QTableWidget()
        self.grade_table.setStyleSheet(
            f"font-family: Consolas; font-size: 10pt;")
        gl.addWidget(self.grade_table)

        self.unc_text = QTextEdit()
        self.unc_text.setReadOnly(True)
        self.unc_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; font-family: Consolas; font-size: 9pt;")
        self.unc_text.setText("Run identification first, then click 'Run Uncertainty Analysis'.")
        gl.addWidget(self.unc_text)

        right_w = QWidget()
        rl = QVBoxLayout(right_w)
        rl.addWidget(grade_box)
        splitter.addWidget(right_w)

        # Plot area
        self.unc_plot = pg.GraphicsLayoutWidget()
        self.unc_plot.setBackground(SILVER["plot_bg"])
        splitter.addWidget(self.unc_plot)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        lay.addWidget(splitter, 1)
        return w

    def _on_run_uncertainty(self):
        result = self.session.ident_result
        if result is None:
            QMessageBox.information(self, "Uncertainty",
                                     "Run identification first.")
            return

        mv_names, cv_names = self._get_tag_lists()

        # Get step response and confidence bands
        if hasattr(result, 'step') and hasattr(result, 'confidence_lo'):
            # FIR IdentResult
            step = result.step  # list of (ny, nu) matrices
            n = result.n_coeff
            ny, nu = step[0].shape

            step_arr = np.zeros((ny, n, nu))
            ci_lo = np.zeros((ny, n, nu))
            ci_hi = np.zeros((ny, n, nu))

            s_acc = np.zeros_like(step[0])
            lo_acc = np.zeros_like(step[0])
            hi_acc = np.zeros_like(step[0])
            for k in range(n):
                s_acc += step[k]
                lo_acc += result.confidence_lo[k]
                hi_acc += result.confidence_hi[k]
                step_arr[:, k, :] = s_acc
                ci_lo[:, k, :] = lo_acc
                ci_hi[:, k, :] = hi_acc

            residual_std = np.array([ch.rmse for ch in result.fits])
            report = analyze_uncertainty(
                step_arr, ci_lo, ci_hi,
                dt=result.config.dt if hasattr(result, 'config') else 1.0,
                cv_names=cv_names, mv_names=mv_names,
                residual_std=residual_std,
            )
        elif hasattr(result, 'A'):
            # SubspaceResult
            step_list = result.to_step(120)
            ny, nu = step_list[0].shape
            n = len(step_list)
            step_arr = np.zeros((ny, n, nu))
            for k in range(n):
                step_arr[:, k, :] = step_list[k]

            report = analyze_uncertainty(
                step_arr, dt=result.config.dt,
                cv_names=cv_names, mv_names=mv_names,
                residual_std=result.fit_rmse,
            )
        else:
            QMessageBox.warning(self, "Uncertainty",
                                 "Unsupported result type.")
            return

        self.unc_text.setText(report.summary())
        self._populate_grade_table(report)
        self._plot_uncertainty(report)

    def _populate_grade_table(self, report: UncertaintyReport):
        ny, nu = report.ny, report.nu
        self.grade_table.setRowCount(ny)
        self.grade_table.setColumnCount(nu)
        self.grade_table.setHorizontalHeaderLabels(report.mv_names)
        self.grade_table.setVerticalHeaderLabels(report.cv_names)

        grade_colors = {
            "A": SILVER["accent_green"],
            "B": SILVER["accent_blue"],
            "C": SILVER["accent_orange"],
            "D": SILVER["accent_red"],
        }

        gm = report.grade_matrix()
        for i in range(ny):
            for j in range(nu):
                grade = gm[i][j]
                item = QTableWidgetItem(grade)
                item.setTextAlignment(Qt.AlignCenter)
                color = grade_colors.get(grade, SILVER["text_primary"])
                item.setForeground(pg.mkColor(color))
                self.grade_table.setItem(i, j, item)

        self.grade_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def _plot_uncertainty(self, report: UncertaintyReport):
        self.unc_plot.clear()
        for idx, ch in enumerate(report.channels[:8]):
            if ch.step_response is None:
                continue
            p = self.unc_plot.addPlot(
                row=idx, col=0,
                title=f"{ch.cv_name}/{ch.mv_name} [{ch.overall_grade}]")
            p.showGrid(x=True, y=True, alpha=0.15)
            t = np.arange(len(ch.step_response))

            # 2-sigma band
            if ch.step_upper_2s is not None:
                p.addItem(pg.FillBetweenItem(
                    pg.PlotDataItem(t, ch.step_lower_2s, pen=pg.mkPen(None)),
                    pg.PlotDataItem(t, ch.step_upper_2s, pen=pg.mkPen(None)),
                    brush=pg.mkBrush(0, 102, 204, 25),
                ))

            # Step response
            color = TRACE_COLORS[idx % len(TRACE_COLORS)]
            p.plot(t, ch.step_response, pen=pg.mkPen(color, width=2))

    # ==================================================================
    # Gain Matrix sub-tab
    # ==================================================================
    def _build_gainmatrix_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)

        ctrl = QHBoxLayout()
        self.gm_run_btn = QPushButton("Analyze Gain Matrix")
        self.gm_run_btn.clicked.connect(self._on_run_gainmatrix)
        self.gm_run_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_blue']};"
            f" color: white; font-weight: 600; padding: 8px;"
            f" border-radius: 3px; }}")
        ctrl.addWidget(self.gm_run_btn)

        ctrl.addWidget(QLabel("Scaling:"))
        self.gm_scaling = QComboBox()
        self.gm_scaling.addItems(["None", "Typical Moves", "Range"])
        ctrl.addWidget(self.gm_scaling)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        splitter = QSplitter(Qt.Horizontal)

        # Tables
        tables_w = QWidget()
        tl = QVBoxLayout(tables_w)

        gain_box = QGroupBox("GAIN MATRIX")
        gl = QVBoxLayout(gain_box)
        self.gm_gain_table = QTableWidget()
        gl.addWidget(self.gm_gain_table)
        tl.addWidget(gain_box)

        rga_box = QGroupBox("RGA (RELATIVE GAIN ARRAY)")
        rl_box = QVBoxLayout(rga_box)
        self.rga_table = QTableWidget()
        rl_box.addWidget(self.rga_table)
        tl.addWidget(rga_box)

        splitter.addWidget(tables_w)

        # Text results
        self.gm_text = QTextEdit()
        self.gm_text.setReadOnly(True)
        self.gm_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; font-family: Consolas; font-size: 9pt;")
        self.gm_text.setText("Run identification first, then click 'Analyze Gain Matrix'.")
        splitter.addWidget(self.gm_text)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        lay.addWidget(splitter, 1)
        return w

    def _on_run_gainmatrix(self):
        result = self.session.ident_result
        if result is None:
            QMessageBox.information(self, "Gain Matrix",
                                     "Run identification first.")
            return

        mv_names, cv_names = self._get_tag_lists()

        # Extract gain matrix
        if hasattr(result, 'gain_matrix') and callable(result.gain_matrix):
            gain = result.gain_matrix()
        elif hasattr(result, 'gain_matrix'):
            gain = result.gain_matrix
        else:
            QMessageBox.warning(self, "Gain Matrix",
                                 "Cannot extract gain matrix from this result.")
            return

        if isinstance(gain, np.ndarray) and gain.ndim == 2:
            pass
        else:
            gain = np.atleast_2d(gain)

        scaling_map = {
            "None": ScalingMethod.NONE,
            "Typical Moves": ScalingMethod.TYPICAL_MOVES,
            "Range": ScalingMethod.RANGE,
        }
        scaling = scaling_map.get(self.gm_scaling.currentText(), ScalingMethod.NONE)

        report = analyze_gain_matrix(
            gain, cv_names=cv_names, mv_names=mv_names,
            scaling=scaling,
        )

        self.gm_text.setText(report.summary())
        self._populate_gm_tables(report)

    def _populate_gm_tables(self, report: GainMatrixReport):
        G = report.gain_matrix
        ny, nu = G.shape

        # Gain matrix table
        self.gm_gain_table.setRowCount(ny)
        self.gm_gain_table.setColumnCount(nu)
        self.gm_gain_table.setHorizontalHeaderLabels(report.mv_names)
        self.gm_gain_table.setVerticalHeaderLabels(report.cv_names)
        for i in range(ny):
            for j in range(nu):
                val = G[i, j]
                item = QTableWidgetItem(f"{val:+.4g}")
                item.setTextAlignment(Qt.AlignCenter)
                color = SILVER["accent_green"] if val >= 0 else SILVER["accent_orange"]
                item.setForeground(pg.mkColor(color))
                self.gm_gain_table.setItem(i, j, item)
        self.gm_gain_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # RGA table
        if report.rga is not None:
            rga = report.rga
            self.rga_table.setRowCount(rga.shape[0])
            self.rga_table.setColumnCount(rga.shape[1])
            self.rga_table.setHorizontalHeaderLabels(report.mv_names[:rga.shape[1]])
            self.rga_table.setVerticalHeaderLabels(report.cv_names[:rga.shape[0]])
            for i in range(rga.shape[0]):
                for j in range(rga.shape[1]):
                    val = rga[i, j]
                    item = QTableWidgetItem(f"{val:.3f}")
                    item.setTextAlignment(Qt.AlignCenter)
                    # Highlight diagonal elements close to 1 (good pairing)
                    if i == j and 0.5 < val < 2.0:
                        item.setForeground(pg.mkColor(SILVER["accent_green"]))
                    elif abs(val) > 5.0:
                        item.setForeground(pg.mkColor(SILVER["accent_red"]))
                    self.rga_table.setItem(i, j, item)
            self.rga_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        else:
            self.rga_table.setRowCount(0)
            self.rga_table.setColumnCount(0)

    # ==================================================================
    # Helpers
    # ==================================================================
    def _get_tag_lists(self):
        tags = self.session.project.tag_assignments
        mv = [t.controller_tag or t.column for t in tags if t.role == "MV"]
        cv = [t.controller_tag or t.column for t in tags if t.role == "CV"]
        return mv, cv

    # ==================================================================
    # Public hooks
    # ==================================================================
    def on_ident_completed(self, result):
        """Called when identification finishes -- enable analysis buttons."""
        pass

    def on_project_loaded(self):
        self.xcorr_text.setText("Load data and run cross-correlation.")
        self.unc_text.setText("Run identification first.")
        self.gm_text.setText("Run identification first.")
        self.xcorr_plot.clear()
        self.unc_plot.clear()
