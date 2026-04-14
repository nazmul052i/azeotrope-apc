"""APC Ident main window -- modern sidebar layout with workflow wizard.

Uses a vertical sidebar for navigation instead of top tabs, following
the INCA Discovery / modern APC tool paradigm. The sidebar shows
workflow steps with done/current/pending indicators.

ISA-101 Silver theme with white plot backgrounds.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from azeoapc.identification import (
    IdentProject, IdentProjectMetadata, PROJECT_EXT,
    load_ident_project, save_ident_project,
)

from .recent_files import RecentFiles
from .session import IdentSession
from .sidebar import Sidebar
from .tabs import (
    AnalysisTab, DataTab, IdentificationTab, ResultsTab, TagsTab,
    ValidationTab,
)

# Step ID -> tab index mapping
_STEP_INDEX = {
    "data": 0, "tags": 1, "ident": 2,
    "results": 3, "analysis": 4, "validate": 5,
}


class MainWindow(QMainWindow):
    """Top-level apc_ident window."""

    def __init__(self, project: Optional[IdentProject] = None, parent=None):
        super().__init__(parent)
        # The session owns BOTH the persisted project state AND the
        # transient runtime state (loaded df, last ident result, etc).
        self.session = IdentSession(project=project or IdentProject())
        self.project: Optional[IdentProject] = project
        self._dirty: bool = False
        self._recent = RecentFiles(max_entries=10)

        self.setMinimumSize(1400, 850)
        self.setAcceptDrops(True)
        # Theme installed at the QApplication level by app.py via
        # azeoapc.theme.apply_theme; no per-window setStyleSheet
        # needed.

        # Tab references populated by _build_tabs
        self.data_tab: Optional[DataTab] = None
        self.tags_tab: Optional[TagsTab] = None
        self.ident_tab: Optional[IdentificationTab] = None
        self.results_tab: Optional[ResultsTab] = None
        self.analysis_tab: Optional[AnalysisTab] = None
        self.validation_tab: Optional[ValidationTab] = None

        self._build_ui()
        self._build_menu()
        # Always create a real project (never None) so tabs render
        if self.project is None:
            self.project = IdentProject(
                metadata=IdentProjectMetadata(name="New Project"))
            self.session.project = self.project
        self._build_tabs(self.project)
        self._refresh_window_title()
        self._restore_window_state()

    # ==================================================================
    # UI scaffolding
    # ==================================================================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar navigation ──
        self.sidebar = Sidebar()
        self.sidebar.step_clicked.connect(self._on_sidebar_step)
        self.sidebar.context_requested.connect(self._show_step_context_menu)
        self.sidebar.file_remove_requested.connect(self._on_file_remove)
        self.sidebar.file_rename_requested.connect(self._on_file_rename)
        self.sidebar.file_export_requested.connect(self._on_file_export)
        self.sidebar.file_reveal_requested.connect(self._on_file_reveal)
        root.addWidget(self.sidebar)

        # ── Stacked content area ──
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        root.addWidget(self.stack, 1)

        # Keep outer_tabs as an alias for backwards compat with tab-switching code
        self.outer_tabs = self.stack

        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    def _on_sidebar_step(self, step_id: str):
        """Navigate to the panel for the clicked sidebar step."""
        idx = _STEP_INDEX.get(step_id, 0)
        if idx < self.stack.count():
            self.stack.setCurrentIndex(idx)
            self._on_page_changed(idx)

    def _show_step_context_menu(self, step_id: str, global_pos):
        """Build and show context menu for a sidebar step, directly in MainWindow."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #EBECF1; color: #1A1C24; "
            "border: 1px solid #9AA5B4; }"
            "QMenu::item { padding: 5px 24px 5px 12px; }"
            "QMenu::item:selected { background: #2B5EA7; color: white; }"
            "QMenu::separator { height: 1px; background: #C8CDD8; margin: 4px 8px; }")

        if step_id == "data":
            menu.addAction("Load CSV / Parquet...").triggered.connect(
                lambda: self._ctx_load_data())
            menu.addAction("Import DMC Vectors (.vec)...").triggered.connect(
                lambda: self._ctx_import_vec())
            menu.addAction("OPC UA Data Acquisition...").triggered.connect(
                lambda: self._open_opc_ua_dialog())
            menu.addAction("Reload Data").triggered.connect(
                lambda: self.data_tab._on_reload() if self.data_tab else None)
            menu.addSeparator()
            menu.addAction("Export Conditioned Data...").triggered.connect(
                self._export_conditioned_data)

        elif step_id == "tags":
            menu.addAction("Auto-Assign (MV/CV)").triggered.connect(
                lambda: self.tags_tab._on_auto_assign()
                if self.tags_tab and hasattr(self.tags_tab, '_on_auto_assign') else None)
            menu.addAction("Clear All Assignments").triggered.connect(
                lambda: self.tags_tab._on_clear_all()
                if self.tags_tab and hasattr(self.tags_tab, '_on_clear_all') else None)

        elif step_id == "ident":
            menu.addAction("Smart Config").triggered.connect(
                lambda: self.ident_tab._on_smart_config() if self.ident_tab else None)
            menu.addAction("Run Identification (F5)").triggered.connect(
                lambda: self.ident_tab._on_run() if self.ident_tab else None)
            menu.addSeparator()
            menu.addAction("Run Multi-Trial").triggered.connect(
                lambda: self._ctx_run_multi())

        elif step_id == "results":
            menu.addAction("Build Master Model").triggered.connect(
                lambda: self.results_tab._on_build_master() if self.results_tab else None)
            menu.addSeparator()
            menu.addAction("Export Model Bundle...").triggered.connect(
                lambda: self.results_tab._on_export() if self.results_tab else None)

        elif step_id == "analysis":
            menu.addAction("Run Cross-Correlation").triggered.connect(
                lambda: self.analysis_tab._on_run_xcorr() if self.analysis_tab else None)
            menu.addAction("Run Uncertainty Analysis").triggered.connect(
                lambda: self.analysis_tab._on_run_uncertainty() if self.analysis_tab else None)
            menu.addAction("Run Gain Matrix Analysis").triggered.connect(
                lambda: self.analysis_tab._on_run_gainmatrix() if self.analysis_tab else None)

        elif step_id == "validate":
            menu.addAction("Run Validation").triggered.connect(
                lambda: self.validation_tab._on_run()
                if self.validation_tab and hasattr(self.validation_tab, '_on_run') else None)
            menu.addSeparator()
            menu.addAction("Generate Report (HTML)...").triggered.connect(
                self._on_generate_report)

        if menu.actions():
            menu.exec(global_pos)

    def _update_sidebar_file(self):
        """Update sidebar file tree when data is loaded."""
        # Show all loaded files under Data step
        if self.data_tab and hasattr(self.data_tab, '_loaded_files'):
            self.sidebar.clear_files("data")
            for fpath in self.data_tab._loaded_files:
                self.sidebar.add_file("data", fpath)
        elif self.session.df_path:
            self.sidebar.set_file("data", self.session.df_path)
        # Also show bundle under results if it exists
        if self.session.project.last_bundle_path:
            self.sidebar.set_file("results", self.session.project.last_bundle_path)

    # ==================================================================
    # File tree actions
    # ==================================================================
    def _on_file_remove(self, filepath: str):
        """Remove a loaded file from the project."""
        if not self.data_tab:
            return

        # Remove from loaded files list
        if filepath in self.data_tab._loaded_files:
            self.data_tab._loaded_files.remove(filepath)

        # If it was the only file, clear everything
        if not self.data_tab._loaded_files:
            self.session.df = None
            self.session.df_path = None
            self.session.project.data_source_path = ""
            self.sidebar.clear_files("data")
            self.data_tab._refresh_from_session()
            self.data_tab.data_loaded.emit()
            self.statusBar().showMessage("File removed", 3000)
            return

        # Reload remaining files from scratch
        self.session.df = None
        remaining = list(self.data_tab._loaded_files)
        self.data_tab._loaded_files.clear()
        for fpath in remaining:
            try:
                self.data_tab._load_path(fpath)
            except Exception:
                pass

        self.statusBar().showMessage(
            f"Removed {os.path.basename(filepath)}", 3000)

    def _on_file_rename(self, filepath: str):
        """Rename a loaded file on disk."""
        from PySide6.QtWidgets import QInputDialog
        old_name = os.path.basename(filepath)
        new_name, ok = QInputDialog.getText(
            self, "Rename File", "New filename:", text=old_name)
        if not ok or not new_name.strip() or new_name == old_name:
            return
        new_name = new_name.strip()
        new_path = os.path.join(os.path.dirname(filepath), new_name)
        try:
            os.rename(filepath, new_path)
        except Exception as e:
            QMessageBox.critical(self, "Rename", f"Failed:\n{e}")
            return
        # Update tracked paths
        if self.data_tab and hasattr(self.data_tab, '_loaded_files'):
            idx = None
            for i, fp in enumerate(self.data_tab._loaded_files):
                if fp == filepath:
                    idx = i
                    break
            if idx is not None:
                self.data_tab._loaded_files[idx] = new_path
        if self.session.df_path == filepath:
            self.session.df_path = new_path
        if self.session.project.data_source_path == filepath:
            self.session.project.data_source_path = new_path
        self._update_sidebar_file()
        self.statusBar().showMessage(f"Renamed to {new_name}", 3000)

    def _on_file_export(self, filepath: str):
        """Export data from a loaded file to CSV."""
        df = self.session.df
        if df is None:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export Data", "",
            "CSV Files (*.csv);;All Files (*)")
        if save_path:
            df.to_csv(save_path)
            self.statusBar().showMessage(f"Exported: {save_path}", 3000)

    def _on_file_reveal(self, filepath: str):
        """Open file manager at the file location."""
        if not os.path.exists(filepath):
            QMessageBox.warning(self, "Reveal", "File not found.")
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(filepath)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", filepath])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(filepath)])
        except Exception as e:
            QMessageBox.warning(self, "Reveal", f"Could not open:\n{e}")

    def _open_opc_ua_dialog(self):
        """Open OPC UA data acquisition dialog."""
        from .opc_ua_dialog import OpcUaDialog
        dlg = OpcUaDialog(self)
        dlg.data_collected.connect(self._on_opc_data_collected)
        dlg.exec()

    def _on_opc_data_collected(self, df, save_path: str):
        """Handle data from OPC UA collection."""
        if df is None or len(df) == 0:
            return
        # Store as session data
        self.session.df = df
        self.session.df_path = save_path or "(OPC UA live collection)"
        if self.data_tab:
            if save_path:
                self.data_tab._loaded_files.append(save_path)
            else:
                self.data_tab._loaded_files.append("(OPC UA)")
            self.data_tab._refresh_from_session()
            self.data_tab.data_loaded.emit()
            self.data_tab.config_changed.emit()
        self._update_sidebar_file()
        self.statusBar().showMessage(
            f"OPC UA: {len(df)} samples, {len(df.columns)} tags", 5000)

    def _ctx_load_data(self):
        start_dir = self.data_tab._examples_dir() if self.data_tab else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Step-Test Data", start_dir,
            "CSV (*.csv);;Parquet (*.parquet);;DMC Vector (*.vec);;All (*)")
        if path and self.data_tab:
            self.data_tab._load_path(path)

    def _ctx_import_vec(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import DMC Vectors", "",
            "DMC Vectors (*.vec *.dep *.ind);;All Files (*)")
        if path and self.data_tab:
            self.data_tab._load_path(path)

    def _ctx_run_multi(self):
        if self.ident_tab:
            self.ident_tab.chk_multi_trial.setChecked(True)
            self.ident_tab._on_run()

    def _export_conditioned_data(self):
        """Export conditioned data to CSV."""
        if self.session.cond_result is None:
            QMessageBox.information(self, "Export", "Run conditioning first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Conditioned Data", "",
            "CSV Files (*.csv);;All Files (*)")
        if not path:
            return
        if self.session.cond_result.df_clean is not None:
            self.session.cond_result.df_clean.to_csv(path)
            self.statusBar().showMessage(f"Exported: {path}", 3000)

    # ==================================================================
    # Menu
    # ==================================================================
    def _build_menu(self):
        menubar = self.menuBar()

        # ── File ──
        file_menu = menubar.addMenu("&File")

        new_act = QAction("&New Project", self)
        new_act.setShortcut(QKeySequence.New)
        new_act.triggered.connect(self._on_new_project)
        file_menu.addAction(new_act)

        open_act = QAction("&Open Project...", self)
        open_act.setShortcut(QKeySequence.Open)
        open_act.triggered.connect(self._on_open_project)
        file_menu.addAction(open_act)

        self._recent_menu = QMenu("Open &Recent", self)
        file_menu.addMenu(self._recent_menu)
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        save_act = QAction("&Save", self)
        save_act.setShortcut(QKeySequence.Save)
        save_act.triggered.connect(self._on_save)
        file_menu.addAction(save_act)

        save_as_act = QAction("Save &As...", self)
        save_as_act.setShortcut(QKeySequence.SaveAs)
        save_as_act.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_act)

        file_menu.addSeparator()

        reveal_act = QAction("Re&veal in File Manager", self)
        reveal_act.triggered.connect(self._on_reveal)
        file_menu.addAction(reveal_act)

        file_menu.addSeparator()

        exit_act = QAction("E&xit", self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # ── View ──
        view_menu = menubar.addMenu("&View")
        for i, (label, shortcut) in enumerate([
            ("&Data Tab",            "Ctrl+1"),
            ("&Tags Tab",            "Ctrl+2"),
            ("&Identification Tab",  "Ctrl+3"),
            ("&Results Tab",         "Ctrl+4"),
            ("&Analysis Tab",        "Ctrl+5"),
            ("&Validation Tab",      "Ctrl+6"),
        ]):
            act = QAction(label, self)
            act.setShortcut(shortcut)
            act.triggered.connect(
                lambda _=False, idx=i: self._navigate_to_index(idx))
            view_menu.addAction(act)

        # ── Tools ──
        tools_menu = menubar.addMenu("&Tools")

        run_act = QAction("&Run Identification", self)
        run_act.setShortcut("F5")
        run_act.triggered.connect(self._on_run_shortcut)
        tools_menu.addAction(run_act)

        smart_act = QAction("&Smart Config", self)
        smart_act.setShortcut("Ctrl+Shift+S")
        smart_act.triggered.connect(self._on_smart_shortcut)
        tools_menu.addAction(smart_act)

        tools_menu.addSeparator()

        report_act = QAction("Generate &Report...", self)
        report_act.setShortcut("Ctrl+Shift+R")
        report_act.triggered.connect(self._on_generate_report)
        tools_menu.addAction(report_act)

        # ── Help ──
        help_menu = menubar.addMenu("&Help")

        help_act = QAction("&Help Topics (F1)", self)
        help_act.setShortcut("F1")
        help_act.triggered.connect(self._on_help)
        help_menu.addAction(help_act)

        theory_act = QAction("Identification &Theory", self)
        theory_act.triggered.connect(lambda: self._show_help("theory_fir"))
        help_menu.addAction(theory_act)

        ss_theory_act = QAction("&Subspace Theory", self)
        ss_theory_act.triggered.connect(lambda: self._show_help("theory_subspace"))
        help_menu.addAction(ss_theory_act)

        help_menu.addSeparator()

        about_act = QAction("&About APC Ident", self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

    # ------------------------------------------------------------------
    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        paths = self._recent.get()
        if not paths:
            empty = QAction("(no recent projects)", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for p in paths:
            label = os.path.basename(p)
            act = QAction(label, self)
            act.setToolTip(p)
            act.triggered.connect(lambda _=False, path=p: self._open_path(path))
            self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        clear = QAction("Clear Recent List", self)
        clear.triggered.connect(self._on_clear_recent)
        self._recent_menu.addAction(clear)

    # ==================================================================
    # Tab construction
    # ==================================================================
    def _build_tabs(self, project: Optional[IdentProject]):
        # Clear existing stacked widgets
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()

        if project is None:
            for _ in range(6):
                self.stack.addWidget(QWidget())
            self.data_tab = self.tags_tab = self.ident_tab = None
            self.results_tab = self.analysis_tab = self.validation_tab = None
            self.sidebar.set_current("data")
            return

        # Reset live runtime state on every (re)build
        self.session.project = project
        self.session.reset()

        self.data_tab = DataTab(self.session)
        self.tags_tab = TagsTab(self.session)
        self.ident_tab = IdentificationTab(self.session)
        self.results_tab = ResultsTab(self.session)
        self.analysis_tab = AnalysisTab(self.session)
        self.validation_tab = ValidationTab(self.session)

        all_tabs = (self.data_tab, self.tags_tab, self.ident_tab,
                    self.results_tab, self.analysis_tab, self.validation_tab)

        # ── Dirty tracking ──
        for tab in all_tabs:
            if hasattr(tab, "config_changed"):
                tab.config_changed.connect(self._mark_dirty)

        # ── Cross-tab refresh signals ──
        self.data_tab.data_loaded.connect(self.tags_tab.refresh_from_data)
        self.data_tab.data_loaded.connect(
            lambda: self.sidebar.mark_done("data"))
        self.data_tab.data_loaded.connect(self._update_sidebar_file)
        self.tags_tab.config_changed.connect(self.ident_tab.refresh_cv_types)
        self.ident_tab.ident_completed.connect(
            self.results_tab.on_ident_completed)
        self.ident_tab.ident_completed.connect(
            self.analysis_tab.on_ident_completed)
        self.ident_tab.ident_completed.connect(
            self.validation_tab.on_ident_completed)
        # Auto-jump to Results + mark steps done
        self.ident_tab.ident_completed.connect(
            lambda _r: self._navigate_to("results"))
        self.ident_tab.ident_completed.connect(
            lambda _r: self.sidebar.mark_done("ident"))

        # Add to stacked widget (order must match _STEP_INDEX)
        self.stack.addWidget(self.data_tab)       # 0
        self.stack.addWidget(self.tags_tab)        # 1
        self.stack.addWidget(self.ident_tab)       # 2
        self.stack.addWidget(self.results_tab)     # 3
        self.stack.addWidget(self.analysis_tab)    # 4
        self.stack.addWidget(self.validation_tab)  # 5
        self.stack.setCurrentIndex(0)
        self.sidebar.set_current("data")

        # Project reload hook
        for tab in all_tabs:
            if hasattr(tab, "on_project_loaded"):
                tab.on_project_loaded()
        self._dirty = False
        self._refresh_window_title()

        # Show loaded file in sidebar tree
        if self.session.df_path:
            self.sidebar.set_file("data", self.session.df_path)
        if self.session.project.last_bundle_path:
            self.sidebar.set_file("results", self.session.project.last_bundle_path)

    def _navigate_to(self, step_id: str):
        """Navigate to a step by ID."""
        idx = _STEP_INDEX.get(step_id, 0)
        self._navigate_to_index(idx)
        self.sidebar.set_current(step_id)

    def _navigate_to_index(self, idx: int):
        """Navigate to a step by index."""
        if idx < self.stack.count():
            self.stack.setCurrentIndex(idx)
            # Find step_id from index
            reverse = {v: k for k, v in _STEP_INDEX.items()}
            step_id = reverse.get(idx, "data")
            self.sidebar.set_current(step_id)
            self._on_page_changed(idx)

    def _on_page_changed(self, index: int):
        """Update status bar and trigger tab-specific hooks."""
        widget = self.stack.widget(index) if index < self.stack.count() else None
        if widget is self.validation_tab and self.validation_tab is not None:
            self.validation_tab.on_tab_activated()

        step_names = ["Data", "Tags", "Identify", "Results",
                      "Analysis", "Validate"]
        if 0 <= index < len(step_names):
            msg = f"{tab_names[index]} tab"
            if self.session.has_data():
                df = self.session.df
                msg += f"  |  {len(df):,} rows x {len(df.columns)} cols"
            if self.session.has_ident():
                msg += "  |  Model identified"
            self.statusBar().showMessage(msg)

    # ==================================================================
    # Tool shortcuts
    # ==================================================================
    def _on_run_shortcut(self):
        """F5 -> run identification."""
        if self.ident_tab is not None:
            self._navigate_to("ident")
            self.ident_tab._on_run()

    def _on_smart_shortcut(self):
        """Ctrl+Shift+S -> smart config."""
        if self.ident_tab is not None:
            self._navigate_to("ident")
            self.ident_tab._on_smart_config()

    def _on_generate_report(self):
        """Generate an HTML identification report."""
        try:
            from azeoapc.identification.report_generator import (
                generate_html_report, save_report,
            )
        except ImportError:
            QMessageBox.information(
                self, "Report",
                "Report generator module not available yet.")
            return

        result = self.session.ident_result
        if result is None:
            QMessageBox.information(
                self, "Report",
                "Run identification first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Report", "",
            "HTML Files (*.html);;All Files (*)")
        if not path:
            return
        if not path.endswith(".html"):
            path += ".html"

        try:
            html = generate_html_report(
                project=self.session.project,
                ident_result=result,
                cond_result=self.session.cond_result,
            )
            save_report(html, path)
            QMessageBox.information(
                self, "Report", f"Report saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(
                self, "Report", f"Failed:\n{e}")

    def _on_help(self):
        """F1 context-sensitive help."""
        from .help_viewer import show_help, context_help_for_step
        # Determine current step
        idx = self.stack.currentIndex()
        reverse = {v: k for k, v in _STEP_INDEX.items()}
        step_id = reverse.get(idx, "data")
        topic = context_help_for_step(step_id)
        show_help(self, topic)

    def _show_help(self, topic: str):
        """Show help for a specific topic."""
        from .help_viewer import show_help
        show_help(self, topic)

    def _on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self, "About APC Ident",
            "<h2>Azeotrope APC Ident</h2>"
            "<p>Version 0.1.0</p>"
            "<p>Step-test model identification studio for "
            "Advanced Process Control.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>FIR identification (DLS / COR / Ridge)</li>"
            "<li>Subspace identification (N4SID / MOESP / CVA)</li>"
            "<li>18 DMC3-style curve operations</li>"
            "<li>Model assembly with multi-trial comparison</li>"
            "<li>Smart auto-configuration</li>"
            "<li>Model quality scorecard</li>"
            "<li>Cross-correlation, uncertainty, gain matrix analysis</li>"
            "</ul>"
            "<p>&copy; 2026 Azeotrope Process Control</p>"
        )

    # ==================================================================
    # Dirty tracking + window title
    # ==================================================================
    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self._refresh_window_title()

    def _mark_clean(self):
        if self._dirty:
            self._dirty = False
            self._refresh_window_title()

    def _refresh_window_title(self):
        if self.project is None:
            self.setWindowTitle("APC Ident -- No Project")
            return
        name = self.project.metadata.name or "Untitled"
        marker = " *" if self._dirty else ""
        path = self.project.source_path
        if path:
            base = os.path.basename(path)
            self.setWindowTitle(f"APC Ident -- {name}{marker} -- {base}")
        else:
            self.setWindowTitle(f"APC Ident -- {name}{marker} (unsaved)")

    # ==================================================================
    # File menu handlers
    # ==================================================================
    def _on_new_project(self):
        if not self._prompt_save_if_dirty():
            return
        proj = IdentProject()
        proj.metadata = IdentProjectMetadata(name="Untitled Project")

        # C5.4: pre-populate from the bundled example so a fresh
        # New Project lands the user on real data instead of empty
        # tabs. The example is the same 1500-row 2x2 step test we
        # ship with the studio.
        sample = self._sample_csv_path()
        if sample and os.path.exists(sample):
            proj.data_source_path = sample
            self._apply_sample_defaults(proj)

        self.project = proj
        self._build_tabs(proj)
        self._mark_dirty()
        self._refresh_window_title()
        if sample and os.path.exists(sample):
            self.statusBar().showMessage(
                f"New project pre-loaded with {os.path.basename(sample)}",
                4000)
        else:
            self.statusBar().showMessage("New project created", 3000)

    @staticmethod
    def _sample_csv_path() -> str:
        """Locate the bundled example step-test CSV."""
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(here, "examples", "cdu_step_test.csv")

    @staticmethod
    def _apply_sample_defaults(proj: IdentProject):
        """Pre-fill segment + tag bindings + identification config to
        match the bundled example. Lets the user click Identify in the
        Identification tab within ten seconds of File > New."""
        from azeoapc.identification import (
            ConditioningConfig, IdentConfig, IdentMethod, Segment,
            SmoothMethod, TagAssignment,
        )
        proj.tag_assignments = [
            TagAssignment("FIC101_SP", "MV", "FIC-101.SP"),
            TagAssignment("FIC102_SP", "MV", "FIC-102.SP"),
            TagAssignment("TI201_PV",  "CV", "TI-201.PV"),
            TagAssignment("TI202_PV",  "CV", "TI-202.PV"),
        ]
        # Whole-range segment -- the user can refine in the Data tab
        proj.segments = [Segment(name="full")]
        proj.conditioning = ConditioningConfig(
            clip_sigma=4.0,
            holdout_fraction=0.2,
        )
        proj.ident = IdentConfig(
            n_coeff=60, dt=60.0,
            method=IdentMethod.DLS,
            smooth=SmoothMethod.PIPELINE,
            detrend=True,
            remove_mean=True,
        )

    # ------------------------------------------------------------------
    def _on_open_project(self):
        if not self._prompt_save_if_dirty():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open APC Ident Project", self._default_dir(),
            f"APC Ident Project (*{PROJECT_EXT});;YAML (*.yaml *.yml);;All Files (*)")
        if not path:
            return
        self._open_path(path)

    # ------------------------------------------------------------------
    def _open_path(self, path: str):
        if not os.path.exists(path):
            QMessageBox.warning(
                self, "Open Project", f"File no longer exists:\n{path}")
            self._rebuild_recent_menu()
            return
        try:
            proj = load_ident_project(path)
        except Exception as e:
            QMessageBox.critical(
                self, "Open Project", f"Failed to load project:\n{e}")
            return

        # If the saved project name is still the default or empty,
        # derive a proper name from the filename so the title bar
        # shows something meaningful instead of "Untitled Project".
        if proj.metadata.name in ("Untitled Project", "Untitled", ""):
            stem = os.path.splitext(os.path.basename(path))[0]
            proj.metadata.name = stem.replace("_", " ").title()

        self.project = proj
        self._dirty = False
        self._build_tabs(proj)
        self._refresh_window_title()
        self._recent.add(path)
        self._rebuild_recent_menu()
        self.statusBar().showMessage(
            f"Loaded {os.path.basename(path)}", 3000)

    # ------------------------------------------------------------------
    def _on_save(self):
        if self.project is None:
            return
        if self.project.source_path is None:
            self._on_save_as()
            return
        self._save_to(self.project.source_path)

    # ------------------------------------------------------------------
    def _on_save_as(self):
        if self.project is None:
            return
        suggested = (self.project.source_path
                     or os.path.join(self._default_dir(),
                                      (self.project.metadata.name or "untitled")
                                      .lower().replace(" ", "_") + PROJECT_EXT))
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", suggested,
            f"APC Ident Project (*{PROJECT_EXT});;YAML (*.yaml *.yml);;All Files (*)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += PROJECT_EXT
        self._save_to(path)

    # ------------------------------------------------------------------
    def _save_to(self, path: str):
        # If the project name is still the default, derive a nicer one
        # from the file basename so the title bar reflects the actual
        # project rather than staying "Untitled Project" forever.
        if self.project.metadata.name in ("Untitled Project", ""):
            stem = os.path.splitext(os.path.basename(path))[0]
            self.project.metadata.name = stem.replace("_", " ").title()

        try:
            save_ident_project(self.project, path)
        except Exception as e:
            QMessageBox.critical(
                self, "Save Project", f"Failed to save:\n{e}")
            return
        self._mark_clean()
        self._refresh_window_title()
        self._recent.add(path)
        self._rebuild_recent_menu()
        self.statusBar().showMessage(
            f"Saved {os.path.basename(path)}", 3000)

    # ------------------------------------------------------------------
    def _on_reveal(self):
        if self.project is None or not self.project.source_path:
            QMessageBox.information(self, "Reveal", "Save the project first.")
            return
        path = self.project.source_path
        if not os.path.exists(path):
            QMessageBox.warning(self, "Reveal", "File no longer exists.")
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        except Exception as e:
            QMessageBox.warning(self, "Reveal",
                                f"Could not open file manager:\n{e}")

    # ------------------------------------------------------------------
    def _on_clear_recent(self):
        self._recent.clear()
        self._rebuild_recent_menu()

    # ------------------------------------------------------------------
    def _default_dir(self) -> str:
        if self.project and self.project.source_path:
            return os.path.dirname(self.project.source_path)
        examples = os.path.join(os.path.dirname(__file__), "examples")
        if os.path.isdir(examples):
            return examples
        return os.getcwd()

    # ------------------------------------------------------------------
    def _prompt_save_if_dirty(self) -> bool:
        if not self._dirty or self.project is None:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            f"'{self.project.metadata.name}' has unsaved changes. "
            "Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if reply == QMessageBox.Cancel:
            return False
        if reply == QMessageBox.Save:
            self._on_save()
            return not self._dirty
        return True

    # ==================================================================
    # Drag and drop
    # ==================================================================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile().lower()
                if path.endswith((".csv", ".parquet", ".apcident",
                                  ".vec", ".dep", ".ind")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        ext = os.path.splitext(path)[1].lower()

        if ext == ".apcident":
            self._open_path(path)
        elif ext in (".csv", ".parquet"):
            # Load as data in the Data tab
            if self.data_tab is not None:
                self.data_tab._load_path(path)
                self._navigate_to("data")
                self.statusBar().showMessage(
                    f"Loaded {os.path.basename(path)}", 3000)
        elif ext in (".vec", ".dep", ".ind"):
            self.statusBar().showMessage(
                f"DMC vector import: {os.path.basename(path)}", 3000)

    # ==================================================================
    # Window lifecycle
    # ==================================================================
    def closeEvent(self, event):
        if not self._prompt_save_if_dirty():
            event.ignore()
            return
        # Save window geometry
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings("Azeotrope", "APC Ident")
            settings.setValue("geometry", self.saveGeometry())
            settings.setValue("windowState", self.saveState())
        except Exception:
            pass
        super().closeEvent(event)

    def _restore_window_state(self):
        """Restore window geometry from settings."""
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings("Azeotrope", "APC Ident")
            geometry = settings.value("geometry")
            state = settings.value("windowState")
            if geometry:
                self.restoreGeometry(geometry)
            if state:
                self.restoreState(state)
        except Exception:
            pass
