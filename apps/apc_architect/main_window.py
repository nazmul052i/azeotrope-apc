"""APC Architect main window -- modern sidebar layout.

Uses sidebar navigation matching the APC Ident style, with ISA-101
Silver theme and workflow wizard steps.
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
    QStackedWidget, QVBoxLayout, QWidget,
)

from azeoapc.models.config_loader import (
    SimConfig, load_config, save_config, ProjectMetadata,
)

from .calculations_window import CalculationsWindow
from .configuration_window import ConfigurationWindow
from .deployment_window import DeploymentWindow
from .optimizer_window import OptimizerWindow
from .recent_files import RecentFiles
from .backstage import BackstageScreen
from .sidebar import ArchitectSidebar
from .whatif_window import WhatIfSimulator, _STYLE

# Step ID -> stack index
_STEP_INDEX = {
    "config": 0, "optimize": 1, "calculate": 2,
    "simulate": 3, "deploy": 4,
}


class MainWindow(QMainWindow):
    """Top-level window with sidebar navigation and stacked content."""

    def __init__(self, config: Optional[SimConfig] = None, parent=None):
        super().__init__(parent)
        self.cfg: Optional[SimConfig] = config
        self._dirty: bool = False
        self._project_path: Optional[str] = config.source_path if config else None
        self._recent = RecentFiles(max_entries=10)

        self.setMinimumSize(1500, 900)
        self.setAcceptDrops(True)

        # Panel references created in _build_tabs
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
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self.sidebar = ArchitectSidebar()
        self.sidebar.step_clicked.connect(self._on_sidebar_step)
        self.sidebar.context_requested.connect(self._show_step_context_menu)
        root.addWidget(self.sidebar)

        # Stacked content
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Backwards compat alias
        self.outer_tabs = self.stack

        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    def _on_sidebar_step(self, step_id: str):
        self._navigate_to(step_id)

    def _on_backstage_action(self, action_id: str):
        """Handle actions from the backstage landing screen."""
        if action_id == "new":
            self._on_new_project()
        elif action_id == "open":
            self._on_open_project()
        elif action_id == "import":
            self._on_import_bundle()
        elif action_id.startswith("template_"):
            template_name = action_id.replace("template_", "").upper()
            self._new_from_template(template_name)
        else:
            self.statusBar().showMessage(f"Unknown action: {action_id}")

    def _new_from_template(self, template_name: str):
        """Create a new project from a process template."""
        try:
            from azeoapc.identification.process_templates import get_template
            template = get_template(template_name)
            # Create a new config and apply template settings
            cfg = SimConfig(name=f"{template.name} Controller")
            cfg.sample_time = template.suggested_dt
            self.cfg = cfg
            self._project_path = None
            self._build_tabs(cfg)
            self._mark_dirty()
            self.statusBar().showMessage(
                f"New project from {template.name} template", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Template",
                                f"Failed to load template:\n{e}")

    def _navigate_to(self, step_id: str):
        idx = _STEP_INDEX.get(step_id, 0)
        self._navigate_to_index(idx)

    def _navigate_to_index(self, idx: int):
        if idx < self.stack.count():
            self.stack.setCurrentIndex(idx)
            reverse = {v: k for k, v in _STEP_INDEX.items()}
            step_id = reverse.get(idx, "config")
            self.sidebar.set_current(step_id)
            self.statusBar().showMessage(
                f"{step_id.title()} | "
                f"{self.cfg.name if self.cfg else 'No project'}")

    def _show_step_context_menu(self, step_id: str, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #EBECF1; color: #1A1C24; "
            "border: 1px solid #9AA5B4; }"
            "QMenu::item { padding: 5px 24px 5px 12px; }"
            "QMenu::item:selected { background: #2B5EA7; color: white; }"
            "QMenu::separator { height: 1px; background: #C8CDD8; margin: 4px 8px; }")

        if step_id == "config":
            menu.addAction("Import Model Bundle...").triggered.connect(
                self._on_import_bundle)
            menu.addSeparator()
            menu.addAction("Add MV...").triggered.connect(
                lambda: self.statusBar().showMessage("Add MV from config tab"))
            menu.addAction("Add CV...").triggered.connect(
                lambda: self.statusBar().showMessage("Add CV from config tab"))
        elif step_id == "optimize":
            menu.addAction("Auto-Tune Layer 1").triggered.connect(
                lambda: self.optimizer.layer1_page._auto_tune()
                if self.optimizer and hasattr(self.optimizer, 'layer1_page') else None)
            menu.addAction("Apply to Simulator").triggered.connect(
                lambda: self.optimizer._apply()
                if self.optimizer and hasattr(self.optimizer, '_apply') else None)
        elif step_id == "simulate":
            menu.addAction("Step Simulation").triggered.connect(
                lambda: self.simulator._step_simulation()
                if self.simulator and hasattr(self.simulator, '_step_simulation') else None)
            menu.addAction("Reset Simulation").triggered.connect(
                lambda: self.simulator._init_engine()
                if self.simulator and hasattr(self.simulator, '_init_engine') else None)
        elif step_id == "deploy":
            menu.addAction("Connect OPC UA...").triggered.connect(
                lambda: self.deployment._on_connect_clicked()
                if self.deployment and hasattr(self.deployment, '_on_connect_clicked') else None)
            menu.addAction("Deploy Controller").triggered.connect(
                lambda: self.deployment._on_deploy_clicked()
                if self.deployment and hasattr(self.deployment, '_on_deploy_clicked') else None)

        if menu.actions():
            menu.exec(global_pos)

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
            act.triggered.connect(lambda _=False, idx=i: self._navigate_to_index(idx))
            view_menu.addAction(act)

        # ── Help ──
        help_menu = menubar.addMenu("&Help")

        help_act = QAction("&Help Topics (F1)", self)
        help_act.setShortcut("F1")
        help_act.triggered.connect(self._on_help)
        help_menu.addAction(help_act)

        help_menu.addSeparator()

        about_act = QAction("&About APC Architect", self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

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
        """Build the five panels from a (possibly None) SimConfig."""
        # Tear down existing
        if self.deployment is not None and hasattr(self.deployment, "shutdown"):
            try:
                self.deployment.shutdown()
            except Exception:
                pass
        while self.stack.count():
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()

        if cfg is None:
            # Show backstage landing screen
            backstage = BackstageScreen(
                recent_paths=self._recent.get())
            backstage.action_triggered.connect(self._on_backstage_action)
            backstage.recent_opened.connect(self._open_path)
            self.stack.addWidget(backstage)
            self.configuration = self.optimizer = self.calculations = None
            self.simulator = self.deployment = None
            return

        self.configuration = ConfigurationWindow(cfg)
        self.optimizer = OptimizerWindow(cfg)
        self.simulator = WhatIfSimulator(cfg)
        self.calculations = CalculationsWindow(self.simulator.engine)
        self.deployment = DeploymentWindow(self.simulator.engine)

        # Wire dirty tracking + cross-tab refresh signals
        self.configuration.config_changed.connect(self._on_configuration_changed)
        self.optimizer.config_changed.connect(self._on_optimizer_applied)
        if hasattr(self.deployment, "config_changed"):
            self.deployment.config_changed.connect(self._mark_dirty)
        if hasattr(self.calculations, "config_changed"):
            self.calculations.config_changed.connect(self._mark_dirty)

        # Add to stacked widget (order matches _STEP_INDEX)
        self.stack.addWidget(self.configuration)  # 0
        self.stack.addWidget(self.optimizer)       # 1
        self.stack.addWidget(self.calculations)    # 2
        self.stack.addWidget(self.simulator)       # 3
        self.stack.addWidget(self.deployment)      # 4
        self.stack.setCurrentIndex(0)
        self.sidebar.set_current("config")

        # Show model file in sidebar if available
        if hasattr(cfg, '_raw_yaml') and cfg._raw_yaml:
            model = cfg._raw_yaml.get("model", {})
            if isinstance(model, dict) and model.get("source"):
                self.sidebar.set_file("config", model["source"])

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
        # Status bar shows project name
        self.statusBar().showMessage(f"{name}{marker}")

    # ==================================================================
    # File menu handlers
    # ==================================================================
    def _on_help(self):
        from .help_viewer import show_architect_help, context_help_for_step
        idx = self.stack.currentIndex()
        reverse = {v: k for k, v in _STEP_INDEX.items()}
        step_id = reverse.get(idx, "config")
        topic = context_help_for_step(step_id)
        show_architect_help(self, topic)

    def _on_about(self):
        QMessageBox.about(
            self, "About APC Architect",
            "<h2>Azeotrope APC Architect</h2>"
            "<p>Version 0.2.0</p>"
            "<p>Controller configuration, tuning, simulation, and "
            "deployment studio for Advanced Process Control.</p>"
            "<p>Features:</p>"
            "<ul>"
            "<li>3-layer optimization (QP + LP + NLP)</li>"
            "<li>DMC3-style what-if simulator</li>"
            "<li>Python calculation scripting</li>"
            "<li>OPC UA deployment runtime</li>"
            "<li>Process templates & recipes</li>"
            "</ul>"
            "<p>&copy; 2026 Azeotrope Process Control</p>")

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
        self._navigate_to("simulate")

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
        self._navigate_to("optimize")
