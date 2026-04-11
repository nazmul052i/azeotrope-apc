"""Data tab -- load step-test data, view trends, mark segments.

Layout:

  Top bar     : [Load CSV...]  [Reload]  file label
  Stats label : "1500 rows x 5 cols  - 2 NaN  - datetime index"
  Splitter    :
    Top  : pyqtgraph trend strip with one stacked panel per column
           (linked X axes). A LinearRegionItem on the bottom panel
           lets the user drag-select a window. The orange shaded
           region under each panel reflects the active segment.
    Bot  : Segments table | side buttons (Add from selection,
           Add manual, Delete, Use Whole Range)

The trends are interactive: pan/zoom with mouse, drag the orange
selection bracket to fine-tune. Add Segment captures the current
selection into the project's segment list.
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
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from azeoapc.identification import Segment

from ..session import IdentSession
from ..theme import SILVER, TRACE_COLORS


# Maximum panels in the trend strip; if more columns, the rest are hidden
MAX_TREND_PANELS = 8


class DataTab(QWidget):
    """Data tab body."""

    config_changed = Signal()    # emitted when project state changes
    data_loaded = Signal()       # emitted when a fresh DataFrame appears

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._region: Optional[pg.LinearRegionItem] = None
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
        self.load_btn = QPushButton("Load CSV...")
        self.load_btn.clicked.connect(self._on_load_csv)
        bar.addWidget(self.load_btn)

        self.reload_btn = QPushButton("Reload")
        self.reload_btn.clicked.connect(self._on_reload)
        self.reload_btn.setEnabled(False)
        bar.addWidget(self.reload_btn)

        self.file_label = QLabel("(no file loaded)")
        self.file_label.setStyleSheet(
            f"color: {SILVER['text_secondary']}; padding-left: 10px;")
        bar.addWidget(self.file_label, 1)

        root.addLayout(bar)

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 9pt;")
        root.addWidget(self.stats_label)

        # ── Splitter: trend strip / segment editor ──
        splitter = QSplitter(Qt.Vertical)

        # Trend strip
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground(SILVER["plot_bg"])
        splitter.addWidget(self.plot_widget)

        # Segment editor: segments table | excluded ranges table | buttons
        seg_panel = QWidget()
        seg_layout = QHBoxLayout(seg_panel)
        seg_layout.setContentsMargins(0, 6, 0, 0)
        seg_layout.setSpacing(6)

        # ── Segments column ──
        seg_col = QVBoxLayout()
        seg_col.setSpacing(2)
        seg_col.addWidget(QLabel("Segments"))

        self.seg_table = QTableWidget()
        self.seg_table.setColumnCount(3)
        self.seg_table.setHorizontalHeaderLabels(["Name", "Start", "End"])
        self.seg_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.seg_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.seg_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self.seg_table.verticalHeader().setVisible(False)
        self.seg_table.itemChanged.connect(self._on_seg_cell_edited)
        self.seg_table.itemSelectionChanged.connect(
            self._on_segment_selection_changed)
        seg_col.addWidget(self.seg_table, 1)
        seg_layout.addLayout(seg_col, 2)

        # ── Excluded ranges column (for the currently selected segment) ──
        ex_col = QVBoxLayout()
        ex_col.setSpacing(2)
        self.ex_label = QLabel("Excluded Ranges")
        self.ex_label.setStyleSheet(
            f"color: {SILVER['text_secondary']};")
        ex_col.addWidget(self.ex_label)

        self.ex_table = QTableWidget()
        self.ex_table.setColumnCount(2)
        self.ex_table.setHorizontalHeaderLabels(["Start", "End"])
        self.ex_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.ex_table.verticalHeader().setVisible(False)
        self.ex_table.itemChanged.connect(self._on_ex_cell_edited)
        ex_col.addWidget(self.ex_table, 1)
        seg_layout.addLayout(ex_col, 2)

        # ── Buttons column ──
        side = QVBoxLayout()
        side.setSpacing(4)

        side.addWidget(QLabel("Segments"))
        self.add_from_sel_btn = QPushButton("Add from Selection")
        self.add_from_sel_btn.setToolTip(
            "Capture the orange selection bracket as a new segment")
        self.add_from_sel_btn.clicked.connect(self._on_add_from_selection)
        self.add_from_sel_btn.setEnabled(False)
        side.addWidget(self.add_from_sel_btn)

        self.add_whole_btn = QPushButton("Use Whole Range")
        self.add_whole_btn.clicked.connect(self._on_use_whole_range)
        self.add_whole_btn.setEnabled(False)
        side.addWidget(self.add_whole_btn)

        self.delete_seg_btn = QPushButton("Delete")
        self.delete_seg_btn.clicked.connect(self._on_delete_segment)
        side.addWidget(self.delete_seg_btn)

        side.addSpacing(8)
        side.addWidget(QLabel("Excluded Ranges"))
        self.add_ex_btn = QPushButton("+ Excluded from Selection")
        self.add_ex_btn.setToolTip(
            "Capture the orange selection bracket as an excluded range "
            "inside the selected segment")
        self.add_ex_btn.clicked.connect(self._on_add_excluded_from_selection)
        self.add_ex_btn.setEnabled(False)
        side.addWidget(self.add_ex_btn)

        self.del_ex_btn = QPushButton("- Excluded")
        self.del_ex_btn.clicked.connect(self._on_delete_excluded)
        side.addWidget(self.del_ex_btn)

        side.addStretch()
        seg_layout.addLayout(side)

        splitter.addWidget(seg_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([500, 220])

        root.addWidget(splitter, 1)

    # ==================================================================
    # Data loading
    # ==================================================================
    def _on_load_csv(self):
        start_dir = self._examples_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Step-Test CSV", start_dir,
            "CSV (*.csv);;Parquet (*.parquet);;All Files (*)")
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
            df = self._read_dataframe(path)
        except Exception as e:
            QMessageBox.critical(self, "Load CSV", f"Failed to load:\n{e}")
            return
        self.session.df = df
        self.session.df_path = path
        # Persist the path on the project (relative to the project file
        # if we know it; absolute otherwise -- save_ident_project does
        # the rebasing on save)
        self.session.project.data_source_path = path
        self.session.project.timestamp_col = (
            df.index.name or "" if isinstance(df.index, pd.DatetimeIndex) else "")
        # Reset segments only if changing files
        self._refresh_from_session()
        self.data_loaded.emit()
        self.config_changed.emit()

    def _read_dataframe(self, path: str) -> pd.DataFrame:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path)
        # Try to parse a leading datetime column
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

    # ==================================================================
    # Population
    # ==================================================================
    def _refresh_from_session(self):
        df = self.session.df
        if df is None:
            self.file_label.setText("(no file loaded)")
            self.stats_label.setText("")
            self.reload_btn.setEnabled(False)
            self.add_from_sel_btn.setEnabled(False)
            self.add_whole_btn.setEnabled(False)
            self.plot_widget.clear()
            self._region = None
            self._populate_segments_table()
            return

        path = self.session.df_path or "(in memory)"
        self.file_label.setText(os.path.basename(path))
        self.file_label.setStyleSheet(
            f"color: {SILVER['accent_green']}; padding-left: 10px;"
            f" font-weight: 500;")
        n_nan = int(df.isna().sum().sum())
        idx_kind = "datetime" if isinstance(df.index, pd.DatetimeIndex) else "integer"
        self.stats_label.setText(
            f"  {len(df):,} rows  \u00d7  {len(df.columns)} columns "
            f"  -  {n_nan} NaN  -  {idx_kind} index")

        self.reload_btn.setEnabled(True)
        self.add_from_sel_btn.setEnabled(True)
        self.add_whole_btn.setEnabled(True)

        self._build_trend_plots(df)
        self._populate_segments_table()

    # ------------------------------------------------------------------
    def _build_trend_plots(self, df: pd.DataFrame):
        self.plot_widget.clear()
        cols = list(df.columns)[:MAX_TREND_PANELS]
        if not cols:
            return

        # Use sample index on the x axis (consistent across datetime /
        # integer indices). The selection region works in this same
        # coordinate space, which we then map back to the dataframe
        # index when adding segments.
        x = np.arange(len(df))

        plots = []
        for idx, col in enumerate(cols):
            p = self.plot_widget.addPlot(row=idx, col=0)
            p.setMouseEnabled(x=True, y=False)
            p.showGrid(x=True, y=True, alpha=0.15)
            ax_color = SILVER["plot_axis"]
            for an in ("left", "bottom"):
                ax = p.getAxis(an)
                ax.setPen(pg.mkPen(ax_color, width=1))
                ax.setTextPen(pg.mkPen(ax_color))
                ax.setStyle(tickFont=QFont("Segoe UI", 8))
            p.setLabel("left", col, color=SILVER["text_secondary"])
            if idx > 0:
                p.setXLink(plots[0])

            color = TRACE_COLORS[idx % len(TRACE_COLORS)]
            series = df[col].to_numpy(dtype=float)
            valid = ~np.isnan(series)
            p.plot(x[valid], series[valid], pen=pg.mkPen(color, width=1.5))
            plots.append(p)

        if len(df.columns) > MAX_TREND_PANELS:
            self.plot_widget.addLabel(
                f"(showing {MAX_TREND_PANELS} of {len(df.columns)} columns)",
                row=MAX_TREND_PANELS, col=0,
                color=SILVER["text_muted"], size="9pt",
            )

        # Drag-selection region on the bottom panel only; visually mirrored
        # by linking X.
        if plots:
            n = len(df)
            lo = int(0.25 * n)
            hi = int(0.75 * n)
            self._region = pg.LinearRegionItem(
                values=(lo, hi),
                brush=pg.mkBrush(255, 159, 67, 40),
                pen=pg.mkPen(255, 159, 67, width=1),
            )
            self._region.setZValue(10)
            plots[-1].addItem(self._region)

    # ==================================================================
    # Segment table
    # ==================================================================
    def _populate_segments_table(self):
        segs = self.session.project.segments
        self.seg_table.blockSignals(True)
        self.seg_table.setRowCount(len(segs))
        for r, seg in enumerate(segs):
            for c, value in enumerate([
                seg.name,
                _ts_to_text(seg.start),
                _ts_to_text(seg.end),
            ]):
                item = QTableWidgetItem(value)
                self.seg_table.setItem(r, c, item)
        self.seg_table.blockSignals(False)
        # Reselect first row if possible to drive the excluded-ranges pane
        if segs and self.seg_table.currentRow() < 0:
            self.seg_table.selectRow(0)
        self._populate_excluded_table()

    def _on_seg_cell_edited(self, item: QTableWidgetItem):
        r = item.row()
        c = item.column()
        if r >= len(self.session.project.segments):
            return
        seg = self.session.project.segments[r]
        text = item.text().strip()
        if c == 0:
            seg.name = text
        elif c == 1:
            seg.start = text or None
        elif c == 2:
            seg.end = text or None
        self.config_changed.emit()

    def _on_segment_selection_changed(self):
        self._populate_excluded_table()

    def _on_add_from_selection(self):
        if self._region is None or self.session.df is None:
            return
        lo_x, hi_x = self._region.getRegion()
        df = self.session.df
        n = len(df)
        lo = int(max(0, min(n - 1, round(lo_x))))
        hi = int(max(0, min(n - 1, round(hi_x))))
        if lo >= hi:
            QMessageBox.information(self, "Add Segment",
                                     "Selection is empty.")
            return
        start = df.index[lo]
        end = df.index[hi]
        seg = Segment(
            name=f"seg{len(self.session.project.segments) + 1}",
            start=start, end=end,
        )
        self.session.project.segments.append(seg)
        self._populate_segments_table()
        self.config_changed.emit()

    def _on_use_whole_range(self):
        if self.session.df is None:
            return
        df = self.session.df
        seg = Segment(
            name="full",
            start=df.index[0],
            end=df.index[-1],
        )
        self.session.project.segments = [seg]
        self._populate_segments_table()
        self.config_changed.emit()

    def _on_delete_segment(self):
        rows = sorted({i.row() for i in self.seg_table.selectedIndexes()},
                      reverse=True)
        if not rows:
            return
        for r in rows:
            if 0 <= r < len(self.session.project.segments):
                del self.session.project.segments[r]
        self._populate_segments_table()
        self.config_changed.emit()

    # ==================================================================
    # Excluded ranges (C5.5)
    # ==================================================================
    def _selected_segment(self) -> Optional[Segment]:
        row = self.seg_table.currentRow()
        if 0 <= row < len(self.session.project.segments):
            return self.session.project.segments[row]
        return None

    def _populate_excluded_table(self):
        seg = self._selected_segment()
        self.ex_table.blockSignals(True)
        if seg is None:
            self.ex_table.setRowCount(0)
            self.ex_label.setText("Excluded Ranges  (no segment selected)")
            self.add_ex_btn.setEnabled(False)
            self.del_ex_btn.setEnabled(False)
            self.ex_table.blockSignals(False)
            return
        self.ex_label.setText(f"Excluded Ranges  ({seg.name or '?'})")
        self.add_ex_btn.setEnabled(self.session.df is not None)
        self.del_ex_btn.setEnabled(True)
        self.ex_table.setRowCount(len(seg.excluded_ranges))
        for r, (start, end) in enumerate(seg.excluded_ranges):
            self.ex_table.setItem(r, 0, QTableWidgetItem(_ts_to_text(start)))
            self.ex_table.setItem(r, 1, QTableWidgetItem(_ts_to_text(end)))
        self.ex_table.blockSignals(False)

    def _on_ex_cell_edited(self, item: QTableWidgetItem):
        seg = self._selected_segment()
        if seg is None:
            return
        r = item.row()
        c = item.column()
        if r >= len(seg.excluded_ranges):
            return
        old_start, old_end = seg.excluded_ranges[r]
        text = item.text().strip() or None
        if c == 0:
            seg.excluded_ranges[r] = (text, old_end)
        else:
            seg.excluded_ranges[r] = (old_start, text)
        self.config_changed.emit()

    def _on_add_excluded_from_selection(self):
        seg = self._selected_segment()
        if seg is None:
            QMessageBox.information(
                self, "Excluded Range", "Select a segment first.")
            return
        if self._region is None or self.session.df is None:
            return
        lo_x, hi_x = self._region.getRegion()
        df = self.session.df
        n = len(df)
        lo = int(max(0, min(n - 1, round(lo_x))))
        hi = int(max(0, min(n - 1, round(hi_x))))
        if lo >= hi:
            QMessageBox.information(self, "Excluded Range",
                                     "Selection is empty.")
            return
        start = df.index[lo]
        end = df.index[hi]
        seg.excluded_ranges.append((start, end))
        self._populate_excluded_table()
        self.config_changed.emit()

    def _on_delete_excluded(self):
        seg = self._selected_segment()
        if seg is None:
            return
        rows = sorted({i.row() for i in self.ex_table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            if 0 <= r < len(seg.excluded_ranges):
                del seg.excluded_ranges[r]
        self._populate_excluded_table()
        self.config_changed.emit()

    # ==================================================================
    # Public hooks
    # ==================================================================
    def on_project_loaded(self):
        """Called by MainWindow when a fresh IdentProject becomes active.

        If the project carries a data_source_path that exists on disk,
        auto-load it so the user lands on the trend view immediately.
        """
        self.session.df = None
        self.session.df_path = None
        path = self.session.project.data_source_path
        if path:
            # Resolve relative to the project file's directory if needed
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
def _ts_to_text(v) -> str:
    if v is None:
        return ""
    try:
        if isinstance(v, pd.Timestamp):
            return v.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    if isinstance(v, (int, float)):
        return str(int(v))
    return str(v)
