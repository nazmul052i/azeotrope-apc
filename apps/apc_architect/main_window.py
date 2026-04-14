"""APC Architect main window.

Top-level QMainWindow with five tabs (Configuration / Optimization /
Calculations / Simulation / Deployment) and a File menu that owns project
lifecycle: New, Open Project, Open Recent, Save, Save As, plus dirty
tracking and a save-on-close prompt.
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

from azeoapc.models.config_loader import (
    SimConfig, load_config, save_config, ProjectMetadata,
)

from .calculations_window import CalculationsWindow
from .configuration_window import ConfigurationWindow
from .deployment_window import DeploymentWindow
from .optimizer_window import OptimizerWindow
from .recent_files import RecentFiles
from .whatif_window import WhatIfSimulator, _STYLE


_TAB_DEFS = [
    ("configuration", "  \u2630  Configuration  "),
    ("optimizer",     "  \u2699  Optimization  "),
    ("calculations",  "  \u0192  Calculations  "),
    ("simulator",     "  \u25B6  Simulation  "),
    ("deployment",    "  \u26A1  Deployment  "),
]


class MainWindow(QMainWindow):
    """Top-level window with five tabs and a File menu owning project lifecycle."""

    def __init__(self, config: Optional[SimConfig] = None, parent=None):
        super().__init__(parent)
        self.cfg: Optional[SimConfig] = config
        self._dirty: bool = False
        self._project_path: Optional[str] = config.source_path if config else None
        self._recent = RecentFiles(max_entries=10)

        self.setMinimumSize(1500, 900)
        # Theme is installed at the QApplication level by app.py via
        # azeoapc.theme.apply_theme; the named-button overrides from
        # whatif's _STYLE are appended there too. No per-window
        # setStyleSheet needed.

        # Tab widget references created in _build_tabs
        self.configuration: Optional[QWidget] = None
        self.optimizer: Optional[QWidget] = None
        self.calculations: Optional[QWidget] = None
        self.simulator: Optional[QWidget] = None
        self.deployment: Optional[QWidget] = None

        self._build_ui()
        self._build_menu()
        self._build_tabs(self.cfg)
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
        self.outer_tabs.setStyleSheet("""
        QTabWidget::pane {
            border: none;
            background: #ECECEC;
        }
        QTabBar::tab {
            background: #D8D8D8;
            color: #404040;
            border: none;
            padding: 10px 32px;
            margin-right: 1px;
            font-size: 11pt;
            font-weight: 600;
            min-width: 140px;
        }
        QTabBar::tab:selected {
            background: #0066CC;
            color: white;
            border-bottom: 3px solid #0066CC;
        }
        QTabBar::tab:hover:!selected {
            background: #E4E4E4;
            color: #1A1A1A;
        }
        """)
        root.addWidget(self.outer_tabs, 1)

    # ------------------------------------------------------------------
    def _build_header(self):
        header = QWidget()
        header.setFixedHeight(38)
        header.setStyleSheet(
            "background: #ECECEC; border-bottom: 1px solid #B0B0B0;")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        icon = QLabel("\u25C6")
        icon.setStyleSheet("color: #0066CC; font-size: 18pt; font-weight: bold;")
        lay.addWidget(icon)

        brand = QLabel("APC ARCHITECT")
        brand.setStyleSheet(
            "color: #1A1A1A; font-size: 12pt; font-weight: 600; "
            "letter-spacing: 1px;")
        lay.addWidget(brand)

        sep = QLabel("|")
        sep.setStyleSheet("color: #B0B0B0; font-size: 14pt;")
        lay.addWidget(sep)

        self.sim_label = QLabel(
            self.cfg.name if self.cfg else "No project loaded")
        self.sim_label.setStyleSheet(
            "color: #404040; font-size: 10pt; font-weight: 500;")
        lay.addWidget(self.sim_label)

        lay.addStretch()

        version = QLabel("v0.1.0")
        version.setStyleSheet("color: #707070; font-size: 8pt;")
        lay.addWidget(version)

        return header

    # ==================================================================
    # Menu
    # ==================================================================
    def _build_menu(self):
        menubar = self.menuBar()
        # Menu chrome comes from the canonical Silver theme installed
        # at the QApplication level by app.py -- no per-window override
        # needed. Removing the local setStyleSheet lets QMenuBar inherit
        # the light DeltaV Live look automatically.

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

        import_act = QAction("&Import Model Bundle...", self)
        import_act.setShortcut("Ctrl+I")
        import_act.setToolTip(
            "Import an .apcmodel bundle exported by APC Ident. "
            "This sets the plant model for the controller.")
        import_act.triggered.connect(self._on_import_bundle)
        file_menu.addAction(import_act)

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
            ("&Configuration Tab", "Ctrl+1"),
            ("&Optimization Tab",  "Ctrl+2"),
            ("Calc&ulations Tab",  "Ctrl+3"),
            ("&Simulation Tab",    "Ctrl+4"),
            ("&Deployment Tab",    "Ctrl+5"),
        ]):
            act = QAction(label, self)
            act.setShortcut(shortcut)
            act.triggered.connect(lambda _=False, idx=i: self.outer_tabs.setCurrentIndex(idx))
            view_menu.addAction(act)

        # ── Help ──
        from azeoapc.theme.help_menu import build_help_menu
        build_help_menu(menubar, "architect", self,
                         include_mpc_theory=True,
                         include_ident_theory=False)

    # ------------------------------------------------------------------
    def _rebuild_recent_menu(self):
        """Repopulate File > Open Recent from QSettings."""
        self._recent_menu.clear()
        paths = self._recent.get()
        if not paths:
            empty = QAction("(no recent projects)", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for p in paths:
            label = os.path.basename(p)
            tooltip = p
            act = QAction(label, self)
            act.setToolTip(tooltip)
            act.triggered.connect(lambda _=False, path=p: self._open_path(path))
            self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        clear = QAction("Clear Recent List", self)
        clear.triggered.connect(self._on_clear_recent)
        self._recent_menu.addAction(clear)

    # ==================================================================
    # Tab construction (used by both __init__ and project open/new)
    # ==================================================================
    def _build_tabs(self, cfg: Optional[SimConfig]):
        """Build the five sub-tabs from a (possibly None) SimConfig.

        Tears down any prior deployment runtime first so we don't leak
        OPC UA threads when reloading.
        """
        # Tear down existing tabs / runtime
        if self.deployment is not None and hasattr(self.deployment, "shutdown"):
            try:
                self.deployment.shutdown()
            except Exception:
                pass
        self.outer_tabs.clear()

        if cfg is None:
            for _, label in _TAB_DEFS:
                self.outer_tabs.addTab(QWidget(), label)
            self.configuration = self.optimizer = self.calculations = None
            self.simulator = self.deployment = None
            return

        self.configuration = ConfigurationWindow(cfg)
        self.optimizer = OptimizerWindow(cfg)
        self.simulator = WhatIfSimulator(cfg)
        # Calculations + Deployment need the live engine from the simulator
        self.calculations = CalculationsWindow(self.simulator.engine)
        self.deployment = DeploymentWindow(self.simulator.engine)

        # Wire dirty tracking + cross-tab refresh signals
        self.configuration.config_changed.connect(self._on_configuration_changed)
        self.optimizer.config_changed.connect(self._on_optimizer_applied)
        if hasattr(self.deployment, "config_changed"):
            self.deployment.config_changed.connect(self._mark_dirty)
        if hasattr(self.calculations, "config_changed"):
            self.calculations.config_changed.connect(self._mark_dirty)

        self.outer_tabs.addTab(self.configuration, _TAB_DEFS[0][1])
        self.outer_tabs.addTab(self.optimizer,     _TAB_DEFS[1][1])
        self.outer_tabs.addTab(self.calculations,  _TAB_DEFS[2][1])
        self.outer_tabs.addTab(self.simulator,     _TAB_DEFS[3][1])
        self.outer_tabs.addTab(self.deployment,    _TAB_DEFS[4][1])
        self.outer_tabs.setCurrentIndex(0)

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
        if self.cfg is None:
            self.setWindowTitle("APC Architect -- No Project")
            return
        name = self.cfg.name or "Untitled"
        marker = " *" if self._dirty else ""
        if self._project_path:
            base = os.path.basename(self._project_path)
            self.setWindowTitle(f"APC Architect -- {name}{marker} -- {base}")
        else:
            self.setWindowTitle(f"APC Architect -- {name}{marker} (unsaved)")
        if hasattr(self, "sim_label"):
            self.sim_label.setText(name + marker)

    # ==================================================================
    # File menu handlers
    # ==================================================================
    def _on_new_project(self):
        if not self._prompt_save_if_dirty():
            return
        cfg = SimConfig()
        cfg.name = "Untitled Project"
        cfg.project = ProjectMetadata()
        cfg._raw_yaml = {}
        self.cfg = cfg
        self._project_path = None
        self._build_tabs(cfg)
        self._mark_dirty()
        self._refresh_window_title()

    # ------------------------------------------------------------------
    def _on_open_project(self):
        if not self._prompt_save_if_dirty():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open APC Project", self._default_open_dir(),
            "APC Project (*.apcproj *.yaml *.yml);;All Files (*)")
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
            cfg = load_config(path)
        except Exception as e:
            QMessageBox.critical(
                self, "Open Project", f"Failed to load project:\n{e}")
            return

        # If the loaded name is still the default, derive from filename
        if cfg.name in ("Untitled", "Untitled Project", ""):
            stem = os.path.splitext(os.path.basename(path))[0]
            cfg.name = stem.replace("_", " ").title()

        self.cfg = cfg
        self._project_path = cfg.source_path
        self._dirty = False
        self._build_tabs(cfg)
        self._refresh_window_title()
        self._recent.add(path)
        self._rebuild_recent_menu()

    # ------------------------------------------------------------------
    def _on_save(self):
        if self.cfg is None:
            return
        if self._project_path is None:
            self._on_save_as()
            return
        self._save_to(self._project_path)

    # ------------------------------------------------------------------
    def _on_save_as(self):
        if self.cfg is None:
            return
        suggested = self._project_path or os.path.join(
            self._default_open_dir(),
            (self.cfg.name or "untitled").lower().replace(" ", "_") + ".apcproj")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", suggested,
            "APC Project (*.apcproj);;YAML (*.yaml *.yml);;All Files (*)")
        if not path:
            return
        # Ensure extension if user didn't type one
        if not os.path.splitext(path)[1]:
            path += ".apcproj"
        self._save_to(path)

    # ------------------------------------------------------------------
    def _save_to(self, path: str):
        # If the controller name is still the default, derive from filename
        if self.cfg.name in ("Untitled", "Untitled Project", ""):
            stem = os.path.splitext(os.path.basename(path))[0]
            self.cfg.name = stem.replace("_", " ").title()

        try:
            save_config(self.cfg, path)
        except Exception as e:
            QMessageBox.critical(
                self, "Save Project", f"Failed to save:\n{e}")
            return
        self._project_path = self.cfg.source_path
        self._mark_clean()
        self._refresh_window_title()
        self._recent.add(path)
        self._rebuild_recent_menu()
        self.statusBar().showMessage(f"Saved {os.path.basename(path)}", 3000)

    # ------------------------------------------------------------------
    def _on_import_bundle(self):
        """Import an .apcmodel bundle exported by APC Ident.

        Populates the SimConfig's plant model from the bundle's
        state-space realization and — if the config has no MVs/CVs
        yet — auto-creates variable entries from the bundle's tag
        lists so the user lands on a fully-populated controller
        instead of a blank screen.
        """
        if self.cfg is None:
            QMessageBox.information(
                self, "Import Bundle",
                "Create or open a project first (File > New Project).")
            return

        start_dir = self._default_open_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Model Bundle", start_dir,
            "APC Model Bundle (*.apcmodel);;All Files (*)")
        if not path:
            return

        try:
            from azeoapc.identification.model_bundle import load_model_bundle
            bundle = load_model_bundle(path)
        except Exception as e:
            QMessageBox.critical(
                self, "Import Bundle",
                f"Failed to load bundle:\n{type(e).__name__}: {e}")
            return

        if bundle.A is None:
            QMessageBox.warning(
                self, "Import Bundle",
                "This bundle has no state-space realization.\n"
                "Re-export it from APC Ident with ERA enabled.")
            return

        import numpy as np
        from azeoapc.models.variables import MV, CV, Limits
        from azeoapc.models.plant import StateSpacePlant

        # Auto-create MV/CV entries from the bundle's tag lists if
        # the config doesn't have them yet.
        if not self.cfg.mvs:
            for i, tag in enumerate(bundle.mv_tags):
                u0 = float(bundle.u0[i]) if bundle.u0 is not None and i < len(bundle.u0) else 0.0
                self.cfg.mvs.append(MV(
                    tag=tag, name=tag, units="",
                    steady_state=u0,
                    limits=Limits(),
                    move_suppress=1.0,
                ))
        if not self.cfg.cvs:
            for i, tag in enumerate(bundle.cv_tags):
                y0 = float(bundle.y0[i]) if bundle.y0 is not None and i < len(bundle.y0) else 0.0
                self.cfg.cvs.append(CV(
                    tag=tag, name=tag, units="",
                    steady_state=y0,
                    setpoint=y0,
                    limits=Limits(),
                    weight=1.0,
                ))

        # Build the plant from the bundle's state-space matrices
        nx = bundle.A.shape[0]
        nu = bundle.B.shape[1]
        ny = bundle.C.shape[0]
        nd = max(len(self.cfg.dvs), 1)
        Bd = np.zeros((nx, nd))

        u0 = bundle.u0 if bundle.u0 is not None else np.array(
            [mv.steady_state for mv in self.cfg.mvs])
        y0 = bundle.y0 if bundle.y0 is not None else np.array(
            [cv.steady_state for cv in self.cfg.cvs])
        d0 = (np.array([dv.steady_state for dv in self.cfg.dvs])
              if self.cfg.dvs else np.zeros(0))

        self.cfg.plant = StateSpacePlant(
            A=bundle.A, Bu=bundle.B, Bd=Bd, C=bundle.C, D=bundle.D,
            x0=np.zeros(nx), u0=u0, d0=d0, y0=y0,
            sample_time=self.cfg.sample_time,
            continuous=False,
        )

        # Store the bundle path in _raw_yaml so save_config can
        # round-trip the model section.
        if self.cfg._raw_yaml is None:
            self.cfg._raw_yaml = {}
        # Make the source path relative to the project dir if possible
        if self._project_path:
            try:
                rel = os.path.relpath(
                    path, os.path.dirname(self._project_path)
                ).replace("\\", "/")
            except ValueError:
                rel = path.replace("\\", "/")
        else:
            rel = os.path.abspath(path).replace("\\", "/")
        self.cfg._raw_yaml["model"] = {
            "type": "bundle",
            "source": rel,
        }

        # Update the controller name from the bundle if still untitled
        if self.cfg.name in ("Untitled", "Untitled Project", ""):
            self.cfg.name = bundle.name or "Imported Controller"

        # Rebuild all tabs with the new plant
        self._build_tabs(self.cfg)
        self._mark_dirty()
        self._refresh_window_title()

        self.statusBar().showMessage(
            f"Imported model bundle: {os.path.basename(path)} "
            f"({bundle.ny} CV x {bundle.nu} MV, nx={nx})",
            6000)

        QMessageBox.information(
            self, "Import Bundle",
            f"Model imported successfully.\n\n"
            f"  Bundle: {bundle.name}\n"
            f"  MVs: {', '.join(bundle.mv_tags)}\n"
            f"  CVs: {', '.join(bundle.cv_tags)}\n"
            f"  States: {nx}  (ERA order {bundle.era_order})\n\n"
            f"The controller now has a plant model. You can:\n"
            f"  - Configure limits in the Configuration tab\n"
            f"  - Tune the optimizer in the Optimization tab\n"
            f"  - Run a what-if simulation in the Simulation tab\n"
            f"  - Save the project (File > Save As)")

    # ------------------------------------------------------------------
    def _on_reveal(self):
        if not self._project_path or not os.path.exists(self._project_path):
            QMessageBox.information(self, "Reveal",
                                    "Save the project first.")
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(self._project_path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", self._project_path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(self._project_path)])
        except Exception as e:
            QMessageBox.warning(self, "Reveal", f"Could not open file manager:\n{e}")

    # ------------------------------------------------------------------
    def _on_clear_recent(self):
        self._recent.clear()
        self._rebuild_recent_menu()

    # ------------------------------------------------------------------
    def _default_open_dir(self) -> str:
        if self._project_path:
            return os.path.dirname(self._project_path)
        # Fall back to bundled examples folder
        examples = os.path.join(os.path.dirname(__file__), "examples")
        if os.path.isdir(examples):
            return examples
        return os.getcwd()

    # ------------------------------------------------------------------
    def _prompt_save_if_dirty(self) -> bool:
        """If unsaved changes exist, ask the user. Returns False on cancel."""
        if not self._dirty or self.cfg is None:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            f"'{self.cfg.name}' has unsaved changes. Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if reply == QMessageBox.Cancel:
            return False
        if reply == QMessageBox.Save:
            self._on_save()
            return not self._dirty   # if save failed, dirty stays true
        return True   # Discard

    # ==================================================================
    # Cross-tab signal handlers
    # ==================================================================
    def _on_configuration_changed(self):
        """Configuration sub-tab edited a value."""
        self._mark_dirty()
        if self.optimizer is not None and hasattr(self.optimizer, "refresh"):
            self.optimizer.refresh()

    def _on_optimizer_applied(self):
        """User clicked Apply in the optimizer tab -- rebuild engine."""
        self._mark_dirty()
        if self.simulator is not None and hasattr(self.simulator, "_init_engine"):
            self.simulator._init_engine()
        if self.calculations is not None and hasattr(self.calculations, "set_engine"):
            self.calculations.set_engine(self.simulator.engine)
        if self.deployment is not None and hasattr(self.deployment, "set_engine"):
            self.deployment.set_engine(self.simulator.engine)
        if self.simulator is not None and hasattr(self.simulator, "_populate"):
            try:
                self.simulator.mv_table.cellChanged.disconnect()
                self.simulator.cv_table.cellChanged.disconnect()
            except (RuntimeError, AttributeError):
                pass
            self.simulator._populate()
        if self.configuration is not None and hasattr(self.configuration, "refresh"):
            self.configuration.refresh()
        # Auto-switch to Simulation so user can immediately test
        self.outer_tabs.setCurrentIndex(3)

    # ==================================================================
    # Window lifecycle
    # ==================================================================
    def closeEvent(self, event):
        """Save-prompt + tear down OPC UA threads on app exit."""
        if not self._prompt_save_if_dirty():
            event.ignore()
            return
        if self.deployment is not None and hasattr(self.deployment, "shutdown"):
            try:
                self.deployment.shutdown()
            except Exception:
                pass
        super().closeEvent(event)

    # ==================================================================
    # External hooks (used by Optimization tab "Run RTO" button)
    # ==================================================================
    def trigger_rto(self):
        """Run Layer 3 RTO once and display the result."""
        if self.simulator is None or not hasattr(self.simulator, "engine"):
            QMessageBox.warning(self, "RTO", "No simulation engine loaded.")
            return
        if self.simulator.engine is None or self.simulator.engine.layer3 is None:
            QMessageBox.warning(
                self, "RTO",
                "Layer 3 RTO is not available.\n\n"
                "Requirements:\n"
                "  \u2022 Plant must be a NonlinearPlant (type: nonlinear in YAML)\n"
                "  \u2022 Layer 3 must be enabled in the Optimization tab\n"
                "  \u2022 CasADi must be installed (pip install casadi)")
            return
        result = self.simulator.engine.execute_rto()
        if hasattr(self.optimizer, "layer3_page"):
            self.optimizer.layer3_page.show_rto_result(result)
        if hasattr(self.optimizer, "layer_tabs"):
            self.optimizer.layer_tabs.setCurrentIndex(0)
        self.outer_tabs.setCurrentIndex(0)
