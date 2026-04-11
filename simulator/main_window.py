"""Main application window: Optimization + Simulation tabs."""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTabWidget, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from .models.config_loader import SimConfig, load_config
from .optimizer_window import OptimizerWindow
from .whatif_window import WhatIfSimulator, _STYLE


class MainWindow(QMainWindow):
    """Top-level window with Optimization and Simulation tabs."""

    def __init__(self, config: SimConfig = None, parent=None):
        super().__init__(parent)
        self.cfg = config
        title = config.name if config else "No Config"
        self.setWindowTitle(f"Azeotrope APC -- {title}")
        self.setMinimumSize(1500, 900)
        self.setStyleSheet(_STYLE)

        self._build_ui()
        self._build_menu()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header strip with app branding + sim name
        header = self._build_header()
        root.addWidget(header)

        # Outer tabs: Optimization | Simulation
        self.outer_tabs = QTabWidget()
        self.outer_tabs.setStyleSheet("""
        QTabWidget::pane {
            border: none;
            background: #F5F6F8;
        }
        QTabBar::tab {
            background: #2C3345;
            color: #C8D0DC;
            border: none;
            padding: 10px 32px;
            margin-right: 1px;
            font-size: 11pt;
            font-weight: 600;
            min-width: 140px;
        }
        QTabBar::tab:selected {
            background: #3B5998;
            color: white;
            border-bottom: 3px solid #6BBAFF;
        }
        QTabBar::tab:hover:!selected {
            background: #3A4560;
            color: #E8EDF5;
        }
        """)

        if self.cfg:
            self.optimizer = OptimizerWindow(self.cfg)
            self.simulator = WhatIfSimulator(self.cfg)
            # When optimizer applies changes, refresh the simulator's tables
            self.optimizer.config_changed.connect(self._on_optimizer_applied)
        else:
            self.optimizer = QWidget()
            self.simulator = QWidget()

        self.outer_tabs.addTab(self.optimizer, "  ⚙  Optimization  ")
        self.outer_tabs.addTab(self.simulator, "  ▶  Simulation  ")
        # Default to Optimization tab so user configures first
        self.outer_tabs.setCurrentIndex(0)

        root.addWidget(self.outer_tabs, 1)

    def _build_header(self):
        header = QWidget()
        header.setFixedHeight(38)
        header.setStyleSheet(
            "background: #1A2030; border-bottom: 1px solid #0F1420;")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        # Diamond brand icon
        icon = QLabel("◆")
        icon.setStyleSheet("color: #6BBAFF; font-size: 18pt; font-weight: bold;")
        lay.addWidget(icon)

        brand = QLabel("AZEOTROPE APC")
        brand.setStyleSheet(
            "color: #E8EDF5; font-size: 12pt; font-weight: 600; "
            "letter-spacing: 1px;")
        lay.addWidget(brand)

        sep = QLabel("|")
        sep.setStyleSheet("color: rgba(255,255,255,0.2); font-size: 14pt;")
        lay.addWidget(sep)

        self.sim_label = QLabel(self.cfg.name if self.cfg else "No configuration loaded")
        self.sim_label.setStyleSheet(
            "color: #A8B4C8; font-size: 10pt; font-weight: 500;")
        lay.addWidget(self.sim_label)

        lay.addStretch()

        version = QLabel("v0.1.0")
        version.setStyleSheet("color: #6B7394; font-size: 8pt;")
        lay.addWidget(version)

        return header

    def _build_menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet(
            "QMenuBar { background: #2C3345; color: #C8D0DC; "
            "border-bottom: 1px solid #1A2030; }"
            "QMenuBar::item:selected { background: #3B5998; }"
            "QMenu { background: #2C3345; color: #E8EDF5; "
            "border: 1px solid #1A2030; }"
            "QMenu::item:selected { background: #3B5998; }")

        file_menu = menubar.addMenu("&File")
        open_act = QAction("&Open Configuration...", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._open_config)
        file_menu.addAction(open_act)

        file_menu.addSeparator()

        exit_act = QAction("E&xit", self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        view_menu = menubar.addMenu("&View")
        opt_act = QAction("&Optimization Tab", self)
        opt_act.setShortcut("Ctrl+1")
        opt_act.triggered.connect(lambda: self.outer_tabs.setCurrentIndex(0))
        view_menu.addAction(opt_act)

        sim_act = QAction("&Simulation Tab", self)
        sim_act.setShortcut("Ctrl+2")
        sim_act.triggered.connect(lambda: self.outer_tabs.setCurrentIndex(1))
        view_menu.addAction(sim_act)

    def _open_config(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Configuration", "",
            "YAML Files (*.yaml *.yml);;All Files (*)")
        if not path:
            return
        try:
            new_cfg = load_config(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load config:\n{e}")
            return
        self.cfg = new_cfg
        # Rebuild tabs
        self.outer_tabs.clear()
        self.optimizer = OptimizerWindow(new_cfg)
        self.simulator = WhatIfSimulator(new_cfg)
        self.optimizer.config_changed.connect(self._on_optimizer_applied)
        self.outer_tabs.addTab(self.optimizer, "  ⚙  Optimization  ")
        self.outer_tabs.addTab(self.simulator, "  ▶  Simulation  ")
        self.sim_label.setText(new_cfg.name)
        self.setWindowTitle(f"Azeotrope APC -- {new_cfg.name}")

    def _on_optimizer_applied(self):
        """Called when user clicks Apply in the optimizer tab."""
        # Rebuild the simulator engine with new config values
        if hasattr(self.simulator, "_init_engine"):
            self.simulator._init_engine()
        if hasattr(self.simulator, "_populate"):
            # Disconnect to avoid signal storm
            try:
                self.simulator.mv_table.cellChanged.disconnect()
                self.simulator.cv_table.cellChanged.disconnect()
            except (RuntimeError, AttributeError):
                pass
            self.simulator._populate()
        # Auto-switch to Simulation tab so user can immediately test
        self.outer_tabs.setCurrentIndex(1)

    def trigger_rto(self):
        """Run Layer 3 RTO once and display the result."""
        if not hasattr(self.simulator, "engine") or self.simulator.engine is None:
            QMessageBox.warning(self, "RTO", "No simulation engine loaded.")
            return
        if self.simulator.engine.layer3 is None:
            QMessageBox.warning(
                self, "RTO",
                "Layer 3 RTO is not available.\n\n"
                "Requirements:\n"
                "  • Plant must be a NonlinearPlant (type: nonlinear in YAML)\n"
                "  • Layer 3 must be enabled in the Optimization tab\n"
                "  • CasADi must be installed (pip install casadi)")
            return
        result = self.simulator.engine.execute_rto()
        if hasattr(self.optimizer, "layer3_page"):
            self.optimizer.layer3_page.show_rto_result(result)
        # Switch to Layer 3 tab to show the result
        if hasattr(self.optimizer, "layer_tabs"):
            self.optimizer.layer_tabs.setCurrentIndex(0)
        self.outer_tabs.setCurrentIndex(0)
