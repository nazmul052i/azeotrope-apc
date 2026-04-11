"""
step_ident_app.py — MIMO FIR Identification Studio

PySide6 / pyqtgraph desktop application for:
  1. Loading process historian CSV data
  2. Assigning tags as MV / CV / Ignore
  3. Automatic data conditioning (interpolation, detrend, outlier removal)
  4. FIR model identification (DLS / COR / Ridge)
  5. Step-response matrix visualisation (MV rows × CV columns)

Requires: fir_ident.py in the same directory or on PYTHONPATH.

Author : Azeotrope Process Control
License: Proprietary
"""
from __future__ import annotations

import logging
import sys
import os
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import (
    Qt, Signal, Slot, QThread, QObject, QSize, QTimer, QMargins
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon, QPalette, QPainter, QPen, QBrush,
    QLinearGradient, QPixmap
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QSplitter, QLabel, QPushButton, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QFormLayout, QProgressBar, QStatusBar,
    QMessageBox, QFrame, QScrollArea, QSizePolicy, QTabWidget,
    QTextEdit, QAbstractItemView
)

# Local import
from fir_ident import (
    FIRIdentifier, IdentConfig, IdentMethod, SmoothMethod, IdentResult
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# ═════════════════════════════════════════════════════════════════════
#  Theme — DeltaV Live Silver inspired
# ═════════════════════════════════════════════════════════════════════

SILVER = {
    "bg_primary":       "#1e1e2e",
    "bg_secondary":     "#252536",
    "bg_panel":         "#2a2a3d",
    "bg_input":         "#1a1a2a",
    "bg_header":        "#32324a",
    "border":           "#3d3d5c",
    "border_accent":    "#5a5a8a",
    "text_primary":     "#e0e0f0",
    "text_secondary":   "#9090b0",
    "text_muted":       "#606080",
    "accent_blue":      "#4a9eff",
    "accent_green":     "#3ddc84",
    "accent_orange":    "#ff9f43",
    "accent_red":       "#ff5252",
    "accent_cyan":      "#00d2ff",
    "accent_purple":    "#b388ff",
    "plot_bg":          "#141422",
    "plot_grid":        "#2a2a40",
    "plot_axis":        "#8080a0",
}

# Distinct colours for step response traces
TRACE_COLORS = [
    "#4a9eff", "#3ddc84", "#ff9f43", "#ff5252",
    "#b388ff", "#00d2ff", "#ffeb3b", "#ff6e9c",
    "#76ff03", "#18ffff", "#ff9100", "#e040fb",
]

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {SILVER['bg_primary']};
    color: {SILVER['text_primary']};
    font-family: 'Segoe UI', 'Roboto', 'SF Pro Display', sans-serif;
    font-size: 13px;
}}
QGroupBox {{
    background-color: {SILVER['bg_panel']};
    border: 1px solid {SILVER['border']};
    border-radius: 6px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
    font-size: 12px;
    color: {SILVER['text_secondary']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: {SILVER['accent_blue']};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QPushButton {{
    background-color: {SILVER['bg_header']};
    border: 1px solid {SILVER['border']};
    border-radius: 4px;
    padding: 7px 18px;
    color: {SILVER['text_primary']};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {SILVER['border_accent']};
    border-color: {SILVER['accent_blue']};
}}
QPushButton:pressed {{
    background-color: {SILVER['accent_blue']};
}}
QPushButton#btn_identify {{
    background-color: {SILVER['accent_blue']};
    color: #ffffff;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 24px;
    border: none;
    border-radius: 5px;
}}
QPushButton#btn_identify:hover {{
    background-color: #5cb0ff;
}}
QPushButton#btn_identify:disabled {{
    background-color: {SILVER['border']};
    color: {SILVER['text_muted']};
}}
QComboBox {{
    background-color: {SILVER['bg_input']};
    border: 1px solid {SILVER['border']};
    border-radius: 4px;
    padding: 5px 8px;
    color: {SILVER['text_primary']};
    min-width: 80px;
}}
QComboBox QAbstractItemView {{
    background-color: {SILVER['bg_panel']};
    border: 1px solid {SILVER['border']};
    color: {SILVER['text_primary']};
    selection-background-color: {SILVER['accent_blue']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QSpinBox, QDoubleSpinBox {{
    background-color: {SILVER['bg_input']};
    border: 1px solid {SILVER['border']};
    border-radius: 4px;
    padding: 5px 8px;
    color: {SILVER['text_primary']};
}}
QTableWidget {{
    background-color: {SILVER['bg_secondary']};
    border: 1px solid {SILVER['border']};
    border-radius: 4px;
    gridline-color: {SILVER['border']};
    color: {SILVER['text_primary']};
    selection-background-color: {SILVER['accent_blue']};
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 4px 6px;
}}
QHeaderView::section {{
    background-color: {SILVER['bg_header']};
    color: {SILVER['text_secondary']};
    border: 1px solid {SILVER['border']};
    padding: 5px;
    font-weight: 600;
    font-size: 11px;
}}
QProgressBar {{
    background-color: {SILVER['bg_input']};
    border: 1px solid {SILVER['border']};
    border-radius: 3px;
    text-align: center;
    color: {SILVER['text_primary']};
    height: 18px;
}}
QProgressBar::chunk {{
    background-color: {SILVER['accent_blue']};
    border-radius: 2px;
}}
QStatusBar {{
    background-color: {SILVER['bg_secondary']};
    color: {SILVER['text_secondary']};
    border-top: 1px solid {SILVER['border']};
    font-size: 11px;
}}
QTabWidget::pane {{
    border: 1px solid {SILVER['border']};
    border-radius: 4px;
    background-color: {SILVER['bg_primary']};
}}
QTabBar::tab {{
    background-color: {SILVER['bg_header']};
    color: {SILVER['text_secondary']};
    border: 1px solid {SILVER['border']};
    padding: 6px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background-color: {SILVER['bg_panel']};
    color: {SILVER['accent_blue']};
    border-bottom: 2px solid {SILVER['accent_blue']};
}}
QTextEdit {{
    background-color: {SILVER['bg_input']};
    border: 1px solid {SILVER['border']};
    border-radius: 4px;
    color: {SILVER['text_primary']};
    font-family: 'Cascadia Code', 'Consolas', 'Fira Code', monospace;
    font-size: 11px;
    padding: 6px;
}}
QScrollArea {{
    border: none;
}}
QLabel#lbl_title {{
    font-size: 16px;
    font-weight: 700;
    color: {SILVER['accent_blue']};
    letter-spacing: 1px;
}}
QLabel#lbl_subtitle {{
    font-size: 11px;
    color: {SILVER['text_muted']};
}}
QLabel#lbl_section {{
    font-size: 11px;
    font-weight: 600;
    color: {SILVER['text_secondary']};
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QCheckBox {{
    color: {SILVER['text_primary']};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {SILVER['border']};
    border-radius: 3px;
    background-color: {SILVER['bg_input']};
}}
QCheckBox::indicator:checked {{
    background-color: {SILVER['accent_blue']};
    border-color: {SILVER['accent_blue']};
}}
QSplitter::handle {{
    background-color: {SILVER['border']};
    width: 2px;
}}
"""


# ═════════════════════════════════════════════════════════════════════
#  Tag role assignment
# ═════════════════════════════════════════════════════════════════════
class TagRole(str, Enum):
    IGNORE = "Ignore"
    MV = "MV"
    CV = "CV"
    DV = "DV"


# ═════════════════════════════════════════════════════════════════════
#  Data conditioning engine
# ═════════════════════════════════════════════════════════════════════
class DataConditioner:
    """Pre-process raw historian data for FIR identification."""

    @staticmethod
    def condition(
        df: pd.DataFrame,
        mv_cols: List[str],
        cv_cols: List[str],
        resample_period: Optional[float] = None,
        interpolate: bool = True,
        clip_sigma: float = 4.0,
        fillna_method: str = "ffill",
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        Condition raw data and return (u, y, df_clean).

        Steps:
            1. Select MV/CV columns
            2. Forward-fill NaN (historian compression gaps)
            3. Outlier clipping (> clip_sigma std devs)
            4. Linear interpolation of remaining gaps
            5. Return numpy arrays (N, nu) and (N, ny)
        """
        cols = mv_cols + cv_cols
        df_work = df[cols].copy()

        n_raw = len(df_work)
        n_nan_before = df_work.isna().sum().sum()

        # Forward-fill (historian compression artefact)
        if fillna_method == "ffill":
            df_work = df_work.ffill()
        df_work = df_work.bfill()  # handle leading NaN

        # Outlier clipping per column
        n_clipped = 0
        for col in cols:
            series = df_work[col]
            mu = series.mean()
            sigma = series.std()
            if sigma > 1e-15:
                mask = (series - mu).abs() > clip_sigma * sigma
                n_clip_col = mask.sum()
                if n_clip_col > 0:
                    df_work.loc[mask, col] = np.nan
                    n_clipped += n_clip_col

        # Interpolate clipped values
        if interpolate:
            df_work = df_work.interpolate(method="linear", limit_direction="both")

        # Final NaN safety
        df_work = df_work.fillna(method="ffill").fillna(method="bfill")

        n_nan_after = df_work.isna().sum().sum()

        logger.info(
            "Data conditioning: %d rows, %d NaN filled, %d outliers clipped, %d NaN remaining",
            n_raw, n_nan_before, n_clipped, n_nan_after,
        )

        u = df_work[mv_cols].values.astype(np.float64)
        y = df_work[cv_cols].values.astype(np.float64)

        return u, y, df_work


# ═════════════════════════════════════════════════════════════════════
#  Worker thread for identification
# ═════════════════════════════════════════════════════════════════════
class IdentWorker(QObject):
    finished = Signal(object)    # IdentResult
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, u, y, config):
        super().__init__()
        self.u = u
        self.y = y
        self.config = config

    @Slot()
    def run(self):
        try:
            self.progress.emit("Building regression matrix…")
            ident = FIRIdentifier(self.config)

            self.progress.emit("Solving identification…")
            result = ident.identify(self.u, self.y)

            self.progress.emit("Done")
            self.finished.emit(result)
        except Exception as e:
            logger.exception("Identification failed")
            self.error.emit(str(e))


# ═════════════════════════════════════════════════════════════════════
#  Tag assignment table widget
# ═════════════════════════════════════════════════════════════════════
class TagTable(QTableWidget):
    """Table for assigning CSV columns to MV / CV / DV / Ignore roles."""

    roles_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Tag Name", "Role", "Mean", "Std", "NaN%"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 5):
            self.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._combos: List[QComboBox] = []

    def load_columns(self, df: pd.DataFrame):
        self.setRowCount(0)
        self._combos.clear()
        self.setRowCount(len(df.columns))

        for row, col in enumerate(df.columns):
            # Tag name
            item = QTableWidgetItem(str(col))
            self.setItem(row, 0, item)

            # Role combo
            combo = QComboBox()
            combo.addItems([r.value for r in TagRole])
            combo.setCurrentText(TagRole.IGNORE.value)
            combo.currentTextChanged.connect(lambda _: self.roles_changed.emit())
            self.setCellWidget(row, 1, combo)
            self._combos.append(combo)

            # Stats
            series = pd.to_numeric(df[col], errors="coerce")
            mean_val = f"{series.mean():.4g}" if series.notna().any() else "—"
            std_val = f"{series.std():.4g}" if series.notna().any() else "—"
            nan_pct = f"{series.isna().mean() * 100:.1f}%"

            for ci, val in [(2, mean_val), (3, std_val), (4, nan_pct)]:
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                self.setItem(row, ci, item)

    def get_assignments(self) -> Dict[str, TagRole]:
        result = {}
        for row in range(self.rowCount()):
            tag = self.item(row, 0).text()
            role_text = self._combos[row].currentText()
            result[tag] = TagRole(role_text)
        return result

    def get_mv_cols(self) -> List[str]:
        assigns = self.get_assignments()
        return [k for k, v in assigns.items() if v == TagRole.MV]

    def get_cv_cols(self) -> List[str]:
        assigns = self.get_assignments()
        return [k for k, v in assigns.items() if v == TagRole.CV]

    def auto_assign(self):
        """Heuristic: first half MVs, second half CVs (user can override)."""
        n = self.rowCount()
        if n == 0:
            return
        n_mv = max(1, n // 2)
        for i in range(n):
            if i < n_mv:
                self._combos[i].setCurrentText(TagRole.MV.value)
            else:
                self._combos[i].setCurrentText(TagRole.CV.value)
        self.roles_changed.emit()


# ═════════════════════════════════════════════════════════════════════
#  Step Response Matrix Plot Widget
# ═════════════════════════════════════════════════════════════════════
class StepResponseMatrix(QWidget):
    """
    Grid of pyqtgraph plots: rows = MVs, columns = CVs.
    Each cell shows the step-response S(k) and confidence bands.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)

        # Header
        self._header = QLabel("STEP RESPONSE MATRIX")
        self._header.setObjectName("lbl_section")
        self._header.setAlignment(Qt.AlignCenter)
        self.layout_main.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self.layout_main.addWidget(self._scroll)

        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(2)
        self._scroll.setWidget(self._container)

        self._plots: List[pg.PlotWidget] = []

    def clear_plots(self):
        for pw in self._plots:
            pw.setParent(None)
            pw.deleteLater()
        self._plots.clear()
        # Clear grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def plot_result(
        self,
        result: IdentResult,
        mv_names: List[str],
        cv_names: List[str],
        dt: float,
    ):
        self.clear_plots()
        ny = result.ny
        nu = result.nu
        n = result.n_coeff

        step = result.step
        # Build confidence bands for step response (cumulative sum of FIR CI)
        ci_lo_step = self._cumsum_list(result.confidence_lo)
        ci_hi_step = self._cumsum_list(result.confidence_hi)

        t = np.arange(n) * dt

        # Column headers (CVs) — row 0
        for j in range(nu):
            lbl = QLabel(f"  {mv_names[j] if j < len(mv_names) else f'MV{j}'}")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {SILVER['accent_blue']}; font-weight: 700; "
                f"font-size: 11px; padding: 4px;"
            )
            self._grid.addWidget(lbl, 0, j + 1)

        # Row headers (MVs) — column 0
        for i in range(ny):
            lbl = QLabel(f"{cv_names[i] if i < len(cv_names) else f'CV{i}'}  ")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet(
                f"color: {SILVER['accent_green']}; font-weight: 700; "
                f"font-size: 11px; padding: 4px;"
            )
            self._grid.addWidget(lbl, i + 1, 0)

        # Plot cells
        for i in range(ny):      # CV row
            for j in range(nu):  # MV column
                pw = pg.PlotWidget()
                pw.setBackground(SILVER["plot_bg"])
                pw.setMinimumSize(220, 160)
                pw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

                # Axes styling
                ax_color = SILVER["plot_axis"]
                for axis_name in ("left", "bottom"):
                    ax = pw.getAxis(axis_name)
                    ax.setPen(pg.mkPen(ax_color, width=1))
                    ax.setTextPen(pg.mkPen(ax_color))
                    ax.setStyle(tickFont=QFont("Segoe UI", 8))

                pw.showGrid(x=True, y=True, alpha=0.15)

                # Extract channel data
                s = np.array([step[k][i, j] for k in range(n)])
                lo = np.array([ci_lo_step[k][i, j] for k in range(n)])
                hi = np.array([ci_hi_step[k][i, j] for k in range(n)])

                # Confidence band (fill between)
                color_idx = (i * nu + j) % len(TRACE_COLORS)
                trace_color = QColor(TRACE_COLORS[color_idx])

                fill_color = QColor(trace_color)
                fill_color.setAlpha(30)
                pw.addItem(pg.FillBetweenItem(
                    pg.PlotDataItem(t, lo, pen=pg.mkPen(None)),
                    pg.PlotDataItem(t, hi, pen=pg.mkPen(None)),
                    brush=fill_color,
                ))

                # Step response trace
                pw.plot(
                    t, s,
                    pen=pg.mkPen(trace_color, width=2),
                    antialias=True,
                )

                # Zero line
                pw.addItem(pg.InfiniteLine(
                    pos=0, angle=0,
                    pen=pg.mkPen(SILVER["text_muted"], width=1, style=Qt.DashLine),
                ))

                # Gain annotation
                gain = s[-1] if len(s) > 0 else 0.0
                gain_text = pg.TextItem(
                    f"K={gain:.4g}",
                    color=SILVER["text_secondary"],
                    anchor=(1, 0),
                )
                gain_text.setFont(QFont("Segoe UI", 8))
                gain_text.setPos(t[-1], gain)
                pw.addItem(gain_text)

                self._grid.addWidget(pw, i + 1, j + 1)
                self._plots.append(pw)

        # Corner label
        corner = QLabel("")
        self._grid.addWidget(corner, 0, 0)

        # Axis labels
        mv_label = QLabel("← MV (INPUT) →")
        mv_label.setAlignment(Qt.AlignCenter)
        mv_label.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 10px;")
        self._grid.addWidget(mv_label, ny + 1, 1, 1, nu)

        self._header.setText(
            f"STEP RESPONSE MATRIX — {nu} MV × {ny} CV  |  "
            f"N={n}  dt={dt}s  ({n * dt:.0f}s horizon)"
        )

    @staticmethod
    def _cumsum_list(fir_list: List[np.ndarray]) -> List[np.ndarray]:
        result = []
        acc = np.zeros_like(fir_list[0])
        for g in fir_list:
            acc = acc + g
            result.append(acc.copy())
        return result


# ═════════════════════════════════════════════════════════════════════
#  Main Application Window
# ═════════════════════════════════════════════════════════════════════
class StepIdentApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MPC Step-Test Identification Studio — Azeotrope Process Control")
        self.setMinimumSize(1280, 800)
        self.resize(1500, 900)

        self._df: Optional[pd.DataFrame] = None
        self._result: Optional[IdentResult] = None
        self._thread: Optional[QThread] = None

        self._build_ui()
        self.setStyleSheet(STYLESHEET)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Horizontal)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.addWidget(splitter)

        # ── Left panel: config ───────────────────────────────────────
        left_panel = QWidget()
        left_panel.setFixedWidth(380)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(8, 8, 8, 8)

        # Title
        title = QLabel("STEP-TEST IDENT")
        title.setObjectName("lbl_title")
        left_layout.addWidget(title)

        subtitle = QLabel("MIMO FIR Model Identification")
        subtitle.setObjectName("lbl_subtitle")
        left_layout.addWidget(subtitle)

        left_layout.addSpacing(6)

        # ── Data loading ─────────────────────────────────────────────
        grp_data = QGroupBox("DATA SOURCE")
        grp_data_layout = QVBoxLayout(grp_data)

        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("Load CSV…")
        self.btn_load.clicked.connect(self._on_load_csv)
        btn_row.addWidget(self.btn_load)

        self.btn_auto = QPushButton("Auto-Assign")
        self.btn_auto.setToolTip("Assign first half as MV, rest as CV")
        self.btn_auto.clicked.connect(self._on_auto_assign)
        self.btn_auto.setEnabled(False)
        btn_row.addWidget(self.btn_auto)
        grp_data_layout.addLayout(btn_row)

        self.lbl_file = QLabel("No file loaded")
        self.lbl_file.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 11px;")
        grp_data_layout.addWidget(self.lbl_file)

        self.tag_table = TagTable()
        self.tag_table.setMaximumHeight(260)
        self.tag_table.roles_changed.connect(self._on_roles_changed)
        grp_data_layout.addWidget(self.tag_table)

        self.lbl_assign = QLabel("MV: 0  |  CV: 0")
        self.lbl_assign.setStyleSheet(f"color: {SILVER['text_secondary']}; font-size: 11px;")
        grp_data_layout.addWidget(self.lbl_assign)

        left_layout.addWidget(grp_data)

        # ── Identification config ────────────────────────────────────
        grp_cfg = QGroupBox("IDENTIFICATION")
        cfg_form = QFormLayout(grp_cfg)
        cfg_form.setSpacing(8)

        self.spin_ncoeff = QSpinBox()
        self.spin_ncoeff.setRange(5, 500)
        self.spin_ncoeff.setValue(60)
        self.spin_ncoeff.setToolTip("Number of FIR coefficients (model length)")
        cfg_form.addRow("Model Length", self.spin_ncoeff)

        self.spin_dt = QDoubleSpinBox()
        self.spin_dt.setRange(0.1, 3600.0)
        self.spin_dt.setValue(60.0)
        self.spin_dt.setSuffix(" s")
        self.spin_dt.setDecimals(1)
        self.spin_dt.setToolTip("Sample period")
        cfg_form.addRow("Sample Period", self.spin_dt)

        self.combo_method = QComboBox()
        self.combo_method.addItems(["dls", "cor", "ridge"])
        self.combo_method.setToolTip(
            "DLS = Direct Least Squares (open-loop)\n"
            "COR = Correlation (closed-loop tolerant)\n"
            "Ridge = L2 regularised (collinear inputs)"
        )
        cfg_form.addRow("Method", self.combo_method)

        self.combo_smooth = QComboBox()
        self.combo_smooth.addItems(["pipeline", "exponential", "savgol", "asymptotic", "none"])
        cfg_form.addRow("Smoothing", self.combo_smooth)

        self.spin_alpha = QDoubleSpinBox()
        self.spin_alpha.setRange(0.001, 1000.0)
        self.spin_alpha.setValue(1.0)
        self.spin_alpha.setDecimals(3)
        self.spin_alpha.setToolTip("Ridge regularisation parameter")
        cfg_form.addRow("Ridge α", self.spin_alpha)

        self.chk_detrend = QCheckBox("Detrend")
        self.chk_detrend.setChecked(True)
        self.chk_prewhiten = QCheckBox("Prewhiten (Δ)")
        self.chk_prewhiten.setChecked(False)

        opts_row = QHBoxLayout()
        opts_row.addWidget(self.chk_detrend)
        opts_row.addWidget(self.chk_prewhiten)
        cfg_form.addRow(opts_row)

        left_layout.addWidget(grp_cfg)

        # ── Conditioning config ──────────────────────────────────────
        grp_cond = QGroupBox("DATA CONDITIONING")
        cond_form = QFormLayout(grp_cond)

        self.spin_clip = QDoubleSpinBox()
        self.spin_clip.setRange(1.0, 10.0)
        self.spin_clip.setValue(4.0)
        self.spin_clip.setDecimals(1)
        self.spin_clip.setSuffix(" σ")
        self.spin_clip.setToolTip("Outlier clipping threshold (std devs)")
        cond_form.addRow("Outlier Clip", self.spin_clip)

        left_layout.addWidget(grp_cond)

        # ── Run button ───────────────────────────────────────────────
        self.btn_identify = QPushButton("▶  IDENTIFY MODEL")
        self.btn_identify.setObjectName("btn_identify")
        self.btn_identify.setEnabled(False)
        self.btn_identify.clicked.connect(self._on_identify)
        left_layout.addWidget(self.btn_identify)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        left_layout.addWidget(self.progress)

        left_layout.addStretch()

        # ── Branding ─────────────────────────────────────────────────
        brand = QLabel("AZEOTROPE PROCESS CONTROL")
        brand.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 9px; "
            f"letter-spacing: 2px; font-weight: 600;"
        )
        brand.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(brand)

        splitter.addWidget(left_panel)

        # ── Right panel: plots + log ─────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self.tabs = QTabWidget()

        # Tab 1: Step Response Matrix
        self.step_matrix = StepResponseMatrix()
        self.tabs.addTab(self.step_matrix, "Step Response Matrix")

        # Tab 2: Raw Data Preview
        self.plot_raw = pg.GraphicsLayoutWidget()
        self.plot_raw.setBackground(SILVER["plot_bg"])
        self.tabs.addTab(self.plot_raw, "Raw Data")

        # Tab 3: Diagnostics Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.tabs.addTab(self.log_text, "Diagnostics")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_panel)

        splitter.setSizes([380, 1100])

        # Status bar
        self.statusBar().showMessage("Ready — load a CSV file to begin")

    # ─────────────────────────────────────────────────────────────────
    #  Slots
    # ─────────────────────────────────────────────────────────────────
    @Slot()
    def _on_load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Step-Test Data",
            str(Path.home()),
            "CSV Files (*.csv);;All Files (*.*)"
        )
        if not path:
            return

        try:
            # Try to detect timestamp column
            df = pd.read_csv(path)

            # Attempt to parse first column as datetime index
            first_col = df.columns[0]
            try:
                df[first_col] = pd.to_datetime(df[first_col])
                df = df.set_index(first_col)
                logger.info("Parsed '%s' as datetime index", first_col)
            except (ValueError, TypeError):
                logger.info("No datetime index detected — using integer index")

            # Convert all remaining columns to numeric
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            self._df = df
            self.tag_table.load_columns(df)
            self.btn_auto.setEnabled(True)

            n_rows = len(df)
            n_cols = len(df.columns)
            fname = Path(path).name
            self.lbl_file.setText(f"{fname}  ({n_rows:,} rows × {n_cols} tags)")
            self.lbl_file.setStyleSheet(f"color: {SILVER['accent_green']}; font-size: 11px;")
            self.statusBar().showMessage(f"Loaded {fname}: {n_rows:,} × {n_cols}")
            logger.info("Loaded %s: %d rows, %d columns", fname, n_rows, n_cols)

            self._plot_raw_data()

        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load CSV:\n{e}")
            logger.exception("CSV load failed")

    @Slot()
    def _on_auto_assign(self):
        self.tag_table.auto_assign()

    @Slot()
    def _on_roles_changed(self):
        mv = self.tag_table.get_mv_cols()
        cv = self.tag_table.get_cv_cols()
        self.lbl_assign.setText(f"MV: {len(mv)}  |  CV: {len(cv)}")
        can_run = len(mv) >= 1 and len(cv) >= 1 and self._df is not None
        self.btn_identify.setEnabled(can_run)

    @Slot()
    def _on_identify(self):
        if self._df is None:
            return

        mv_cols = self.tag_table.get_mv_cols()
        cv_cols = self.tag_table.get_cv_cols()

        if not mv_cols or not cv_cols:
            QMessageBox.warning(self, "Setup", "Assign at least 1 MV and 1 CV.")
            return

        # Condition data
        try:
            u, y, df_clean = DataConditioner.condition(
                self._df, mv_cols, cv_cols,
                clip_sigma=self.spin_clip.value(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Conditioning Error", str(e))
            return

        n_samples = u.shape[0]
        n_coeff = self.spin_ncoeff.value()
        if n_samples < n_coeff + 10:
            QMessageBox.warning(
                self, "Insufficient Data",
                f"Only {n_samples} samples for {n_coeff} coefficients.\n"
                f"Reduce model length or provide more data."
            )
            return

        # Build config
        config = IdentConfig(
            n_coeff=n_coeff,
            dt=self.spin_dt.value(),
            method=IdentMethod(self.combo_method.currentText()),
            smooth=SmoothMethod(self.combo_smooth.currentText()),
            ridge_alpha=self.spin_alpha.value(),
            detrend=self.chk_detrend.isChecked(),
            prewhiten=self.chk_prewhiten.isChecked(),
        )

        # Run in background thread
        self.btn_identify.setEnabled(False)
        self.progress.setVisible(True)
        self.statusBar().showMessage("Identifying model…")

        self._thread = QThread()
        self._worker = IdentWorker(u, y, config)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(lambda r: self._on_ident_done(r, mv_cols, cv_cols))
        self._worker.error.connect(self._on_ident_error)
        self._worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    def _on_ident_done(self, result: IdentResult, mv_cols, cv_cols):
        self._result = result
        self.progress.setVisible(False)
        self.btn_identify.setEnabled(True)

        # Plot step response matrix
        self.step_matrix.plot_result(result, mv_cols, cv_cols, result.config.dt)
        self.tabs.setCurrentIndex(0)

        # Diagnostics log
        self.log_text.clear()
        self.log_text.append(result.summary())
        self.log_text.append("\n" + "─" * 60)
        self.log_text.append("\nSettling Indices (1% tolerance):")
        settling = result.settling_index(tol=0.01)
        for i in range(result.ny):
            for j in range(result.nu):
                cv_name = cv_cols[i] if i < len(cv_cols) else f"CV{i}"
                mv_name = mv_cols[j] if j < len(mv_cols) else f"MV{j}"
                self.log_text.append(
                    f"  {cv_name} ← {mv_name}: settles at k={settling[i,j]} "
                    f"({settling[i,j] * result.config.dt:.0f}s)"
                )

        self.statusBar().showMessage(
            f"Identification complete: {result.nu} MV × {result.ny} CV, "
            f"cond={result.condition_number:.0f}"
        )

    def _on_ident_error(self, msg: str):
        self.progress.setVisible(False)
        self.btn_identify.setEnabled(True)
        QMessageBox.critical(self, "Identification Failed", msg)
        self.statusBar().showMessage("Identification failed")

    # ─────────────────────────────────────────────────────────────────
    #  Raw data plotting
    # ─────────────────────────────────────────────────────────────────
    def _plot_raw_data(self):
        if self._df is None:
            return

        self.plot_raw.clear()
        df = self._df
        cols = list(df.columns)
        n_cols = len(cols)

        if n_cols == 0:
            return

        plots = []
        for idx, col in enumerate(cols[:12]):  # max 12 subplots
            if idx == 0:
                p = self.plot_raw.addPlot(row=idx, col=0)
            else:
                p = self.plot_raw.addPlot(row=idx, col=0)
                p.setXLink(plots[0])

            series = df[col].values
            valid = ~np.isnan(series.astype(float))
            x = np.arange(len(series))

            color = TRACE_COLORS[idx % len(TRACE_COLORS)]
            p.plot(x[valid], series[valid], pen=pg.mkPen(color, width=1.5))

            p.setLabel("left", col, color=SILVER["text_secondary"])
            p.showGrid(x=True, y=True, alpha=0.1)

            for axis_name in ("left", "bottom"):
                ax = p.getAxis(axis_name)
                ax.setPen(pg.mkPen(SILVER["plot_axis"], width=1))
                ax.setTextPen(pg.mkPen(SILVER["plot_axis"]))

            plots.append(p)

        if n_cols > 12:
            note = self.plot_raw.addLabel(
                f"(Showing 12 of {n_cols} tags)",
                row=12, col=0,
            )

        self.tabs.setCurrentIndex(1)


# ═════════════════════════════════════════════════════════════════════
#  Entry point
# ═════════════════════════════════════════════════════════════════════
def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Step-Test Identification Studio")
    app.setOrganizationName("Azeotrope Process Control")

    # Force dark palette baseline
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(SILVER["bg_primary"]))
    palette.setColor(QPalette.WindowText, QColor(SILVER["text_primary"]))
    palette.setColor(QPalette.Base, QColor(SILVER["bg_input"]))
    palette.setColor(QPalette.AlternateBase, QColor(SILVER["bg_secondary"]))
    palette.setColor(QPalette.Text, QColor(SILVER["text_primary"]))
    palette.setColor(QPalette.Button, QColor(SILVER["bg_header"]))
    palette.setColor(QPalette.ButtonText, QColor(SILVER["text_primary"]))
    palette.setColor(QPalette.Highlight, QColor(SILVER["accent_blue"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    window = StepIdentApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
