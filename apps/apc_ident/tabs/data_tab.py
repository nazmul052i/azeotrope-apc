"""Data tab -- INCA Discovery-style trend workspace.

The trend plot IS the workspace. All data processing happens directly
on the plot through interactive modes, right-click context menus,
and draggable overlays.

Layout:
  ┌────────────────────────────────────────────┬──────────────┐
  │ [Load] [Mode: Pan|Select|Bad|Cutoff]       │ PROPERTIES   │
  │ [Smart Condition] [Before/After] [SSD]     │              │
  ├────────────────────────────────────────────┤ Tag stats    │
  │                                            │ Segment info │
  │           TREND PLOTS                      │ Conditioning │
  │         (full height, interactive)         │   report     │
  │                                            │              │
  │   • Right-click: Mark Bad, Exclude,        │              │
  │     Set Cutoff, Detect Spikes, SSD         │              │
  │   • Drag cutoff lines to adjust            │              │
  │   • Orange region for segment selection    │              │
  │   • Green shading for steady state         │              │
  │   • Red X for bad data                     │              │
  │                                            │              │
  ├────────────────────────────────────────────┤              │
  │ Segments: [seg1: 08:30-11:00] [+ Add] [-] │              │
  └────────────────────────────────────────────┴──────────────┘
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from azeoapc.identification import Segment
from azeoapc.identification.data_conditioning import (
    auto_configure as auto_configure_conditioning,
    condition_dataframe as run_conditioning_engine,
    detect_cutoff_violations, detect_flatline, detect_spikes,
)
from azeoapc.identification.steady_state import (
    compute_ssd, auto_configure_ssd,
)
from azeoapc.identification.resampling import (
    resample_dataframe, analyze_resample_rates, suggest_resample_rate,
)

from ..session import IdentSession
from ..theme import SILVER, TRACE_COLORS

MAX_TREND_PANELS = 12


# ---------------------------------------------------------------------------
# Tag Properties Dialog
# ---------------------------------------------------------------------------
class TagPropertiesDialog(QDialog):
    """Dialog showing tag properties, stats, and role assignment."""

    def __init__(self, col: str, df, tag_assignment, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Tag Properties: {col}")
        self.setMinimumWidth(380)
        self._col = col
        self._tag = tag_assignment

        # Force light theme on dialog
        self.setStyleSheet(
            f"QDialog {{ background: {SILVER['bg_panel']}; color: {SILVER['text_primary']}; }}"
            f"QLabel {{ color: {SILVER['text_primary']}; background: transparent; }}"
            f"QLineEdit, QComboBox {{ background: {SILVER['bg_input']}; "
            f"  color: {SILVER['text_primary']}; border: 1px solid {SILVER['border']}; "
            f"  padding: 4px; }}"
            f"QPushButton {{ background: {SILVER['bg_panel']}; color: {SILVER['text_primary']}; "
            f"  border: 1px solid {SILVER['border']}; padding: 6px 16px; border-radius: 3px; }}"
            f"QPushButton:hover {{ border-color: {SILVER['accent_blue']}; }}"
        )

        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        # Column name (read-only)
        self.col_label = QLineEdit(col)
        self.col_label.setReadOnly(True)
        self.col_label.setStyleSheet(
            f"background: {SILVER['bg_panel']}; color: {SILVER['text_secondary']}; "
            f"border: 1px solid {SILVER['border']};")
        form.addRow("CSV Column:", self.col_label)

        # Controller tag (editable)
        self.tag_edit = QLineEdit(tag_assignment.controller_tag if tag_assignment else "")
        self.tag_edit.setPlaceholderText("e.g. TI-201.PV")
        form.addRow("Controller Tag:", self.tag_edit)

        # Role
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Ignore", "MV", "CV", "DV"])
        if tag_assignment:
            self.role_combo.setCurrentText(tag_assignment.role)
        form.addRow("Role:", self.role_combo)

        lay.addLayout(form)

        # Stats
        if df is not None and col in df.columns:
            s = df[col]
            n = len(s)
            n_nan = int(s.isna().sum())
            stats_text = (
                f"\nStatistics ({n:,} samples):\n"
                f"  Mean:    {s.mean():.4f}\n"
                f"  Std:     {s.std():.4f}\n"
                f"  Min:     {s.min():.4f}\n"
                f"  Max:     {s.max():.4f}\n"
                f"  Median:  {s.median():.4f}\n"
                f"  NaN:     {n_nan} ({100*n_nan/max(n,1):.1f}%)\n"
                f"  Range:   {s.max() - s.min():.4f}"
            )
            stats_label = QLabel(stats_text)
            stats_label.setStyleSheet(
                f"font-family: Consolas; font-size: 9pt; "
                f"color: {SILVER['text_primary']}; "
                f"background: {SILVER['bg_input']}; padding: 8px; "
                f"border: 1px solid {SILVER['border']}; border-radius: 3px;")
            lay.addWidget(stats_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def get_values(self):
        return {
            "controller_tag": self.tag_edit.text().strip(),
            "role": self.role_combo.currentText(),
        }


# ---------------------------------------------------------------------------
# Compact toolbar button helper
# ---------------------------------------------------------------------------
def _tool_btn(text: str, tooltip: str = "", checkable: bool = False) -> QToolButton:
    btn = QToolButton()
    btn.setText(text)
    btn.setToolTip(tooltip)
    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    btn.setCheckable(checkable)
    btn.setMinimumHeight(28)
    btn.setMinimumWidth(36)
    return btn


class DataTab(QWidget):
    """INCA Discovery-style trend workspace."""

    config_changed = Signal()
    data_loaded = Signal()

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._region: Optional[pg.LinearRegionItem] = None
        self._plots: List[pg.PlotItem] = []
        self._plot_cols: List[str] = []
        self._overlays: Dict[str, list] = {}
        self._cond_config = None
        self._ssd_result = None
        self._show_conditioned = False
        self._loaded_files: List[str] = []  # track all loaded file paths

        self._build()
        self._refresh_from_session()

    # ==================================================================
    # Build UI
    # ==================================================================
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Tag browser panel (hidden until data is loaded) ──
        self._tag_panel = self._build_tag_browser()
        self._tag_panel.setVisible(False)
        root.addWidget(self._tag_panel)

        # ── Center: trend workspace ──
        center = QWidget()
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(4, 4, 2, 4)
        center_lay.setSpacing(4)

        # Toolbar
        center_lay.addWidget(self._build_toolbar())

        # Trend plots
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground(SILVER["plot_bg"])
        center_lay.addWidget(self.plot_widget, 1)

        # Segment bar (compact)
        center_lay.addWidget(self._build_segment_bar())

        root.addWidget(center, 1)

        # ── Right: properties panel ──
        right = QFrame()
        right.setFixedWidth(260)
        right.setStyleSheet(
            f"QFrame {{ border-left: 1px solid {SILVER['border']}; }}")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(8, 8, 8, 8)
        right_lay.setSpacing(6)

        # File info
        self.file_label = QLabel("No file loaded")
        self.file_label.setWordWrap(True)
        self.file_label.setStyleSheet(
            f"font-weight: 600; color: {SILVER['text_secondary']}; border: none;")
        right_lay.addWidget(self.file_label)

        self.stats_label = QLabel("")
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 8pt; border: none;")
        right_lay.addWidget(self.stats_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {SILVER['border']}; border: none;")
        right_lay.addWidget(sep)

        # Properties / conditioning report
        props_label = QLabel("CONDITIONING")
        props_label.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 7pt; "
            f"font-weight: bold; letter-spacing: 1px; border: none;")
        right_lay.addWidget(props_label)

        self.props_text = QTextEdit()
        self.props_text.setReadOnly(True)
        self.props_text.setStyleSheet(
            f"background: {SILVER['bg_input']}; font-family: Consolas; "
            f"font-size: 8pt; border: 1px solid {SILVER['border']};")
        self.props_text.setText("Load data and run conditioning\nto see results here.")
        self.props_text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.props_text.customContextMenuRequested.connect(
            self._show_props_context_menu)
        right_lay.addWidget(self.props_text, 1)

        root.addWidget(right)

    # ------------------------------------------------------------------
    def _build_toolbar(self):
        bar = QFrame()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            f"QFrame {{ background: {SILVER['bg_panel']}; "
            f"border: 1px solid {SILVER['border']}; border-radius: 3px; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(4)

        # Load
        self.load_btn = _tool_btn("\U0001F4C2 Load", "Load CSV or Parquet file")
        self.load_btn.clicked.connect(self._on_load_csv)
        lay.addWidget(self.load_btn)

        self.reload_btn = _tool_btn("\u21BB", "Reload file")
        self.reload_btn.clicked.connect(self._on_reload)
        self.reload_btn.setEnabled(False)
        lay.addWidget(self.reload_btn)

        # Separator
        lay.addWidget(self._vsep())

        # Smart condition
        self.smart_btn = _tool_btn(
            "\u26A1 Auto Condition",
            "Auto-detect and apply conditioning\n"
            "(cutoff, flatline, spike, bad data replacement)")
        self.smart_btn.clicked.connect(self._on_auto_condition)
        lay.addWidget(self.smart_btn)

        # Before/After toggle
        self.before_after_btn = _tool_btn(
            "\u2194 Before/After", "Toggle raw vs conditioned view", checkable=True)
        self.before_after_btn.toggled.connect(self._on_toggle_conditioned)
        lay.addWidget(self.before_after_btn)

        lay.addWidget(self._vsep())

        # SSD
        self.ssd_btn = _tool_btn(
            "\u2593 SSD", "Run steady-state detection")
        self.ssd_btn.clicked.connect(self._on_auto_ssd)
        lay.addWidget(self.ssd_btn)

        # Resample
        self.resample_btn = _tool_btn(
            "\u2261 Resample", "Analyze and resample data")
        self.resample_btn.clicked.connect(self._on_resample)
        lay.addWidget(self.resample_btn)

        lay.addStretch()

        # Stats summary
        self.toolbar_stats = QLabel("")
        self.toolbar_stats.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 8pt; background: transparent;")
        lay.addWidget(self.toolbar_stats)

        return bar

    def _vsep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setFixedHeight(24)
        sep.setStyleSheet(f"background: {SILVER['border']};")
        return sep

    # ------------------------------------------------------------------
    def _build_tag_browser(self):
        """Tag browser panel -- select which tags to plot."""
        panel = QFrame()
        panel.setFixedWidth(180)
        panel.setStyleSheet(
            f"QFrame {{ border-right: 1px solid {SILVER['border']}; }}")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # Header
        header = QLabel("TAGS")
        header.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 7pt; "
            f"font-weight: bold; letter-spacing: 2px; border: none;")
        lay.addWidget(header)

        # Search
        self.tag_search = QLineEdit()
        self.tag_search.setPlaceholderText("\U0001F50D Search tags...")
        self.tag_search.setFixedHeight(26)
        self.tag_search.textChanged.connect(self._on_tag_search)
        lay.addWidget(self.tag_search)

        # Quick filter buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)
        self.tag_all_btn = QPushButton("All")
        self.tag_all_btn.setFixedHeight(22)
        self.tag_all_btn.clicked.connect(lambda: self._set_all_tags(True))
        btn_row.addWidget(self.tag_all_btn)

        self.tag_mv_btn = QPushButton("MVs")
        self.tag_mv_btn.setFixedHeight(22)
        self.tag_mv_btn.clicked.connect(self._select_mvs_only)
        btn_row.addWidget(self.tag_mv_btn)

        self.tag_cv_btn = QPushButton("CVs")
        self.tag_cv_btn.setFixedHeight(22)
        self.tag_cv_btn.clicked.connect(self._select_cvs_only)
        btn_row.addWidget(self.tag_cv_btn)

        self.tag_none_btn = QPushButton("None")
        self.tag_none_btn.setFixedHeight(22)
        self.tag_none_btn.clicked.connect(lambda: self._set_all_tags(False))
        btn_row.addWidget(self.tag_none_btn)
        lay.addLayout(btn_row)

        # Scrollable tag checklist
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {SILVER['border']}; }}")

        self._tag_list_widget = QWidget()
        self._tag_list_layout = QVBoxLayout(self._tag_list_widget)
        self._tag_list_layout.setContentsMargins(4, 4, 4, 4)
        self._tag_list_layout.setSpacing(2)
        self._tag_list_layout.addStretch()
        scroll.setWidget(self._tag_list_widget)
        self._tag_checkboxes: List[QCheckBox] = []

        lay.addWidget(scroll, 1)

        # Tag stats (shown for selected tag)
        self._tag_stats_label = QLabel("")
        self._tag_stats_label.setWordWrap(True)
        self._tag_stats_label.setStyleSheet(
            f"color: {SILVER['text_secondary']}; font-size: 8pt; "
            f"border: none; padding-top: 4px;")
        self._tag_stats_label.setFixedHeight(60)
        lay.addWidget(self._tag_stats_label)

        return panel

    def _populate_tag_browser(self):
        """Fill the tag browser with checkboxes for each column."""
        # Clear existing
        for cb in self._tag_checkboxes:
            cb.setParent(None)
            cb.deleteLater()
        self._tag_checkboxes.clear()

        # Remove stretch
        while self._tag_list_layout.count():
            item = self._tag_list_layout.takeAt(0)

        df = self.session.df
        if df is None:
            self._tag_list_layout.addStretch()
            return

        # Get role assignments for color coding
        role_map = {}
        for t in self.session.project.tag_assignments:
            role_map[t.column] = t.role

        role_colors = {
            "MV": SILVER["accent_blue"],
            "CV": SILVER["accent_green"],
            "DV": SILVER["accent_orange"],
        }

        for col in df.columns:
            role = role_map.get(col, "Ignore")
            color = role_colors.get(role, SILVER["text_primary"])

            # Build display text: [MV] FCV-410.SP
            if role in ("MV", "CV", "DV"):
                display = f"[{role}] {col}"
            else:
                display = f"      {col}"

            cb = QCheckBox(display)
            cb.setChecked(True)
            cb.setToolTip(f"{col}  ({role})")
            # Store raw column name
            cb.setProperty("tag_column", col)

            cb.setStyleSheet(
                f"QCheckBox {{ color: {color}; font-size: 8.5pt; "
                f"font-family: Consolas; "
                f"background: transparent; border: none; }}")
            cb.toggled.connect(self._on_tag_toggled)
            cb.enterEvent = lambda ev, c=col: self._show_tag_stats(c)

            # Right-click context menu
            cb.setContextMenuPolicy(Qt.CustomContextMenu)
            cb.customContextMenuRequested.connect(
                lambda pos, c=col, w=cb: self._show_tag_context_menu(c, w, pos))

            self._tag_checkboxes.append(cb)
            self._tag_list_layout.addWidget(cb)

        self._tag_list_layout.addStretch()

    def _on_tag_search(self, text: str):
        """Filter tag checkboxes by search text."""
        text = text.lower()
        for cb in self._tag_checkboxes:
            col = (cb.property("tag_column") or cb.text()).lower()
            visible = text in col if text else True
            cb.setVisible(visible)

    def _on_tag_toggled(self, checked: bool):
        """Rebuild trend plots based on checked tags."""
        self._rebuild_plots_from_selection()

    def _set_all_tags(self, checked: bool):
        """Check or uncheck all tags."""
        for cb in self._tag_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._rebuild_plots_from_selection()

    def _select_mvs_only(self):
        mv_cols = {t.column for t in self.session.project.tag_assignments
                   if t.role == "MV"}
        for cb in self._tag_checkboxes:
            cb.blockSignals(True)
            col = cb.property("tag_column") or ""
            cb.setChecked(col in mv_cols)
            cb.blockSignals(False)
        self._rebuild_plots_from_selection()

    def _select_cvs_only(self):
        cv_cols = {t.column for t in self.session.project.tag_assignments
                   if t.role == "CV"}
        for cb in self._tag_checkboxes:
            cb.blockSignals(True)
            col = cb.property("tag_column") or ""
            cb.setChecked(col in cv_cols)
            cb.blockSignals(False)
        self._rebuild_plots_from_selection()

    def _get_selected_columns(self) -> List[str]:
        """Return list of column names that are checked."""
        df = self.session.df
        if df is None:
            return []
        selected = []
        for cb in self._tag_checkboxes:
            if cb.isChecked() and cb.isVisible():
                col = cb.property("tag_column") or cb.text().strip()
                if col in df.columns:
                    selected.append(col)
        return selected

    def _rebuild_plots_from_selection(self):
        """Rebuild trend plots showing only the selected tags."""
        df = self.session.df
        if df is None:
            return
        selected = self._get_selected_columns()
        if not selected:
            self.plot_widget.clear()
            self._plots = []
            self._plot_cols = []
            return
        # Build plots for selected columns only
        self._build_trend_plots_for_columns(df, selected)

    def _show_tag_stats(self, col: str):
        """Show statistics for a tag on hover."""
        df = self.session.df
        if df is None or col not in df.columns:
            return
        s = df[col]
        n_nan = int(s.isna().sum())
        pct_nan = 100.0 * n_nan / max(len(s), 1)
        mean = s.mean()
        std = s.std()
        mn = s.min()
        mx = s.max()

        role = "Ignore"
        for t in self.session.project.tag_assignments:
            if t.column == col:
                role = t.role
                break

        self._tag_stats_label.setText(
            f"{col}  [{role}]\n"
            f"Mean: {mean:.3f}  Std: {std:.3f}\n"
            f"Range: [{mn:.2f}, {mx:.2f}]  NaN: {pct_nan:.1f}%")

    def _show_tag_context_menu(self, col: str, widget, pos):
        """Right-click context menu on a tag in the browser."""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #EBECF1; color: #1A1C24; "
            "border: 1px solid #9AA5B4; }"
            "QMenu::item { padding: 5px 24px 5px 12px; }"
            "QMenu::item:selected { background: #2B5EA7; color: white; }"
            "QMenu::separator { height: 1px; background: #C8CDD8; margin: 4px 8px; }")

        act = menu.addAction(f"\u2699  Properties: {col}...")
        act.triggered.connect(lambda: self._open_tag_properties(col))

        menu.addSeparator()

        # Role quick-set
        role_menu = menu.addMenu("Set Role")
        for role in ["MV", "CV", "DV", "Ignore"]:
            r_act = role_menu.addAction(role)
            r_act.triggered.connect(
                lambda _, r=role, c=col: self._set_tag_role(c, r))

        menu.addSeparator()

        act = menu.addAction("Plot Only This Tag")
        act.triggered.connect(lambda: self._plot_only_tag(col))

        act = menu.addAction("Hide This Tag")
        act.triggered.connect(lambda: self._hide_tag(col))

        menu.addSeparator()

        act = menu.addAction("\u2500  Set Upper Cutoff...")
        act.triggered.connect(lambda: self._ctx_set_cutoff(col, "upper"))

        act = menu.addAction("\u2500  Set Lower Cutoff...")
        act.triggered.connect(lambda: self._ctx_set_cutoff(col, "lower"))

        act = menu.addAction("\u25B2  Detect Spikes")
        act.triggered.connect(lambda: self._ctx_detect_spikes(col))

        act = menu.addAction("\u25A0  Detect Flatline")
        act.triggered.connect(lambda: self._ctx_detect_flatline(col))

        menu.exec(widget.mapToGlobal(pos))

    def _open_tag_properties(self, col: str):
        """Open the tag properties dialog."""
        # Find or create tag assignment
        tag = None
        for t in self.session.project.tag_assignments:
            if t.column == col:
                tag = t
                break

        from azeoapc.identification import TagAssignment
        if tag is None:
            tag = TagAssignment(column=col)
            self.session.project.tag_assignments.append(tag)

        dlg = TagPropertiesDialog(col, self.session.df, tag, parent=self)
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.get_values()
            tag.controller_tag = vals["controller_tag"]
            tag.role = vals["role"]
            self._populate_tag_browser()
            self._rebuild_plots_from_selection()
            self.config_changed.emit()

    def _set_tag_role(self, col: str, role: str):
        """Quick-set role from context menu."""
        from azeoapc.identification import TagAssignment
        found = False
        for t in self.session.project.tag_assignments:
            if t.column == col:
                t.role = role
                if not t.controller_tag:
                    t.controller_tag = col
                found = True
                break
        if not found:
            self.session.project.tag_assignments.append(
                TagAssignment(column=col, role=role, controller_tag=col))
        self._populate_tag_browser()
        self.config_changed.emit()

    def _plot_only_tag(self, col: str):
        """Show only this tag in the trend plot."""
        for cb in self._tag_checkboxes:
            cb.blockSignals(True)
            cb.setChecked((cb.property("tag_column") or "") == col)
            cb.blockSignals(False)
        self._rebuild_plots_from_selection()

    def _hide_tag(self, col: str):
        """Uncheck this tag."""
        for cb in self._tag_checkboxes:
            if (cb.property("tag_column") or "") == col:
                cb.setChecked(False)
                break

    # ------------------------------------------------------------------
    def _build_segment_bar(self):
        bar = QFrame()
        bar.setFixedHeight(32)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)

        lay.addWidget(QLabel("Segments:"))

        self.seg_label = QLabel("(none)")
        self.seg_label.setStyleSheet(
            f"color: {SILVER['text_secondary']}; font-size: 8pt;")
        lay.addWidget(self.seg_label, 1)

        self.add_seg_btn = _tool_btn("+ From Selection", "Add segment from orange region")
        self.add_seg_btn.clicked.connect(self._on_add_from_selection)
        self.add_seg_btn.setEnabled(False)
        lay.addWidget(self.add_seg_btn)

        self.whole_btn = _tool_btn("Use All", "Use entire data range")
        self.whole_btn.clicked.connect(self._on_use_whole_range)
        self.whole_btn.setEnabled(False)
        lay.addWidget(self.whole_btn)

        self.del_seg_btn = _tool_btn("\u2715", "Delete last segment")
        self.del_seg_btn.clicked.connect(self._on_delete_last_segment)
        lay.addWidget(self.del_seg_btn)

        return bar

    # ==================================================================
    # Data loading
    # ==================================================================
    def _on_load_csv(self):
        start_dir = self._examples_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Step-Test Data", start_dir,
            "CSV (*.csv);;Parquet (*.parquet);;DMC Vector (*.vec);;All (*)")
        if not path:
            return
        self._load_path(path)

    def _on_reload(self):
        if self.session.df_path:
            self._load_path(self.session.df_path)

    def _examples_dir(self) -> str:
        ex = os.path.join(os.path.dirname(__file__), "..", "examples")
        return os.path.abspath(ex) if os.path.isdir(ex) else os.getcwd()

    def _load_path(self, path: str):
        try:
            df_new = self._read_dataframe(path)
        except Exception as e:
            QMessageBox.critical(self, "Load", f"Failed:\n{e}")
            return

        # Track loaded files
        if path not in self._loaded_files:
            self._loaded_files.append(path)

        # Merge with existing data if we already have a DataFrame
        if self.session.df is not None and len(self.session.df) > 0:
            existing = self.session.df
            # Add new columns that don't already exist
            for col in df_new.columns:
                if col not in existing.columns:
                    # Align by index if both are datetime, otherwise by position
                    if (isinstance(existing.index, pd.DatetimeIndex)
                            and isinstance(df_new.index, pd.DatetimeIndex)):
                        existing = existing.join(df_new[[col]], how="outer")
                    else:
                        # Positional merge -- pad shorter with NaN
                        n = max(len(existing), len(df_new))
                        if len(df_new) <= len(existing):
                            vals = np.full(len(existing), np.nan)
                            vals[:len(df_new)] = df_new[col].values
                            existing[col] = vals
                        else:
                            # Extend existing
                            vals = df_new[col].values[:len(existing)]
                            existing[col] = vals
            self.session.df = existing
        else:
            self.session.df = df_new

        self.session.df_path = path
        self.session.project.data_source_path = self._loaded_files[0]
        self.session.project.timestamp_col = (
            self.session.df.index.name or ""
            if isinstance(self.session.df.index, pd.DatetimeIndex) else "")
        self._cond_config = None
        self._ssd_result = None
        self._show_conditioned = False
        self.before_after_btn.setChecked(False)
        self._refresh_from_session()
        self.data_loaded.emit()
        self.config_changed.emit()

    def _read_dataframe(self, path: str) -> pd.DataFrame:
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

        # Re-apply saved calculated vectors
        calc_vecs = self.session.project.calculated_vectors
        if calc_vecs:
            from azeoapc.identification.calculated_vectors import (
                CalculatedTag, add_calculated_tags,
            )
            tags = [CalculatedTag(name=cv["name"], expression=cv["expression"])
                    for cv in calc_vecs]
            try:
                df = add_calculated_tags(df, tags)
            except Exception:
                pass

        return df

    # ==================================================================
    # Refresh
    # ==================================================================
    def _refresh_from_session(self):
        df = self.session.df
        has_data = df is not None and len(df) > 0

        self.reload_btn.setEnabled(has_data)
        self.add_seg_btn.setEnabled(has_data)
        self.whole_btn.setEnabled(has_data)
        self.smart_btn.setEnabled(has_data)
        self.ssd_btn.setEnabled(has_data)
        self.resample_btn.setEnabled(has_data)

        if not has_data:
            self.file_label.setText("No file loaded")
            self.stats_label.setText("Load a CSV file to begin")
            self.toolbar_stats.setText("")
            self.plot_widget.clear()
            self._plots = []
            self._plot_cols = []
            self._region = None
            self._tag_panel.setVisible(False)
            self._update_seg_label()
            return

        path = self.session.df_path or "(in memory)"
        self.file_label.setText(os.path.basename(path))
        n_nan = int(df.isna().sum().sum())
        idx_kind = "datetime" if isinstance(df.index, pd.DatetimeIndex) else "integer"
        self.stats_label.setText(
            f"{len(df):,} rows \u00d7 {len(df.columns)} cols\n"
            f"{n_nan} NaN \u2022 {idx_kind} index")
        self.toolbar_stats.setText(
            f"{len(df):,} rows \u00d7 {len(df.columns)} cols")

        self._tag_panel.setVisible(True)
        self._populate_tag_browser()
        self._build_trend_plots(df)
        self._update_seg_label()

    # ==================================================================
    # Trend plots
    # ==================================================================
    def _build_trend_plots(self, df: pd.DataFrame):
        selected = self._get_selected_columns()
        cols = selected if selected else list(df.columns)[:MAX_TREND_PANELS]
        self._build_trend_plots_for_columns(df, cols)

    def _build_trend_plots_for_columns(self, df: pd.DataFrame, cols: List[str]):
        self.plot_widget.clear()
        self._plots = []
        self._plot_cols = []
        self._overlays = {}

        cols = cols[:MAX_TREND_PANELS]
        if not cols:
            return

        x = np.arange(len(df))

        for idx, col in enumerate(cols):
            p = self.plot_widget.addPlot(row=idx, col=0)
            p.setMouseEnabled(x=True, y=False)
            p.showGrid(x=True, y=True, alpha=0.12)
            ax_color = SILVER["plot_axis"]
            for an in ("left", "bottom"):
                ax = p.getAxis(an)
                ax.setPen(pg.mkPen(ax_color, width=1))
                ax.setTextPen(pg.mkPen(ax_color))
                ax.setStyle(tickFont=QFont("Segoe UI", 8))
            p.setLabel("left", col, color=SILVER["text_secondary"],
                       **{"font-size": "8pt"})
            if idx > 0:
                p.setXLink(self._plots[0])
            # Hide bottom axis except on last plot
            if idx < len(cols) - 1:
                p.getAxis("bottom").setStyle(showValues=False)

            color = TRACE_COLORS[idx % len(TRACE_COLORS)]
            series = df[col].to_numpy(dtype=float)
            valid = ~np.isnan(series)
            p.plot(x[valid], series[valid], pen=pg.mkPen(color, width=1.5))

            # Right-click context menu
            p.setMenuEnabled(False)
            vb = p.getViewBox()
            vb.menu = self._build_context_menu(col, p)

            self._plots.append(p)
            self._plot_cols.append(col)
            self._overlays[col] = []

        if len(df.columns) > MAX_TREND_PANELS:
            self.plot_widget.addLabel(
                f"(showing {MAX_TREND_PANELS} of {len(df.columns)} columns)",
                row=MAX_TREND_PANELS, col=0,
                color=SILVER["text_muted"], size="8pt")

        # Selection region
        if self._plots:
            n = len(df)
            lo = int(0.25 * n)
            hi = int(0.75 * n)
            self._region = pg.LinearRegionItem(
                values=(lo, hi),
                brush=pg.mkBrush(43, 94, 167, 35),  # blue tint
                pen=pg.mkPen(43, 94, 167, width=1),
            )
            self._region.setZValue(10)
            self._plots[-1].addItem(self._region)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def _build_context_menu(self, col: str, plot: pg.PlotItem) -> QMenu:
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #EBECF1; color: #1A1C24; "
            "border: 1px solid #9AA5B4; }"
            "QMenu::item { padding: 5px 24px 5px 12px; }"
            "QMenu::item:selected { background: #2B5EA7; color: white; }"
            "QMenu::separator { height: 1px; background: #C8CDD8; margin: 4px 8px; }")

        act = menu.addAction("\u2715  Mark Selection as Bad")
        act.triggered.connect(lambda: self._ctx_mark_bad(col))

        act = menu.addAction("\u2716  Exclude Selection")
        act.triggered.connect(lambda: self._on_add_excluded_from_selection(col))

        menu.addSeparator()

        act = menu.addAction("\u2500  Set Upper Cutoff...")
        act.triggered.connect(lambda: self._ctx_set_cutoff(col, "upper"))

        act = menu.addAction("\u2500  Set Lower Cutoff...")
        act.triggered.connect(lambda: self._ctx_set_cutoff(col, "lower"))

        menu.addSeparator()

        act = menu.addAction("\u25A0  Detect Flatline")
        act.triggered.connect(lambda: self._ctx_detect_flatline(col))

        act = menu.addAction("\u25B2  Detect Spikes")
        act.triggered.connect(lambda: self._ctx_detect_spikes(col))

        menu.addSeparator()

        act = menu.addAction("\u2593  SSD on this variable")
        act.triggered.connect(lambda: self._ctx_run_ssd(col))

        menu.addSeparator()

        act = menu.addAction("\u21BA  Clear overlays")
        act.triggered.connect(lambda: self._clear_overlays(col))

        act = menu.addAction("\u2922  Reset zoom")
        act.triggered.connect(lambda: plot.autoRange())

        return menu

    # ==================================================================
    # Toolbar actions
    # ==================================================================
    def _on_auto_condition(self):
        df = self.session.df
        if df is None:
            return
        self._cond_config = auto_configure_conditioning(df)
        df_clean, report = run_conditioning_engine(df, self._cond_config)

        # Draw overlays
        x = np.arange(len(df))
        for idx, col in enumerate(self._plot_cols):
            if col not in report.variable_stats:
                continue
            p = self._plots[idx]
            self._clear_overlays(col)

            raw = df[col].to_numpy(dtype=float)
            clean = df_clean[col].to_numpy(dtype=float)

            bad_mask = np.abs(raw - clean) > 1e-10
            bad_mask |= np.isnan(raw) & ~np.isnan(clean)

            if bad_mask.any():
                scatter = pg.ScatterPlotItem(
                    x[bad_mask], raw[bad_mask],
                    symbol='x', size=8,
                    pen=pg.mkPen(SILVER["accent_red"], width=1.5),
                    brush=pg.mkBrush(SILVER["accent_red"]),
                )
                p.addItem(scatter)
                self._overlays[col].append(scatter)

                valid_c = ~np.isnan(clean)
                curve = p.plot(
                    x[valid_c], clean[valid_c],
                    pen=pg.mkPen(SILVER["accent_blue"], width=1.2,
                                 style=Qt.DashLine))
                self._overlays[col].append(curve)

        self.props_text.setText(report.summary())

    def _on_toggle_conditioned(self, checked: bool):
        """Toggle between raw and conditioned data view."""
        self._show_conditioned = checked
        df = self.session.df
        if df is None:
            return

        if checked and self._cond_config is not None:
            df_clean, _ = run_conditioning_engine(df, self._cond_config)
            self._build_trend_plots(df_clean)
            self.toolbar_stats.setText("Showing: CONDITIONED")
        else:
            self._build_trend_plots(df)
            self.toolbar_stats.setText(
                f"{len(df):,} rows \u00d7 {len(df.columns)} cols")

    def _on_auto_ssd(self):
        df = self.session.df
        if df is None:
            return
        cols = [c for c in self._plot_cols
                if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        cfg = auto_configure_ssd(df, columns=cols)
        self._ssd_result = compute_ssd(df, cfg, columns=cols)

        x = np.arange(len(df))
        for idx, col in enumerate(self._plot_cols):
            if col not in self._ssd_result.variables:
                continue
            p = self._plots[idx]
            vr = self._ssd_result.variables[col]

            regions = _find_regions(vr.is_steady)
            for start, end in regions:
                region = pg.LinearRegionItem(
                    values=(start, end),
                    brush=pg.mkBrush(45, 142, 60, 25),
                    pen=pg.mkPen(None), movable=False)
                region.setZValue(-5)
                p.addItem(region)
                self._overlays.setdefault(col, []).append(region)

        self.props_text.setText(self._ssd_result.summary())

    def _on_resample(self):
        df = self.session.df
        if df is None or not isinstance(df.index, pd.DatetimeIndex):
            QMessageBox.information(self, "Resample",
                                     "Requires datetime index.")
            return

        analysis = analyze_resample_rates(df)
        suggestion = suggest_resample_rate(analysis)
        default = suggestion.period_sec if suggestion else 60

        period, ok = QInputDialog.getInt(
            self, "Resample", "Sample period (seconds):",
            value=default, min=1, max=3600)
        if not ok:
            return

        n_before = len(df)
        df_r = resample_dataframe(df, period)
        self.session.df = df_r
        self._refresh_from_session()
        self.props_text.setText(
            f"Resampled: {n_before} \u2192 {len(df_r)} rows\n"
            f"Period: {period}s")
        self.data_loaded.emit()
        self.config_changed.emit()

    # ==================================================================
    # Context menu actions
    # ==================================================================
    def _ctx_mark_bad(self, col: str):
        if self._region is None or self.session.df is None:
            return
        lo_x, hi_x = self._region.getRegion()
        df = self.session.df
        n = len(df)
        lo = int(max(0, min(n - 1, round(lo_x))))
        hi = int(max(0, min(n - 1, round(hi_x))))
        if lo >= hi:
            return
        df.iloc[lo:hi, df.columns.get_loc(col)] = np.nan
        self._refresh_from_session()
        self.props_text.setText(f"Marked {hi-lo} samples as bad in {col}")
        self.config_changed.emit()

    def _on_add_excluded_from_selection(self, col: str = ""):
        seg = self._get_or_create_segment()
        if self._region is None or self.session.df is None:
            return
        lo_x, hi_x = self._region.getRegion()
        df = self.session.df
        n = len(df)
        lo = int(max(0, min(n - 1, round(lo_x))))
        hi = int(max(0, min(n - 1, round(hi_x))))
        if lo >= hi:
            return
        start, end = df.index[lo], df.index[hi]
        seg.excluded_ranges.append((start, end))
        self._update_seg_label()
        self.config_changed.emit()
        self.props_text.setText(
            f"Excluded range added to '{seg.name}':\n{start} \u2192 {end}")

    def _ctx_set_cutoff(self, col: str, which: str):
        df = self.session.df
        if df is None or col not in df.columns:
            return
        series = df[col].dropna()
        default = float(series.max()) if which == "upper" else float(series.min())
        val, ok = QInputDialog.getDouble(
            self, f"{which.title()} Cutoff", f"{col}:", value=default, decimals=4)
        if not ok:
            return

        idx = self._plot_cols.index(col) if col in self._plot_cols else -1
        if idx < 0:
            return
        p = self._plots[idx]
        color = SILVER["accent_red"]
        label_pos = 0.95 if which == "upper" else 0.05
        line = pg.InfiniteLine(
            pos=val, angle=0,
            pen=pg.mkPen(color, width=1.2, style=Qt.DashLine),
            label=f"{which[:2].upper()}={val:.2f}",
            labelOpts={"color": color, "position": label_pos},
            movable=True,
        )
        p.addItem(line)
        self._overlays.setdefault(col, []).append(line)

    def _ctx_detect_flatline(self, col: str):
        df = self.session.df
        if df is None or col not in df.columns:
            return
        values = df[col].to_numpy(dtype=float)
        rng = float(np.nanmax(values) - np.nanmin(values))
        flat = detect_flatline(values, rng * 0.001, period=10)
        n_flat = int(flat.sum())

        if n_flat > 0:
            idx = self._plot_cols.index(col) if col in self._plot_cols else -1
            if idx >= 0:
                x = np.arange(len(values))
                scatter = pg.ScatterPlotItem(
                    x[flat], values[flat], symbol='s', size=6,
                    pen=pg.mkPen(SILVER["accent_orange"], width=1),
                    brush=pg.mkBrush(SILVER["accent_orange"]))
                self._plots[idx].addItem(scatter)
                self._overlays.setdefault(col, []).append(scatter)
        self.props_text.setText(f"{col}: {n_flat} flatline samples")

    def _ctx_detect_spikes(self, col: str):
        df = self.session.df
        if df is None or col not in df.columns:
            return
        values = df[col].to_numpy(dtype=float)
        diff_std = float(pd.Series(values).diff().dropna().std())
        spikes = detect_spikes(values, 5.0 * diff_std, reclassify_period=3)
        n_spikes = int(spikes.sum())

        if n_spikes > 0:
            idx = self._plot_cols.index(col) if col in self._plot_cols else -1
            if idx >= 0:
                x = np.arange(len(values))
                scatter = pg.ScatterPlotItem(
                    x[spikes], values[spikes], symbol='t', size=10,
                    pen=pg.mkPen(SILVER["accent_red"], width=1.5),
                    brush=pg.mkBrush(SILVER["accent_red"]))
                self._plots[idx].addItem(scatter)
                self._overlays.setdefault(col, []).append(scatter)
        self.props_text.setText(f"{col}: {n_spikes} spikes detected")

    def _ctx_run_ssd(self, col: str):
        df = self.session.df
        if df is None or col not in df.columns:
            return
        cfg = auto_configure_ssd(df, columns=[col])
        result = compute_ssd(df, cfg, columns=[col])

        idx = self._plot_cols.index(col) if col in self._plot_cols else -1
        if idx >= 0 and col in result.variables:
            p = self._plots[idx]
            vr = result.variables[col]
            regions = _find_regions(vr.is_steady)
            for start, end in regions:
                region = pg.LinearRegionItem(
                    values=(start, end),
                    brush=pg.mkBrush(45, 142, 60, 25),
                    pen=pg.mkPen(None), movable=False)
                region.setZValue(-5)
                p.addItem(region)
                self._overlays.setdefault(col, []).append(region)

            frac = float(vr.is_steady.sum()) / max(len(df), 1)
            self.props_text.setText(f"{col}: {frac:.1%} steady-state")

    # ==================================================================
    # Overlay management
    # ==================================================================
    def _clear_overlays(self, col: str):
        if col not in self._overlays:
            return
        idx = self._plot_cols.index(col) if col in self._plot_cols else -1
        if idx < 0:
            return
        p = self._plots[idx]
        for item in self._overlays[col]:
            p.removeItem(item)
        self._overlays[col] = []

    # ==================================================================
    # Segments (compact)
    # ==================================================================
    def _update_seg_label(self):
        segs = self.session.project.segments
        if not segs:
            self.seg_label.setText("(none)")
        else:
            parts = []
            for s in segs:
                n_ex = len(s.excluded_ranges)
                ex_str = f" [{n_ex} excl]" if n_ex > 0 else ""
                parts.append(f"{s.name}{ex_str}")
            self.seg_label.setText("  |  ".join(parts))

    def _on_add_from_selection(self):
        if self._region is None or self.session.df is None:
            return
        lo_x, hi_x = self._region.getRegion()
        df = self.session.df
        n = len(df)
        lo = int(max(0, min(n - 1, round(lo_x))))
        hi = int(max(0, min(n - 1, round(hi_x))))
        if lo >= hi:
            QMessageBox.information(self, "Segment", "Selection is empty.")
            return
        seg = Segment(
            name=f"seg{len(self.session.project.segments) + 1}",
            start=df.index[lo], end=df.index[hi])
        self.session.project.segments.append(seg)
        self._update_seg_label()
        self.config_changed.emit()

    def _on_use_whole_range(self):
        if self.session.df is None:
            return
        df = self.session.df
        seg = Segment(name="full", start=df.index[0], end=df.index[-1])
        self.session.project.segments = [seg]
        self._update_seg_label()
        self.config_changed.emit()

    def _on_delete_last_segment(self):
        if self.session.project.segments:
            self.session.project.segments.pop()
            self._update_seg_label()
            self.config_changed.emit()

    def _get_or_create_segment(self) -> Segment:
        if not self.session.project.segments:
            self._on_use_whole_range()
        return self.session.project.segments[-1]

    # ==================================================================
    # Properties panel context menu
    # ==================================================================
    def _show_props_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #EBECF1; color: #1A1C24; "
            "border: 1px solid #9AA5B4; }"
            "QMenu::item { padding: 5px 24px 5px 12px; }"
            "QMenu::item:selected { background: #2B5EA7; color: white; }"
            "QMenu::separator { height: 1px; background: #C8CDD8; margin: 4px 8px; }")
        act = menu.addAction("Copy to Clipboard")
        act.triggered.connect(
            lambda: QApplication.clipboard().setText(self.props_text.toPlainText())
            if hasattr(QApplication, 'clipboard') else None)

        act = menu.addAction("Clear")
        act.triggered.connect(lambda: self.props_text.clear())

        menu.addSeparator()

        act = menu.addAction("\u26A1 Auto Condition All")
        act.triggered.connect(self._on_auto_condition)

        act = menu.addAction("\u2593 Run SSD")
        act.triggered.connect(self._on_auto_ssd)

        menu.exec(self.props_text.mapToGlobal(pos))

    # ==================================================================
    # Public hooks
    # ==================================================================
    def on_project_loaded(self):
        self.session.df = None
        self.session.df_path = None
        self._cond_config = None
        self._ssd_result = None
        self._show_conditioned = False
        self._loaded_files = []
        path = self.session.project.data_source_path
        if path:
            if not os.path.isabs(path) and self.session.project.source_path:
                cand = os.path.normpath(os.path.join(
                    os.path.dirname(self.session.project.source_path), path))
                if os.path.exists(cand):
                    path = cand
            if os.path.exists(path):
                try:
                    self.session.df = self._read_dataframe(path)
                    self.session.df_path = path
                except Exception:
                    pass
        self._refresh_from_session()


# ---------------------------------------------------------------------------
def _find_regions(mask: np.ndarray) -> List[Tuple[int, int]]:
    regions = []
    in_region = False
    start = 0
    for i in range(len(mask)):
        if mask[i] and not in_region:
            start = i
            in_region = True
        elif not mask[i] and in_region:
            regions.append((start, i))
            in_region = False
    if in_region:
        regions.append((start, len(mask)))
    return regions
