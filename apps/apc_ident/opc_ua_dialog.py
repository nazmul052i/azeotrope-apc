"""OPC UA Data Acquisition Dialog.

A popup dialog that lets the engineer:
1. Connect to an OPC UA server
2. Browse the address space and select tags
3. Configure sample time and duration
4. Start live data collection with real-time trending
5. Save collected data to CSV (or auto-load into the Data tab)

Uses opcua-asyncio (asyncua) for the OPC UA client.
Falls back to a simulated mode if opcua is not installed.
"""
from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, Signal, QThread, QTimer, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QSplitter, QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)

# Check if opcua is available
try:
    from asyncua.sync import Client as OpcClient
    HAS_OPCUA = True
except ImportError:
    HAS_OPCUA = False
    logger.info("asyncua not installed -- OPC UA dialog will use simulation mode")

# Light theme for dialog
_DIALOG_SS = """
QDialog { background: #EBECF1; color: #1A1C24; }
QLabel { color: #1A1C24; background: transparent; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #F5F6FA; color: #1A1C24; border: 1px solid #9AA5B4; padding: 4px; }
QPushButton { background: #EBECF1; color: #1A1C24;
    border: 1px solid #9AA5B4; padding: 6px 16px; border-radius: 3px; }
QPushButton:hover { border-color: #2B5EA7; }
QGroupBox { border: 1px solid #9AA5B4; border-radius: 4px;
    margin-top: 8px; padding-top: 12px; background: #EBECF1; }
QGroupBox::title { color: #4A5068; }
QTreeWidget, QTableWidget { background: #F5F6FA; border: 1px solid #9AA5B4;
    color: #1A1C24; }
QHeaderView::section { background: #D0D2DB; color: #1A1C24;
    border: 1px solid #9AA5B4; padding: 4px; }
QTextEdit { background: #F5F6FA; color: #1A1C24; border: 1px solid #9AA5B4;
    font-family: Consolas; font-size: 9pt; }
QProgressBar { background: #DBDBE0; border: 1px solid #9AA5B4; border-radius: 3px; }
QProgressBar::chunk { background: #2B5EA7; border-radius: 2px; }
QCheckBox { color: #1A1C24; }
"""


class OpcUaCollector(QThread):
    """Background thread that collects OPC UA data."""
    data_point = Signal(dict)     # {tag: value, ...} per sample
    progress = Signal(int, int)   # (current, total)
    error = Signal(str)
    finished_ok = Signal(object)  # DataFrame

    def __init__(self, server_url: str, tag_ids: List[str],
                 sample_time_sec: float, n_samples: int):
        super().__init__()
        self.server_url = server_url
        self.tag_ids = tag_ids
        self.sample_time_sec = sample_time_sec
        self.n_samples = n_samples
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        data_rows = []
        timestamps = []

        if HAS_OPCUA:
            try:
                client = OpcClient(self.server_url)
                client.connect()
                nodes = [client.get_node(tid) for tid in self.tag_ids]

                for i in range(self.n_samples):
                    if self._stop:
                        break
                    ts = datetime.now()
                    row = {}
                    for tid, node in zip(self.tag_ids, nodes):
                        try:
                            row[tid] = float(node.read_value())
                        except Exception:
                            row[tid] = np.nan
                    data_rows.append(row)
                    timestamps.append(ts)
                    self.data_point.emit(row)
                    self.progress.emit(i + 1, self.n_samples)

                    # Wait for next sample
                    elapsed = (datetime.now() - ts).total_seconds()
                    wait = max(0, self.sample_time_sec - elapsed)
                    if wait > 0 and not self._stop:
                        self.msleep(int(wait * 1000))

                client.disconnect()
            except Exception as e:
                self.error.emit(str(e))
                return
        else:
            # Simulation mode -- generate random walk data
            np.random.seed(42)
            values = {tid: 50.0 + np.random.randn() * 5 for tid in self.tag_ids}

            for i in range(self.n_samples):
                if self._stop:
                    break
                ts = datetime.now()
                row = {}
                for tid in self.tag_ids:
                    values[tid] += np.random.randn() * 0.5
                    row[tid] = values[tid]
                data_rows.append(row)
                timestamps.append(ts)
                self.data_point.emit(row)
                self.progress.emit(i + 1, self.n_samples)

                elapsed = (datetime.now() - ts).total_seconds()
                wait = max(0, self.sample_time_sec - elapsed)
                if wait > 0 and not self._stop:
                    self.msleep(int(wait * 1000))

        if data_rows:
            df = pd.DataFrame(data_rows, index=pd.DatetimeIndex(timestamps))
            df.index.name = "Timestamp"
            self.finished_ok.emit(df)


class OpcUaDialog(QDialog):
    """OPC UA data acquisition dialog."""

    data_collected = Signal(object, str)  # (DataFrame, save_path or "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OPC UA Data Acquisition")
        self.setMinimumSize(900, 650)
        self.setStyleSheet(_DIALOG_SS)

        self._collector: Optional[OpcUaCollector] = None
        self._collected_df: Optional[pd.DataFrame] = None
        self._live_data: Dict[str, List[float]] = {}
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # ── Connection ──
        conn_box = QGroupBox("CONNECTION")
        cf = QFormLayout(conn_box)
        cf.setSpacing(6)

        self.server_url = QLineEdit("opc.tcp://localhost:4840")
        self.server_url.setPlaceholderText("opc.tcp://hostname:port")
        cf.addRow("Server URL:", self.server_url)

        conn_row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect)
        conn_row.addWidget(self.connect_btn)

        self.conn_status = QLabel(
            "Simulation mode (asyncua not installed)"
            if not HAS_OPCUA else "Disconnected")
        self.conn_status.setStyleSheet("color: #9AA5B4;")
        conn_row.addWidget(self.conn_status, 1)
        cf.addRow("", conn_row)
        lay.addWidget(conn_box)

        # ── Main splitter: tag browser | live trend ──
        splitter = QSplitter(Qt.Horizontal)

        # Left: tag selection
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        tag_box = QGroupBox("TAGS")
        tl = QVBoxLayout(tag_box)

        tag_hint = QLabel(
            "Enter tag IDs (one per line) or browse server.\n"
            "Format: ns=2;s=TagName or ns=2;i=1234")
        tag_hint.setStyleSheet("color: #4A5068; font-size: 8pt;")
        tag_hint.setWordWrap(True)
        tl.addWidget(tag_hint)

        self.tag_input = QTextEdit()
        self.tag_input.setPlaceholderText(
            "ns=2;s=TI-201.PV\nns=2;s=FIC-101.SP\nns=2;s=FCV-410.OP")
        self.tag_input.setMaximumHeight(120)
        tl.addWidget(self.tag_input)

        # Quick-add common tags
        quick_row = QHBoxLayout()
        self.quick_add = QLineEdit()
        self.quick_add.setPlaceholderText("Add tag: TI-201.PV")
        quick_row.addWidget(self.quick_add, 1)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.clicked.connect(self._on_quick_add)
        quick_row.addWidget(add_btn)
        tl.addLayout(quick_row)

        ll.addWidget(tag_box)

        # Sampling config
        sample_box = QGroupBox("SAMPLING")
        sf = QFormLayout(sample_box)

        self.sample_time = QDoubleSpinBox()
        self.sample_time.setRange(0.1, 3600.0)
        self.sample_time.setValue(1.0)
        self.sample_time.setSuffix(" s")
        self.sample_time.setDecimals(1)
        sf.addRow("Sample Period:", self.sample_time)

        self.duration_mode = QComboBox()
        self.duration_mode.addItems(["Number of Samples", "Duration (minutes)"])
        self.duration_mode.currentIndexChanged.connect(self._on_duration_mode)
        sf.addRow("Mode:", self.duration_mode)

        self.n_samples = QSpinBox()
        self.n_samples.setRange(10, 100000)
        self.n_samples.setValue(500)
        sf.addRow("Samples:", self.n_samples)

        self.duration_min = QDoubleSpinBox()
        self.duration_min.setRange(0.1, 1440.0)
        self.duration_min.setValue(10.0)
        self.duration_min.setSuffix(" min")
        self.duration_min.setVisible(False)
        sf.addRow("Duration:", self.duration_min)

        ll.addWidget(sample_box)

        # Auto-load checkbox
        self.chk_auto_load = QCheckBox("Auto-load into Data tab when done")
        self.chk_auto_load.setChecked(True)
        ll.addWidget(self.chk_auto_load)

        splitter.addWidget(left)

        # Right: live trend + status
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        trend_box = QGroupBox("LIVE TREND")
        trend_lay = QVBoxLayout(trend_box)

        try:
            import pyqtgraph as pg
            self.trend_plot = pg.PlotWidget()
            self.trend_plot.setBackground("#FFFFFF")
            self.trend_plot.showGrid(x=True, y=True, alpha=0.15)
            self.trend_plot.setLabel("bottom", "Sample")
            self.trend_plot.setLabel("left", "Value")
            self._trend_curves: Dict[str, object] = {}
            trend_lay.addWidget(self.trend_plot)
            self._has_plot = True
        except ImportError:
            self._has_plot = False
            trend_lay.addWidget(QLabel("(pyqtgraph not available for live trend)"))

        rl.addWidget(trend_box, 1)

        # Collection log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(80)
        rl.addWidget(self.log_text)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        lay.addWidget(splitter, 1)

        # ── Bottom: progress + buttons ──
        bottom = QHBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        bottom.addWidget(self.progress_bar, 1)

        self.start_btn = QPushButton("\u25B6  Start Collection")
        self.start_btn.setStyleSheet(
            "QPushButton { background: #2D8E3C; color: white; "
            "font-weight: bold; padding: 8px 20px; border-radius: 3px; }")
        self.start_btn.clicked.connect(self._on_start)
        bottom.addWidget(self.start_btn)

        self.stop_btn = QPushButton("\u25A0  Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        bottom.addWidget(self.stop_btn)

        self.save_btn = QPushButton("Save CSV...")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        bottom.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load into Data")
        self.load_btn.setEnabled(False)
        self.load_btn.clicked.connect(self._on_load_into_data)
        bottom.addWidget(self.load_btn)

        lay.addLayout(bottom)

    # ==================================================================
    # Connection
    # ==================================================================
    def _on_connect(self):
        url = self.server_url.text().strip()
        if not url:
            return

        if HAS_OPCUA:
            try:
                client = OpcClient(url)
                client.connect()
                self.conn_status.setText(f"Connected to {url}")
                self.conn_status.setStyleSheet("color: #2D8E3C;")
                client.disconnect()
            except Exception as e:
                self.conn_status.setText(f"Failed: {e}")
                self.conn_status.setStyleSheet("color: #C0392B;")
        else:
            self.conn_status.setText("Simulation mode (no real connection)")
            self.conn_status.setStyleSheet("color: #D4930D;")

    # ==================================================================
    # Duration mode
    # ==================================================================
    def _on_duration_mode(self, index: int):
        if index == 0:
            self.n_samples.setVisible(True)
            self.duration_min.setVisible(False)
        else:
            self.n_samples.setVisible(False)
            self.duration_min.setVisible(True)

    def _get_n_samples(self) -> int:
        if self.duration_mode.currentIndex() == 0:
            return self.n_samples.value()
        else:
            dur_sec = self.duration_min.value() * 60
            return max(10, int(dur_sec / self.sample_time.value()))

    # ==================================================================
    # Quick add tag
    # ==================================================================
    def _on_quick_add(self):
        tag = self.quick_add.text().strip()
        if not tag:
            return
        # Auto-format if user just typed a tag name
        if not tag.startswith("ns="):
            tag = f"ns=2;s={tag}"
        current = self.tag_input.toPlainText().strip()
        if current:
            self.tag_input.setText(current + "\n" + tag)
        else:
            self.tag_input.setText(tag)
        self.quick_add.clear()

    # ==================================================================
    # Collection
    # ==================================================================
    def _get_tag_ids(self) -> List[str]:
        text = self.tag_input.toPlainText().strip()
        if not text:
            return []
        return [line.strip() for line in text.split("\n")
                if line.strip() and not line.strip().startswith("#")]

    def _on_start(self):
        tag_ids = self._get_tag_ids()
        if not tag_ids:
            QMessageBox.information(self, "Start", "Enter at least one tag ID.")
            return

        n = self._get_n_samples()
        dt = self.sample_time.value()

        self.log_text.clear()
        self.log_text.append(
            f"Starting collection: {len(tag_ids)} tags, "
            f"{n} samples, dt={dt}s")

        # Clear live data
        self._live_data = {tid: [] for tid in tag_ids}
        if self._has_plot:
            self.trend_plot.clear()
            self._trend_curves = {}
            colors = ["#3C6291", "#14696A", "#C0392B", "#2D8E3C",
                      "#8E44AD", "#D4930D", "#1A5276", "#C44569"]
            for i, tid in enumerate(tag_ids):
                import pyqtgraph as pg
                color = colors[i % len(colors)]
                name = tid.split(";s=")[-1] if ";s=" in tid else tid
                curve = self.trend_plot.plot([], [], pen=pg.mkPen(color, width=1.5),
                                              name=name)
                self._trend_curves[tid] = curve

        self.progress_bar.setRange(0, n)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.save_btn.setEnabled(False)
        self.load_btn.setEnabled(False)

        self._collector = OpcUaCollector(
            self.server_url.text().strip(), tag_ids, dt, n)
        self._collector.data_point.connect(self._on_data_point)
        self._collector.progress.connect(self._on_progress)
        self._collector.error.connect(self._on_error)
        self._collector.finished_ok.connect(self._on_collection_done)
        self._collector.start()

    def _on_stop(self):
        if self._collector:
            self._collector.stop()
            self.log_text.append("Stopping...")

    @Slot(dict)
    def _on_data_point(self, row: dict):
        """Update live trend with new data point."""
        if not self._has_plot:
            return
        for tid, val in row.items():
            if tid in self._live_data:
                self._live_data[tid].append(val)
                if tid in self._trend_curves:
                    x = list(range(len(self._live_data[tid])))
                    self._trend_curves[tid].setData(x, self._live_data[tid])

    @Slot(int, int)
    def _on_progress(self, current: int, total: int):
        self.progress_bar.setValue(current)

    @Slot(str)
    def _on_error(self, msg: str):
        self.log_text.append(f"ERROR: {msg}")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Collection Error", msg)

    @Slot(object)
    def _on_collection_done(self, df: pd.DataFrame):
        self._collected_df = df
        self.log_text.append(
            f"Collection complete: {len(df)} samples, "
            f"{len(df.columns)} tags")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.save_btn.setEnabled(True)
        self.load_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if self.chk_auto_load.isChecked():
            self._on_load_into_data()

    # ==================================================================
    # Save / Load
    # ==================================================================
    def _on_save(self):
        if self._collected_df is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Collected Data", "",
            "CSV Files (*.csv);;All Files (*)")
        if not path:
            return
        if not path.endswith(".csv"):
            path += ".csv"
        self._collected_df.to_csv(path)
        self.log_text.append(f"Saved: {path}")

        # Also emit for the main window
        self.data_collected.emit(self._collected_df, path)

    def _on_load_into_data(self):
        if self._collected_df is None:
            return
        self.data_collected.emit(self._collected_df, "")
        self.log_text.append("Data loaded into Data tab")
        self.accept()  # close dialog
