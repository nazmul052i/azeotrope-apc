"""APC Runtime desktop window -- Aspen Watch Maker equivalent.

A QMainWindow that owns a MultiRunner and shows every loaded
controller in a sortable table with start/stop/refresh toolbar
actions and File / Actions / Tools / Help menus. Modeled after
the Aspen Watch Maker UI: a table of running RTE controllers with
columns for Name, Status, Model Type, Last Run, Last Update,
Cycle, Cycle Time, Avg Time, Available, Reason.

The window owns the MultiRunner directly (not via REST) so the
runners run on stdlib threading.Thread workers in this same
process. The REST + Prometheus surfaces still spin up in a
background uvicorn thread so apc_manager can talk to us as
before -- the GUI just becomes the primary face.

Headless mode (``apc-runtime --headless ...``) bypasses this
window entirely; the cli.py path stays intact for production
boxes that want a server-only deployment.
"""
from __future__ import annotations

import os
import threading
import webbrowser
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMainWindow, QMessageBox, QPushButton,
    QRadioButton, QStatusBar, QTableWidget, QTableWidgetItem, QToolBar,
    QVBoxLayout, QWidget,
)

from azeoapc.theme import SILVER

from .multi_runner import MultiRunner
from .runner import Runner, RunnerStatus


# ── Status badge colours ──────────────────────────────────────────────────
_STATUS_COLOR = {
    "RUNNING":  SILVER["accent_green"],
    "PAUSED":   SILVER["accent_orange"],
    "STARTING": SILVER["accent_cyan"],
    "STOPPING": SILVER["text_muted"],
    "STOPPED":  SILVER["text_muted"],
    "ERROR":    SILVER["accent_red"],
    "IDLE":     SILVER["text_muted"],
}

# Table columns (Aspen Watch Maker layout)
_COLS = [
    ("name",     "Name",        180),
    ("status",   "Status",      90),
    ("model",    "Model Type",  90),
    ("last_run", "Last Run",    150),
    ("cycle",    "Cycle",       70),
    ("cycle_ms", "Cycle Time",  90),
    ("avg_ms",   "Avg Time",    90),
    ("avail",    "Available",   80),
    ("reason",   "Reason",      300),
]


class RuntimeMainWindow(QMainWindow):
    """Aspen Watch Maker-style desktop window for apc_runtime."""

    def __init__(self, multi: MultiRunner, *,
                 rest_url: Optional[str] = None,
                 historian_url: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self.multi = multi
        self.rest_url = rest_url
        self.historian_url = historian_url

        self.setWindowTitle("APC Runtime -- Controller Manager")
        self.setMinimumSize(1100, 580)

        self._build_ui()
        self._populate_table()

        # 1-second auto-refresh so status / cycle counts stay live
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    # ==================================================================
    # UI scaffolding
    # ==================================================================
    def _build_ui(self):
        self._build_menu()
        self._build_toolbar()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Section header strip with filter radios
        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background: {SILVER['bg_secondary']}; "
            f"border-bottom: 1px solid {SILVER['border']}; }}")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(14, 8, 14, 8)
        hlay.setSpacing(20)

        title = QLabel("APC Runtime Controllers")
        title.setStyleSheet(
            f"color: {SILVER['accent_blue']}; font-weight: 700; "
            f"font-size: 11pt; letter-spacing: 1px; "
            f"text-transform: uppercase;")
        hlay.addWidget(title)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: {SILVER['border_accent']};")
        hlay.addWidget(sep)

        # Filter radio buttons (Aspen Watch Maker has ACO / RTE / IQ /
        # Tag Groups / GDOT). We have one source today so the radios
        # filter by status instead of by type -- same affordance.
        self._filter_group = QButtonGroup(self)
        for label, key in [
            ("All",       "all"),
            ("Running",   "running"),
            ("Paused",    "paused"),
            ("Stopped",   "stopped"),
            ("Errors",    "errors"),
        ]:
            rb = QRadioButton(label)
            rb.setProperty("filter_key", key)
            if key == "all":
                rb.setChecked(True)
            rb.toggled.connect(self._on_filter_changed)
            self._filter_group.addButton(rb)
            hlay.addWidget(rb)

        hlay.addStretch()
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            f"color: {SILVER['text_secondary']}; font-size: 9pt;")
        hlay.addWidget(self._count_label)

        root.addWidget(header)

        # ── Table ──
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels([c[1] for c in _COLS])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)  # we drive ordering ourselves
        self._table.setShowGrid(True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        hh = self._table.horizontalHeader()
        for i, (_, _, w) in enumerate(_COLS):
            hh.resizeSection(i, w)
        hh.setStretchLastSection(True)
        root.addWidget(self._table, 1)

        # ── Status bar ──
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._sb_label = QLabel("Ready")
        sb.addWidget(self._sb_label)

        if self.rest_url:
            rest_lbl = QLabel(f"REST: {self.rest_url}")
            rest_lbl.setStyleSheet(f"color: {SILVER['text_muted']};")
            sb.addPermanentWidget(rest_lbl)
        if self.historian_url:
            hist_lbl = QLabel(f"Historian: {self.historian_url}")
            hist_lbl.setStyleSheet(f"color: {SILVER['text_muted']};")
            sb.addPermanentWidget(hist_lbl)

    # ------------------------------------------------------------------
    def _build_menu(self):
        mb = self.menuBar()

        # ── File ──
        fm = mb.addMenu("&File")
        new_act = QAction("&New Workspace", self)
        new_act.setShortcut(QKeySequence.New)
        new_act.triggered.connect(self._on_new_workspace)
        fm.addAction(new_act)

        add_act = QAction("&Add Controller...", self)
        add_act.setShortcut("Ctrl+A")
        add_act.triggered.connect(self._on_add_controller)
        fm.addAction(add_act)

        rem_act = QAction("&Remove Selected", self)
        rem_act.setShortcut(QKeySequence.Delete)
        rem_act.triggered.connect(self._on_remove_controller)
        fm.addAction(rem_act)

        fm.addSeparator()

        exit_act = QAction("E&xit", self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)
        fm.addAction(exit_act)

        # ── Actions ──
        am = mb.addMenu("&Actions")

        start_act = QAction("&Start", self)
        start_act.setShortcut("Ctrl+R")
        start_act.triggered.connect(self._on_start_selected)
        am.addAction(start_act)

        stop_act = QAction("S&top", self)
        stop_act.setShortcut("Ctrl+T")
        stop_act.triggered.connect(self._on_stop_selected)
        am.addAction(stop_act)

        pause_act = QAction("&Pause", self)
        pause_act.triggered.connect(self._on_pause_selected)
        am.addAction(pause_act)

        resume_act = QAction("Res&ume", self)
        resume_act.triggered.connect(self._on_resume_selected)
        am.addAction(resume_act)

        am.addSeparator()

        start_all = QAction("Start &All", self)
        start_all.triggered.connect(self._on_start_all)
        am.addAction(start_all)

        stop_all = QAction("Stop A&ll", self)
        stop_all.triggered.connect(self._on_stop_all)
        am.addAction(stop_all)

        am.addSeparator()

        refresh_act = QAction("&Refresh", self)
        refresh_act.setShortcut("F5")
        refresh_act.triggered.connect(self._refresh)
        am.addAction(refresh_act)

        # ── Tools ──
        tm = mb.addMenu("&Tools")

        if self.rest_url:
            rest_act = QAction("Open REST in &Browser", self)
            rest_act.triggered.connect(
                lambda: webbrowser.open(self.rest_url))
            tm.addAction(rest_act)

        if self.historian_url:
            hist_act = QAction("Open &Historian in Browser", self)
            hist_act.triggered.connect(
                lambda: webbrowser.open(self.historian_url))
            tm.addAction(hist_act)

        tm.addSeparator()

        reveal_act = QAction("Reveal Run &Folder", self)
        reveal_act.triggered.connect(self._on_reveal_run_folder)
        tm.addAction(reveal_act)

        # ── Help ── (shared menu from azeoapc.theme.help_menu)
        from azeoapc.theme.help_menu import build_help_menu
        build_help_menu(mb, "runtime", self,
                         include_mpc_theory=True,
                         include_ident_theory=False)

    # ------------------------------------------------------------------
    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(self.iconSize())  # text-only is fine
        tb.setStyleSheet(
            f"QToolBar {{ background: {SILVER['bg_header']}; "
            f"border-bottom: 1px solid {SILVER['border']}; "
            f"padding: 4px; spacing: 6px; }}"
            f"QToolButton {{ padding: 4px 12px; "
            f"color: {SILVER['text_primary']}; }}"
            f"QToolButton:hover {{ background: {SILVER['bg_panel']}; "
            f"border: 1px solid {SILVER['accent_blue']}; }}"
        )
        self.addToolBar(tb)

        for label, slot in [
            ("New",     self._on_new_workspace),
            ("Open",    self._on_open_workspace),
            ("Add",     self._on_add_controller),
            ("Remove",  self._on_remove_controller),
            (None, None),
            ("Start",   self._on_start_selected),
            ("Stop",    self._on_stop_selected),
            ("Pause",   self._on_pause_selected),
            ("Resume",  self._on_resume_selected),
            (None, None),
            ("Refresh", self._refresh),
        ]:
            if label is None:
                tb.addSeparator()
                continue
            act = QAction(label, self)
            act.triggered.connect(slot)
            tb.addAction(act)

    # ==================================================================
    # Table population
    # ==================================================================
    def _populate_table(self):
        """Drop all rows and rebuild from the current MultiRunner state."""
        self._table.setRowCount(0)
        for key, runner in self.multi.runners.items():
            self._append_row(key, runner)
        self._refresh()
        self._update_count()

    def _append_row(self, key: str, runner: Runner):
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Stash the key on the first cell so we can recover it on
        # selection changes.
        name_item = QTableWidgetItem(key)
        name_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
        name_item.setData(Qt.UserRole, key)
        self._table.setItem(row, 0, name_item)

        for c in range(1, len(_COLS)):
            self._table.setItem(row, c, QTableWidgetItem("-"))

    def _refresh(self):
        """Pull a fresh snapshot from every runner and update each row."""
        # Detect added / removed controllers between refreshes
        seen_keys = set()
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item is not None:
                seen_keys.add(item.data(Qt.UserRole))

        live_keys = set(self.multi.runners.keys())
        added = live_keys - seen_keys
        removed = seen_keys - live_keys

        for key in added:
            self._append_row(key, self.multi.runners[key])

        if removed:
            # Drop rows for removed controllers (iterate from bottom)
            for r in range(self._table.rowCount() - 1, -1, -1):
                item = self._table.item(r, 0)
                if item is None:
                    continue
                if item.data(Qt.UserRole) in removed:
                    self._table.removeRow(r)

        # Update each remaining row
        for r in range(self._table.rowCount()):
            key = self._table.item(r, 0).data(Qt.UserRole)
            runner = self.multi.runners.get(key)
            if runner is None:
                continue
            self._update_row(r, key, runner)

        self._apply_filter()
        self._update_count()

    def _update_row(self, row: int, key: str, runner: Runner):
        snap = runner.snapshot()

        # Model type comes from the engine's plant class
        model_type = "—"
        if runner.engine is not None and runner.engine.cfg.plant is not None:
            cls = type(runner.engine.cfg.plant).__name__
            model_type = {
                "StateSpacePlant": "SS",
                "FOPTDPlant": "FOPTD",
                "NonlinearPlant": "NL",
            }.get(cls, cls)

        last_run = snap.started_at or "—"
        avail = "YES" if snap.status == "RUNNING" else "NO"
        reason = snap.last_error if snap.last_error else (
            "OK" if snap.status == "RUNNING" else snap.status.title())

        cells = [
            (1, snap.status, _STATUS_COLOR.get(snap.status)),
            (2, model_type, None),
            (3, last_run, None),
            (4, str(snap.cycle), None),
            (5, f"{snap.last_cycle_ms:.1f} ms" if snap.last_cycle_ms else "—", None),
            (6, f"{snap.avg_cycle_ms:.1f} ms" if snap.avg_cycle_ms else "—", None),
            (7, avail,
                SILVER["accent_green"] if avail == "YES" else None),
            (8, reason,
                SILVER["accent_red"] if snap.last_error else None),
        ]
        for col, text, color in cells:
            item = self._table.item(row, col)
            if item is None:
                item = QTableWidgetItem(text)
                self._table.setItem(row, col, item)
            else:
                item.setText(text)
            if color is not None:
                item.setForeground(QColor(color))
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            else:
                item.setForeground(QColor(SILVER["text_primary"]))

    def _apply_filter(self):
        rb = self._filter_group.checkedButton()
        if rb is None:
            return
        key = rb.property("filter_key")
        for r in range(self._table.rowCount()):
            status_item = self._table.item(r, 1)
            status = status_item.text() if status_item else ""
            visible = (
                key == "all" or
                (key == "running" and status == "RUNNING") or
                (key == "paused" and status == "PAUSED") or
                (key == "stopped" and status in ("STOPPED", "IDLE")) or
                (key == "errors" and status == "ERROR")
            )
            self._table.setRowHidden(r, not visible)

    def _update_count(self):
        n_total = self._table.rowCount()
        n_running = sum(
            1 for r in range(n_total)
            if self._table.item(r, 1)
            and self._table.item(r, 1).text() == "RUNNING"
        )
        self._count_label.setText(
            f"{n_total} controller(s)  |  {n_running} running")

    def _on_filter_changed(self):
        self._apply_filter()

    def _on_selection_changed(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._sb_label.setText("Ready")
            return
        key = self._table.item(rows[0].row(), 0).data(Qt.UserRole)
        runner = self.multi.runners.get(key)
        if runner is None:
            return
        snap = runner.snapshot()
        bits = [
            f"{key}",
            f"status={snap.status}",
            f"cycle={snap.cycle}",
            f"total={snap.total_cycles}",
        ]
        if snap.project_path:
            bits.append(os.path.basename(snap.project_path))
        self._sb_label.setText("  |  ".join(bits))

    # ==================================================================
    # Selection helpers
    # ==================================================================
    def _selected_runner(self) -> Optional[Runner]:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        key = self._table.item(rows[0].row(), 0).data(Qt.UserRole)
        return self.multi.runners.get(key)

    def _selected_key(self) -> Optional[str]:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._table.item(rows[0].row(), 0).data(Qt.UserRole)

    # ==================================================================
    # File menu / toolbar handlers
    # ==================================================================
    def _on_new_workspace(self):
        running = [r for r in self.multi.runners.values() if r.is_running()]
        if running:
            reply = QMessageBox.question(
                self, "New Workspace",
                f"{len(running)} controller(s) are running. Stop them all "
                "and start a fresh workspace?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return
            self.multi.stop_all(join_timeout=5.0)
        self.multi.runners.clear()
        self._populate_table()
        self.statusBar().showMessage("New workspace", 3000)

    def _on_open_workspace(self):
        # Open is conceptually the same as Add Controller for our
        # single-database design -- pick a .apcproj and load it.
        self._on_add_controller()

    def _on_add_controller(self):
        examples = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "apc_architect", "examples")
        start_dir = examples if os.path.isdir(examples) else os.getcwd()
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Controller", start_dir,
            "Controller (*.apcproj *.yaml *.yml);;All Files (*)")
        if not path:
            return
        self._add_controller_from_path(path)

    def _add_controller_from_path(self, path: str):
        if not os.path.exists(path):
            QMessageBox.warning(
                self, "Add Controller", f"File not found:\n{path}")
            return
        # Build a fresh Runner and slot it into MultiRunner under a
        # unique key derived from the file basename.
        slug = os.path.splitext(os.path.basename(path))[0]
        key = self.multi._unique_key(slug) if hasattr(
            self.multi, "_unique_key") else slug

        try:
            runner = Runner(
                project_path=path,
                run_dir=os.path.join(self.multi.runs_root, key),
                use_embedded_server=True,
                enable_historian=True,
                historian_url=self.historian_url,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Add Controller",
                f"Could not build Runner:\n{type(e).__name__}: {e}")
            return

        self.multi.runners[key] = runner
        self._refresh()
        self.statusBar().showMessage(
            f"Added controller '{key}' from {os.path.basename(path)}",
            5000,
        )

    def _on_remove_controller(self):
        runner = self._selected_runner()
        key = self._selected_key()
        if runner is None or key is None:
            return
        if runner.is_running():
            reply = QMessageBox.question(
                self, "Remove Controller",
                f"'{key}' is still running. Stop and remove it?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return
            runner.stop(join_timeout=5.0)
        self.multi.runners.pop(key, None)
        self._refresh()
        self.statusBar().showMessage(f"Removed '{key}'", 4000)

    # ==================================================================
    # Action handlers
    # ==================================================================
    def _on_start_selected(self):
        runner = self._selected_runner()
        if runner is None:
            return
        runner.start()
        self.statusBar().showMessage(
            f"Started '{self._selected_key()}'", 3000)

    def _on_stop_selected(self):
        runner = self._selected_runner()
        if runner is None:
            return
        runner.stop(join_timeout=5.0)
        self.statusBar().showMessage(
            f"Stopped '{self._selected_key()}'", 3000)

    def _on_pause_selected(self):
        runner = self._selected_runner()
        if runner is None:
            return
        runner.pause()

    def _on_resume_selected(self):
        runner = self._selected_runner()
        if runner is None:
            return
        runner.resume()

    def _on_start_all(self):
        self.multi.start_all()
        self.statusBar().showMessage(
            f"Started {len(self.multi.runners)} controller(s)", 4000)

    def _on_stop_all(self):
        self.multi.stop_all(join_timeout=5.0)
        self.statusBar().showMessage(
            f"Stopped {len(self.multi.runners)} controller(s)", 4000)

    def _on_reveal_run_folder(self):
        runner = self._selected_runner()
        path = (runner.run_dir if runner is not None
                else self.multi.runs_root)
        if not os.path.exists(path):
            QMessageBox.information(
                self, "Reveal", f"Folder does not exist yet:\n{path}")
            return
        try:
            import sys
            import subprocess
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "Reveal", str(e))

    def _on_about(self):
        QMessageBox.about(
            self, "About APC Runtime",
            "<h3>APC Runtime</h3>"
            "<p>Headless production controller cycle loop with a "
            "desktop manager (Aspen Watch Maker style).</p>"
            "<p>Each row in the table is one Runner that owns a "
            "SimEngine + cycle thread. Start / Stop / Pause / Resume "
            "drive the worker thread directly; the REST surface and "
            "historian forwarder are still active in the background "
            "for apc_manager to talk to.</p>"
            "<p>Azeotrope APC v0.1.0</p>",
        )

    # ==================================================================
    def closeEvent(self, event):
        running = [r for r in self.multi.runners.values() if r.is_running()]
        if running:
            reply = QMessageBox.question(
                self, "Stop runners?",
                f"{len(running)} controller(s) are still running. "
                "Stop them before exiting?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Yes:
                self.multi.stop_all(join_timeout=10.0)
        super().closeEvent(event)
