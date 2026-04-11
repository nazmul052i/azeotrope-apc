"""APC Ident main window.

Top-level QMainWindow with five tabs (Data / Tags / Identification /
Results / Validation) and a File menu that owns the .apcident project
lifecycle: New, Open, Open Recent, Save, Save As, plus dirty tracking
and a save-on-close prompt.

Mirrors the apc_architect main_window.py shape so future maintenance
stays muscle-memory consistent across the studio apps.
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
    QTabWidget, QVBoxLayout, QWidget,
)

from azeoapc.identification import (
    IdentProject, IdentProjectMetadata, PROJECT_EXT,
    load_ident_project, save_ident_project,
)

from .recent_files import RecentFiles
from .session import IdentSession
from .tabs import (
    DataTab, IdentificationTab, ResultsTab, TagsTab, ValidationTab,
)
from .theme import SILVER, STYLESHEET


_TAB_DEFS = [
    ("data",         "  \u25A4  Data  "),
    ("tags",         "  \u2630  Tags  "),
    ("ident",        "  \u2699  Identification  "),
    ("results",      "  \u25A0  Results  "),
    ("validation",   "  \u2713  Validation  "),
]


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
        # Theme installed at the QApplication level by app.py via
        # azeoapc.theme.apply_theme; no per-window setStyleSheet
        # needed.

        # Tab references populated by _build_tabs
        self.data_tab: Optional[DataTab] = None
        self.tags_tab: Optional[TagsTab] = None
        self.ident_tab: Optional[IdentificationTab] = None
        self.results_tab: Optional[ResultsTab] = None
        self.validation_tab: Optional[ValidationTab] = None

        self._build_ui()
        self._build_menu()
        self._build_tabs(self.project)
        self._refresh_window_title()

    # ==================================================================
    # UI scaffolding
    # ==================================================================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        self.outer_tabs = QTabWidget()
        root.addWidget(self.outer_tabs, 1)

        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    def _build_header(self):
        header = QWidget()
        header.setFixedHeight(38)
        header.setStyleSheet(
            f"background: {SILVER['bg_secondary']}; "
            f"border-bottom: 1px solid {SILVER['border']};")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        icon = QLabel("\u25C6")
        icon.setStyleSheet(
            f"color: {SILVER['accent_blue']}; font-size: 18pt;"
            f" font-weight: bold;")
        lay.addWidget(icon)

        brand = QLabel("APC IDENT")
        brand.setStyleSheet(
            f"color: {SILVER['text_primary']}; font-size: 12pt;"
            f" font-weight: 600; letter-spacing: 1px;")
        lay.addWidget(brand)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 14pt;")
        lay.addWidget(sep)

        self.proj_label = QLabel(
            self.project.metadata.name if self.project else "No project loaded")
        self.proj_label.setStyleSheet(
            f"color: {SILVER['text_secondary']}; font-size: 10pt;"
            f" font-weight: 500;")
        lay.addWidget(self.proj_label)

        lay.addStretch()

        version = QLabel("v0.1.0")
        version.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 8pt;")
        lay.addWidget(version)

        return header

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
            ("&Validation Tab",      "Ctrl+5"),
        ]):
            act = QAction(label, self)
            act.setShortcut(shortcut)
            act.triggered.connect(
                lambda _=False, idx=i: self.outer_tabs.setCurrentIndex(idx))
            view_menu.addAction(act)

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
        # currentChanged is only connected after the first call to
        # _build_tabs that gets a real project; guard the disconnect
        # so the first build doesn't emit a harmless warning.
        if getattr(self, "_tab_changed_connected", False):
            try:
                self.outer_tabs.currentChanged.disconnect(self._on_tab_changed)
            except (RuntimeError, TypeError):
                pass
            self._tab_changed_connected = False

        self.outer_tabs.clear()

        if project is None:
            for _, label in _TAB_DEFS:
                self.outer_tabs.addTab(QWidget(), label)
            self.data_tab = self.tags_tab = self.ident_tab = None
            self.results_tab = self.validation_tab = None
            return

        # Reset live runtime state on every (re)build
        self.session.project = project
        self.session.reset()

        self.data_tab = DataTab(self.session)
        self.tags_tab = TagsTab(self.session)
        self.ident_tab = IdentificationTab(self.session)
        self.results_tab = ResultsTab(self.session)
        self.validation_tab = ValidationTab(self.session)

        # ── Dirty tracking ──
        for tab in (self.data_tab, self.tags_tab, self.ident_tab,
                    self.results_tab, self.validation_tab):
            if hasattr(tab, "config_changed"):
                tab.config_changed.connect(self._mark_dirty)

        # ── Cross-tab refresh signals ──
        # When new data lands, the tag table needs the new columns.
        self.data_tab.data_loaded.connect(self.tags_tab.refresh_from_data)
        # When identification finishes, the results + validation tabs refresh.
        self.ident_tab.ident_completed.connect(
            self.results_tab.on_ident_completed)
        self.ident_tab.ident_completed.connect(
            self.validation_tab.on_ident_completed)
        # Auto-jump to Results when ident finishes successfully.
        self.ident_tab.ident_completed.connect(
            lambda _r: self.outer_tabs.setCurrentIndex(3))

        self.outer_tabs.addTab(self.data_tab,       _TAB_DEFS[0][1])
        self.outer_tabs.addTab(self.tags_tab,       _TAB_DEFS[1][1])
        self.outer_tabs.addTab(self.ident_tab,      _TAB_DEFS[2][1])
        self.outer_tabs.addTab(self.results_tab,    _TAB_DEFS[3][1])
        self.outer_tabs.addTab(self.validation_tab, _TAB_DEFS[4][1])
        self.outer_tabs.setCurrentIndex(0)

        # Tab activation hook (drives auto-validation)
        self.outer_tabs.currentChanged.connect(self._on_tab_changed)
        self._tab_changed_connected = True

        # Project reload hook -- give tabs a chance to populate from
        # the freshly-loaded IdentProject (e.g. auto-load CSV from
        # data_source_path)
        for tab in (self.data_tab, self.tags_tab, self.ident_tab,
                    self.results_tab, self.validation_tab):
            if hasattr(tab, "on_project_loaded"):
                tab.on_project_loaded()
        # Triggering on_project_loaded fires config_changed -- a fresh
        # load is *not* dirty, so reset the marker.
        self._dirty = False
        self._refresh_window_title()

    def _on_tab_changed(self, index: int):
        """Forward activation events to the tab so it can refresh."""
        widget = self.outer_tabs.widget(index)
        if widget is self.validation_tab and self.validation_tab is not None:
            self.validation_tab.on_tab_activated()

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
            self.proj_label.setText("No project loaded")
            return
        name = self.project.metadata.name or "Untitled"
        marker = " *" if self._dirty else ""
        path = self.project.source_path
        if path:
            base = os.path.basename(path)
            self.setWindowTitle(f"APC Ident -- {name}{marker} -- {base}")
        else:
            self.setWindowTitle(f"APC Ident -- {name}{marker} (unsaved)")
        self.proj_label.setText(name + marker)

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
    # Window lifecycle
    # ==================================================================
    def closeEvent(self, event):
        if not self._prompt_save_if_dirty():
            event.ignore()
            return
        super().closeEvent(event)
