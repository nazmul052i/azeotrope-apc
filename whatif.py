"""Commercial-grade What-If Simulator.

Unified layout with:
- Left panel: editable MV/CV tables with column visibility, edit highlighting
- Right panel: embedded prediction plots (no separate window)
- Bottom: activity log + step controls with keyboard shortcuts
- Scenario save/compare workflow
"""

import os
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QHeaderView,
    QTabWidget, QTextEdit, QFrame, QComboBox, QToolBar,
    QScrollArea, QMenu, QSpinBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QAction, QShortcut

_APP_ICON = r"C:\Program Files (x86)\AspenTech\APC\V14.2\Builder\DMC3.ico"

# ---- MV columns (matches APC web viewer Tuning FIR tab) ----
# Col: (header, editable)
_MV_COLS = [
    # Operating data
    ("Name", False),              # 0
    ("Measurement", False),       # 1
    # Tuning (matches APC column order)
    ("Move Supp", True),          # 2
    ("Max Move", True),           # 3
    ("SS Move Lim", True),        # 4
    ("MinMove Ctrl", False),      # 5
    ("LP Cost", True),            # 6
    ("Cost Rank", True),          # 7
    ("Reverse", False),           # 8
    # Limits (4 types)
    ("Lo Limit", True),           # 9  — operator lo (editable)
    ("Hi Limit", True),           # 10 — operator hi (editable)
    ("Eng Lo", False),            # 11 — engineering lo (read-only)
    ("Eng Hi", False),            # 12 — engineering hi (read-only)
    ("Val Lo", False),            # 13 — validity lo (read-only)
    ("Val Hi", False),            # 14 — validity hi (read-only)
    ("Limit Track", False),       # 15
    ("Move Res", True),           # 16
    ("Move Accum", True),         # 17
    ("Shed Option", False),       # 18
    ("Typical Move", True),       # 19
    # Result (updated after simulate/step)
    ("Predicted", False),         # 20
    ("Delta", False),             # 21
    ("Last Move", False),         # 22
    ("Status", False),            # 23
    ("Desc", False),              # 24
]
_MV_PRED, _MV_DELTA, _MV_LASTMOVE = 20, 21, 22
_MV_LO, _MV_HI = 9, 10
_MV_ENG_LO, _MV_ENG_HI = 11, 12
_MV_VAL_LO, _MV_VAL_HI = 13, 14
_MV_COST, _MV_RANK, _MV_MAXMOVE, _MV_MOVESUPP = 6, 7, 3, 2
_MV_TYPMOVE = 19
_MV_DEFAULT_VISIBLE = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 19, 20, 21, 22}

# ---- CV columns (matches DMC3 Operate view + optimizer fields) ----
# ---- CV columns (matches APC web viewer Tuning FIR tab) ----
_CV_COLS = [
    # Operating data
    ("Name", False),              # 0
    ("Value", False),             # 1
    ("SS Pred", False),           # 2
    # Limits (4 types: operator, engineering, validity)
    ("Lo Limit", True),           # 3   — operator lo (editable)
    ("Hi Limit", True),           # 4   — operator hi (editable)
    ("Eng Lo", False),            # 5   — engineering lo (read-only)
    ("Eng Hi", False),            # 6   — engineering hi (read-only)
    ("Val Lo", False),            # 7   — validity lo (read-only)
    ("Val Hi", False),            # 8   — validity hi (read-only)
    # SS Tuning (matches APC Tuning FIR)
    ("SS Lo Rank", True),         # 9
    ("SS Hi Rank", True),         # 10
    ("SS Lo Concern", True),      # 11
    ("SS Hi Concern", True),      # 12
    ("Cost Rank", True),          # 13
    ("LP Cost", True),            # 14
    # Dynamic Tuning
    ("Dyn Lo Concern", True),     # 15
    ("Dyn Hi Concern", True),     # 16
    ("Dyn Tgt Concern", True),    # 17
    ("Dyn Lo Zone", True),        # 18
    ("Dyn Hi Zone", True),        # 19
    ("Limit Track", False),       # 20
    ("Max SS Step", True),        # 21
    # Computed
    ("ECR", False),               # 22  → 1/concern²
    ("Weight", False),            # 23
    # Result (updated after simulate/step)
    ("Predicted", False),         # 24
    ("Delta", False),             # 25
    ("Violation", False),         # 26
    # Ramp
    ("Ramp", False),              # 27
    ("Ramp SP", True),            # 28
    ("Ramp Rate", True),          # 29
    ("Max Imbal", True),          # 30
    ("Ramp Horizon", True),       # 31
    ("Rotation", True),           # 32
    # Diagnostics
    ("Pred Err", False),          # 33
    ("Status", False),            # 34
    ("Desc", False),              # 35
]
_CV_PRED, _CV_DELTA, _CV_VIOL = 24, 25, 26
_CV_LO, _CV_HI = 3, 4
_CV_ENG_LO, _CV_ENG_HI = 5, 6
_CV_VAL_LO, _CV_VAL_HI = 7, 8
_CV_ECR = 22
_CV_DEFAULT_VISIBLE = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 21, 24, 25, 26}


@dataclass
class Scenario:
    """Saved what-if scenario."""
    name: str
    timestamp: datetime
    mv_lo: dict = field(default_factory=dict)
    mv_hi: dict = field(default_factory=dict)
    cv_lo: dict = field(default_factory=dict)
    cv_hi: dict = field(default_factory=dict)
    feasible: bool = True
    n_violations: int = 0
    dof: int = 0


_STYLE = """
QWidget { font-family: "Segoe UI", Arial; font-size: 9pt; background: #F5F6F8; }
QLabel#title { font-size: 12pt; font-weight: 600; color: #1A2744; }
QLabel#subtitle { font-size: 8pt; color: #6B7394; }
QLabel#feasible { font-size: 9pt; font-weight: bold; padding: 3px 10px; border-radius: 4px; }
QLabel#editSummary { font-size: 8pt; color: #3B5998; font-weight: 500; padding: 2px 6px;
    background: #E8EDF5; border-radius: 3px; }
QLabel#stateIndicator { font-size: 8pt; padding: 2px 8px; border-radius: 3px; font-weight: 600; }

QTableWidget { background: white; alternate-background-color: #F6F7FA;
    border: 1px solid #D0D4DC; gridline-color: #E8EAF0;
    selection-background-color: #3B5998; selection-color: white;
    font-size: 8pt; font-family: "Segoe UI", Arial; }
QTableWidget::item { padding: 2px 5px; }
QTableWidget::item:hover { background: #E8EDF5; }
QHeaderView::section { background: #E2E6EE; border: none;
    border-right: 1px solid #D0D4DC; border-bottom: 1px solid #D0D4DC;
    padding: 3px 5px; font-weight: 600; font-size: 7.5pt; color: #2D3748; }

QTabWidget::pane { border: 1px solid #D5D8E0; background: white; }
QTabBar::tab { background: #ECEEF4; border: 1px solid #D5D8E0; border-bottom: none;
    border-top-left-radius: 3px; border-top-right-radius: 3px;
    padding: 4px 14px; margin-right: 1px; font-size: 8pt; }
QTabBar::tab:selected { background: white; font-weight: 600; }

QTextEdit#activityLog { background: #1A1F2E; color: #C8D0DC; border: none;
    font-family: Consolas, monospace; font-size: 8pt; padding: 6px; }

QSplitter::handle { background: #C0C8D8; }
QSplitter::handle:hover { background: #8090A8; }
QSplitter::handle:pressed { background: #5070A0; }

QPushButton#toolBtn { background: #3B5998; color: white; border: none;
    border-radius: 3px; padding: 4px 14px; font-size: 8pt; font-weight: 600; }
QPushButton#toolBtn:hover { background: #4A6BB5; }
QPushButton#toolBtn:disabled { background: #B0BEC5; }
QPushButton#stopBtn { background: #C62828; color: white; border: none;
    border-radius: 3px; padding: 4px 14px; font-size: 8pt; font-weight: 600; }
QPushButton#stopBtn:hover { background: #E53935; }
QPushButton#resetBtn { background: #6B7394; color: white; border: none;
    border-radius: 3px; padding: 4px 12px; font-size: 8pt; font-weight: 600; }
QPushButton#resetBtn:hover { background: #8899BB; }
QPushButton#greenBtn { background: #2E7D32; color: white; border: none;
    border-radius: 3px; padding: 4px 14px; font-size: 8pt; font-weight: 600; }
QPushButton#greenBtn:hover { background: #388E3C; }
QPushButton#tealBtn { background: #00897B; color: white; border: none;
    border-radius: 3px; padding: 4px 14px; font-size: 8pt; font-weight: 600; }
QPushButton#tealBtn:hover { background: #00ACC1; }
"""

# Colors for cell states
_CLR_EDITABLE = QColor("#FFF8E8")     # warm cream — editable
_CLR_EDITED = QColor("#DBEAFE")       # blue tint — user changed
_CLR_CONSTRAINED = QColor("#FFF3E0")  # amber — at limit
_CLR_VIOLATED = QColor("#FFCDD2")     # red — violated
_CLR_RAMP = QColor("#E3F2FD")         # blue — ramp
_CLR_BAD = QColor("#FFEBEE")          # red — bad/oos
_CLR_FF = QColor("#ECEFF1")           # gray — feedforward
_CLR_RESULT_CHANGE = QColor("#E8F5E9")  # green tint — changed in results
_CLR_RESULT_VIOL = QColor("#FFCDD2")


class WhatIfSimulator(QWidget):
    """Commercial-grade What-If Simulator.

    Unified layout: tables left, plots right, activity log bottom.
    All 10 improvements implemented.
    """

    def __init__(self, agent, parent=None):
        super().__init__(parent)
        self.agent = agent
        c = agent._classification
        self.setWindowTitle(f"What-If Simulator \u2014 {c.name}")
        self.setMinimumSize(1400, 800)
        self.setWindowFlags(Qt.Window)
        self.setStyleSheet(_STYLE)
        from .icons import whatif_icon
        self.setWindowIcon(whatif_icon())

        self._mv_list = []
        self._cv_list = []
        self._mv_originals = {}  # {(row, col): original_text}
        self._cv_originals = {}
        self._n_edits = 0
        self._step_sim = None
        self._steps_per_tick = 1
        self._scenarios = []      # saved scenarios
        self._plot_window = None   # single plot window reference
        self._result_items_mv = []  # pre-created result table items
        self._result_items_cv = []

        self._build_ui()
        self._populate()
        # Create initial plots immediately from current state (no Simulate needed)
        self._create_initial_plot()
        self._setup_shortcuts()

    # ================================================================ UI BUILD
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # --- Header ---
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        title = QLabel("What-If Simulator")
        title.setObjectName("title")
        hdr.addWidget(title)

        self._state_lbl = QLabel("  IDLE  ")
        self._state_lbl.setObjectName("stateIndicator")
        self._state_lbl.setStyleSheet(
            "QLabel#stateIndicator { background: #E8EAF0; color: #6B7394; }")
        hdr.addWidget(self._state_lbl)

        self._feasible_lbl = QLabel("")
        self._feasible_lbl.setObjectName("feasible")
        hdr.addWidget(self._feasible_lbl)

        self._edit_summary = QLabel("")
        self._edit_summary.setObjectName("editSummary")
        hdr.addWidget(self._edit_summary)

        hdr.addStretch()

        # Scenario controls
        self._scenario_combo = QComboBox()
        self._scenario_combo.setFixedWidth(180)
        self._scenario_combo.addItem("(no saved scenarios)")
        self._scenario_combo.setStyleSheet("font-size: 8pt;")
        hdr.addWidget(self._scenario_combo)

        save_btn = QPushButton("Save Scenario")
        save_btn.setObjectName("toolBtn")
        save_btn.clicked.connect(self._save_scenario)
        hdr.addWidget(save_btn)

        root.addLayout(hdr)

        # --- Main body: horizontal splitter ---
        # Left = tables, Right = plots + results
        self._main_split = QSplitter(Qt.Horizontal)

        # ---- LEFT: MV table (top) + CV table (bottom) — like DMC3 Builder ----
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        # Vertical splitter: MV table (top) / CV table (bottom)
        # User can drag the divider to resize — small MV table, large CV table
        table_split = QSplitter(Qt.Vertical)
        table_split.setHandleWidth(4)
        table_split.setStyleSheet(
            "QSplitter::handle { background: #B0B8C8; }"
            "QSplitter::handle:hover { background: #8090A8; }")

        # MV section
        mv_panel = QWidget()
        mv_lay = QVBoxLayout(mv_panel)
        mv_lay.setContentsMargins(0, 0, 0, 0)
        mv_lay.setSpacing(0)
        mv_hdr = QLabel("  Independents (MVs)")
        mv_hdr.setFixedHeight(20)
        mv_hdr.setStyleSheet(
            "font-size: 8pt; font-weight: 600; color: #1A2744; "
            "background: #DDE2EC; border-bottom: 1px solid #C0C8D8;")
        mv_lay.addWidget(mv_hdr)
        self.mv_table = self._make_table(editable=True)
        mv_lay.addWidget(self.mv_table, 1)
        table_split.addWidget(mv_panel)

        # CV section
        cv_panel = QWidget()
        cv_lay = QVBoxLayout(cv_panel)
        cv_lay.setContentsMargins(0, 0, 0, 0)
        cv_lay.setSpacing(0)
        cv_hdr = QLabel("  Dependents (CVs)")
        cv_hdr.setFixedHeight(20)
        cv_hdr.setStyleSheet(
            "font-size: 8pt; font-weight: 600; color: #1A2744; "
            "background: #DDE2EC; border-bottom: 1px solid #C0C8D8;")
        cv_lay.addWidget(cv_hdr)
        self.cv_table = self._make_table(editable=True)
        cv_lay.addWidget(self.cv_table, 1)
        table_split.addWidget(cv_panel)

        # Default: MV gets 35%, CV gets 65% of vertical space
        table_split.setSizes([250, 450])

        left_lay.addWidget(table_split, 1)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        sim_btn = QPushButton("Simulate (Ctrl+Enter)")
        sim_btn.setObjectName("toolBtn")
        sim_btn.clicked.connect(self._on_simulate)
        btn_row.addWidget(sim_btn)

        reset_btn = QPushButton("Reset Limits")
        reset_btn.setObjectName("resetBtn")
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)

        btn_row.addStretch()
        left_lay.addLayout(btn_row)

        self._main_split.addWidget(left)

        # ---- RIGHT: Prediction plots (embedded) ----
        self._plot_container = QWidget()
        self._plot_container_lay = QVBoxLayout(self._plot_container)
        self._plot_container_lay.setContentsMargins(0, 0, 0, 0)
        self._plot_placeholder_lbl = QLabel(
            "Click Simulate or Step to see prediction plots")
        self._plot_placeholder_lbl.setAlignment(Qt.AlignCenter)
        self._plot_placeholder_lbl.setStyleSheet(
            "color: #8899AA; font-size: 10pt; background: #ECEEF4; "
            "border: 1px solid #D5D8E0; min-height: 200px;")
        self._plot_container_lay.addWidget(self._plot_placeholder_lbl)
        self._embedded_plot = None

        self._main_split.addWidget(self._plot_container)
        self._main_split.setSizes([550, 550])

        root.addWidget(self._main_split, 1)

        # --- Step simulation toolbar ---
        step_bar = QFrame()
        step_bar.setFixedHeight(38)
        step_bar.setStyleSheet(
            "QFrame { background: #2C3345; border-top: 1px solid #1A2030; }")
        sl = QHBoxLayout(step_bar)
        sl.setContentsMargins(8, 3, 8, 3)
        sl.setSpacing(6)

        sl.addWidget(QLabel("<span style='color:#A8B4C8;font-size:8pt;'>Step Sim:</span>"))

        self._step_btn = QPushButton("\u25b6 Step (F5)")
        self._step_btn.setObjectName("toolBtn")
        self._step_btn.clicked.connect(self._on_step_one)
        sl.addWidget(self._step_btn)

        self._run_btn = QPushButton("\u25b6\u25b6 Run (F6)")
        self._run_btn.setObjectName("greenBtn")
        self._run_btn.clicked.connect(self._on_run)
        sl.addWidget(self._run_btn)

        self._stop_btn = QPushButton("\u25a0 Stop (Esc)")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        sl.addWidget(self._stop_btn)

        self._reset_sim_btn = QPushButton("\u23ee Reset (F7)")
        self._reset_sim_btn.setObjectName("resetBtn")
        self._reset_sim_btn.clicked.connect(self._on_reset_sim)
        sl.addWidget(self._reset_sim_btn)

        # Step count
        sl.addWidget(QLabel("<span style='color:#A8B4C8;font-size:8pt;'>Steps:</span>"))
        self._step_count_spin = QSpinBox()
        self._step_count_spin.setRange(1, 500)
        self._step_count_spin.setValue(30)
        self._step_count_spin.setStyleSheet(
            "QSpinBox { font-size: 8pt; max-width: 60px; color: white; "
            "background: #3A4560; border: 1px solid #4A5570; }")
        self._step_count_spin.setToolTip("Number of steps for batch run")
        sl.addWidget(self._step_count_spin)

        # Speed
        sl.addWidget(QLabel("<span style='color:#A8B4C8;font-size:8pt;'>Speed:</span>"))
        self._speed_combo = QComboBox()
        self._speed_combo.setStyleSheet(
            "QComboBox { font-size: 8pt; max-width: 120px; color: white; "
            "background: #3A4560; border: 1px solid #4A5570; }")
        self._speed_options = [
            ("1x Real", 1), ("10x", 10), ("60x (1min/s)", 60),
            ("120x", 120), ("300x", 300), ("MAX", -1),
        ]
        for label, _ in self._speed_options:
            self._speed_combo.addItem(label)
        self._speed_combo.setCurrentIndex(2)  # 60x default
        sl.addWidget(self._speed_combo)

        # Step info
        self._step_info = QLabel("")
        self._step_info.setStyleSheet("color: #81C784; font-size: 8pt; font-weight: 600;")
        sl.addWidget(self._step_info)
        sl.addStretch()

        root.addWidget(step_bar)

        # --- Activity log (collapsible) ---
        log_bar = QHBoxLayout()
        log_bar.setContentsMargins(4, 2, 4, 0)
        log_toggle = QPushButton("\u25bc Activity Log")
        log_toggle.setStyleSheet(
            "QPushButton { background: none; border: none; color: #6B7394; "
            "font-size: 8pt; font-weight: 600; text-align: left; padding: 0; }"
            "QPushButton:hover { color: #3B5998; }")
        log_toggle.clicked.connect(self._toggle_log)
        log_bar.addWidget(log_toggle)
        log_bar.addStretch()
        log_clear = QPushButton("Clear")
        log_clear.setStyleSheet(
            "QPushButton { background: none; border: none; color: #8899AA; "
            "font-size: 7pt; } QPushButton:hover { color: #3B5998; }")
        log_clear.clicked.connect(lambda: self._log.clear())
        log_bar.addWidget(log_clear)
        root.addLayout(log_bar)

        self._log = QTextEdit()
        self._log.setObjectName("activityLog")
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        self._log.setMinimumHeight(0)
        root.addWidget(self._log)
        self._log_visible = True

        # Run timer
        self._run_timer = QTimer(self)
        self._run_timer.timeout.connect(self._on_tick)

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        self._log.setVisible(self._log_visible)

    # ================================================================ SHORTCUTS
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("F5"), self, self._on_step_one)
        QShortcut(QKeySequence("F6"), self, self._on_run)
        QShortcut(QKeySequence("Escape"), self, self._on_stop)
        QShortcut(QKeySequence("F7"), self, self._on_reset_sim)
        QShortcut(QKeySequence("Ctrl+Return"), self, self._on_simulate)
        QShortcut(QKeySequence("Ctrl+R"), self, self._on_reset)

    # ================================================================ TABLE
    def _make_table(self, editable=False):
        t = QTableWidget()
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setSelectionMode(QTableWidget.SingleSelection)
        t.verticalHeader().setDefaultSectionSize(21)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setHighlightSections(False)
        t.horizontalHeader().setMinimumSectionSize(40)
        t.setShowGrid(True)
        # Enable mouse tracking for hover highlight (via stylesheet)
        t.setMouseTracking(True)
        if not editable:
            t.setEditTriggers(QTableWidget.NoEditTriggers)
        # Right-click on header: column visibility
        t.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        t.horizontalHeader().customContextMenuRequested.connect(
            lambda pos, table=t: self._show_column_menu(table, pos))
        # Right-click on rows: variable context menu
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(
            lambda pos, table=t: self._show_var_context_menu(table, pos))
        return t

    def _show_column_menu(self, table, pos):
        """Right-click on header to show/hide columns."""
        menu = QMenu(self)
        for col in range(table.columnCount()):
            name = table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else f"Col {col}"
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(not table.isColumnHidden(col))
            act.toggled.connect(lambda checked, c=col: table.setColumnHidden(c, not checked))
        menu.exec(table.horizontalHeader().mapToGlobal(pos))

    def _show_var_context_menu(self, table, pos):
        """Right-click context menu on a variable row."""
        row = table.rowAt(pos.y())
        if row < 0:
            return

        # Determine variable name and type
        is_mv = (table is self.mv_table)
        var_list = self._mv_list if is_mv else self._cv_list
        if row >= len(var_list):
            return
        var = var_list[row]
        var_name = var.name

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #D0D4DC; font-size: 9pt; }"
            "QMenu::item { padding: 4px 20px; }"
            "QMenu::item:selected { background: #3B5998; color: white; }")

        # Variable info header
        header = menu.addAction(f"{var.var_type}: {var_name}")
        header.setEnabled(False)
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        menu.addSeparator()

        # Analysis actions
        menu.addAction("Why is it in this state?",
            lambda: self._run_chat(f"why {var_name}"))
        menu.addAction("What affects / is affected by it?",
            lambda: self._run_chat(f"affects {var_name}"))
        menu.addAction("Sensitivity analysis",
            lambda: self._run_chat(f"sensitivity {var_name}"))
        menu.addAction("Show headroom",
            lambda: self._run_chat(f"headroom {var_name}"))
        menu.addAction("Show tuning",
            lambda: self._run_chat(f"tuning {var_name}"))
        menu.addAction("Value trend (history)",
            lambda: self._run_chat(f"trend {var_name}"))

        menu.addSeparator()

        if not is_mv:
            # CV-specific actions
            if var.is_violated:
                menu.addAction("Fix this violation",
                    lambda: self._run_chat(f"fix {var_name}"))
            if var.is_ramp:
                menu.addAction("Ramp analysis",
                    lambda: self._run_chat(f"ramp {var_name}"))

        if is_mv:
            # MV-specific actions
            menu.addAction(f"How to increase {var_name}",
                lambda: self._run_chat(f"how increase {var_name}"))
            menu.addAction(f"How to decrease {var_name}",
                lambda: self._run_chat(f"how decrease {var_name}"))

        menu.addSeparator()
        menu.addAction("Copy value",
            lambda: self._copy_value(table, row))

        menu.exec(table.mapToGlobal(pos))

    def _run_chat(self, cmd):
        """Run an agent chat command and show result in activity log."""
        try:
            result = self.agent.ask(cmd)
            self._log_event(f"> {cmd}", "info")
            # Show result in a popup or the log
            for line in result.split("\n")[:20]:
                self._log_event(line, "info")
            if result.count("\n") > 20:
                self._log_event(f"  ... ({result.count(chr(10)) - 20} more lines)", "info")
        except Exception as e:
            self._log_event(f"Error: {e}", "error")

    def _copy_value(self, table, row):
        """Copy the selected row's tag and value to clipboard."""
        from PySide6.QtWidgets import QApplication
        tag = table.item(row, 0).text() if table.item(row, 0) else ""
        val = table.item(row, 1).text() if table.item(row, 1) else ""
        QApplication.clipboard().setText(f"{tag}\t{val}")

    # ================================================================ POPULATE
    def _populate(self):
        c = self.agent._classification
        self._mv_originals.clear()
        self._cv_originals.clear()
        self._n_edits = 0
        self._edit_summary.setText("")

        # --- MV table (matches DMC3 Tuning FIR ordering) ---
        headers = [h for h, _ in _MV_COLS]
        self.mv_table.setColumnCount(len(headers))
        self.mv_table.setHorizontalHeaderLabels(headers)
        active_mvs = [mv for mv in c.mvs if mv.is_active]
        self.mv_table.setRowCount(len(active_mvs))
        self._mv_list = active_mvs

        # Columns that should NOT be right-aligned (text columns)
        _MV_TEXT_COLS = {0, 5, 8, 13, 16, 21, 22}  # Name, MinMove, Reverse, LimTrack, Shed, Status, Desc

        for r, mv in enumerate(active_mvs):
            desc = mv.description[:20] + ".." if len(mv.description) > 22 else mv.description
            # Direction indicator for LP cost
            dir_icon = "+" if mv.cost_direction == "MAXIMIZE" else (
                "-" if mv.cost_direction == "MINIMIZE" else "=")
            cost_txt = f"{dir_icon} {mv.cost:.4f}"
            eng_lo = f"{mv.eng_lo_limit:.2f}" if mv.eng_lo_limit > -1e29 else ""
            eng_hi = f"{mv.eng_hi_limit:.2f}" if mv.eng_hi_limit < 1e29 else ""
            row_data = [
                mv.name,                                    # 0 Name
                f"{mv.value:.2f}",                          # 1 Measurement
                f"{mv.move_suppression:.3f}",               # 2 Move Supp
                f"{mv.max_move:.3f}",                       # 3 Max Move
                f"{mv.ss_move_limit:.3f}",                  # 4 SS Move Lim
                "Yes" if getattr(mv, 'ss_min_move', False) else "No",  # 5 MinMove Ctrl
                cost_txt,                                   # 6 LP Cost
                f"{mv.cost_rank}",                          # 7 Cost Rank
                "Yes" if mv.reverse_acting else "No",       # 8 Reverse
                f"{mv.lo_limit:.3f}",                       # 9 Lo Limit (editable)
                f"{mv.hi_limit:.3f}",                       # 10 Hi Limit (editable)
                eng_lo,                                     # 11 Eng Lo (read-only)
                eng_hi,                                     # 12 Eng Hi (read-only)
                f"{mv.val_lo_limit:.3f}" if mv.val_lo_limit > -1e29 else "",  # 13 Val Lo
                f"{mv.val_hi_limit:.3f}" if mv.val_hi_limit < 1e29 else "",  # 14 Val Hi
                "Yes" if mv.use_limit_tracking else "No",   # 15 Limit Track
                f"{mv.move_resolution:.4f}",                # 14 Move Res
                f"{mv.move_accumulation:.3f}",              # 15 Move Accum
                mv.shed_option,                             # 16 Shed Option
                f"{mv.typical_move:.3f}",                   # 17 Typical Move
                "",                                         # 18 Predicted (result)
                "",                                         # 19 Delta (result)
                "",                                         # 20 Last Move (result)
                mv.state_description,                       # 21 Status
                desc,                                       # 22 Desc
            ]
            for col, (txt, is_edit) in enumerate(zip(row_data, [e for _, e in _MV_COLS])):
                it = QTableWidgetItem(txt)
                if not is_edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(_CLR_EDITABLE)
                    self._mv_originals[(r, col)] = txt
                # Right-align numeric columns
                if col not in _MV_TEXT_COLS:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                # Tooltip: show full description + state
                if col == 0:
                    it.setToolTip(f"{mv.name}\n{mv.description}\n"
                                  f"State: {mv.state_description}\n"
                                  f"Direction: {mv.cost_direction}")
                # Color coding
                if mv.is_constrained and not is_edit:
                    it.setBackground(_CLR_CONSTRAINED)
                elif mv.state in ("bad_value", "out_of_service") and not is_edit:
                    it.setBackground(_CLR_BAD)
                self.mv_table.setItem(r, col, it)

        for col in range(len(_MV_COLS)):
            self.mv_table.setColumnHidden(col, col not in _MV_DEFAULT_VISIBLE)
        self.mv_table.resizeColumnsToContents()

        # --- CV table (matches DMC3 Tuning FIR ordering) ---
        cv_headers = [h for h, _ in _CV_COLS]
        self.cv_table.setColumnCount(len(cv_headers))
        self.cv_table.setHorizontalHeaderLabels(cv_headers)
        active_cvs = [cv for cv in c.cvs if cv.is_active]
        self.cv_table.setRowCount(len(active_cvs))
        self._cv_list = active_cvs

        _CV_TEXT_COLS = {0, 20, 27, 34, 35}  # Name, LimTrack, Ramp, Status, Desc

        for r, cv in enumerate(active_cvs):
            desc = cv.description[:20] + ".." if len(cv.description) > 22 else cv.description
            # Compute ECR from concern values:
            # ECR = 1/concern² (higher concern = tighter control = lower ECR)
            avg_concern = max((cv.ss_lo_concern + cv.ss_hi_concern) / 2, 0.01)
            ecr = 1.0 / (avg_concern ** 2)
            eng_lo = f"{cv.eng_lo_limit:.3f}" if cv.eng_lo_limit > -1e29 else ""
            eng_hi = f"{cv.eng_hi_limit:.3f}" if cv.eng_hi_limit < 1e29 else ""
            val_lo = f"{cv.val_lo_limit:.3f}" if cv.val_lo_limit > -1e29 else ""
            val_hi = f"{cv.val_hi_limit:.3f}" if cv.val_hi_limit < 1e29 else ""
            row_data = [
                cv.name,                                    # 0 Name
                f"{cv.value:.3f}",                          # 1 Value
                f"{cv.ss_target:.3f}",                      # 2 SS Pred
                f"{cv.lo_limit:.3f}",                       # 3 Lo Limit (editable)
                f"{cv.hi_limit:.3f}",                       # 4 Hi Limit (editable)
                eng_lo,                                     # 5 Eng Lo (read-only)
                eng_hi,                                     # 6 Eng Hi (read-only)
                val_lo,                                     # 7 Val Lo (read-only)
                val_hi,                                     # 8 Val Hi (read-only)
                f"{cv.ss_lo_rank}",                         # 9 SS Lo Rank
                f"{cv.ss_hi_rank}",                         # 10 SS Hi Rank
                f"{cv.ss_lo_concern:.3f}",                  # 11 SS Lo Concern
                f"{cv.ss_hi_concern:.3f}",                  # 12 SS Hi Concern
                f"{cv.cv_cost_rank}",                       # 13 Cost Rank
                f"{cv.cv_cost:.3f}",                        # 14 LP Cost
                f"{cv.dyn_lo_concern:.3f}",                 # 15 Dyn Lo Concern
                f"{cv.dyn_hi_concern:.3f}",                 # 16 Dyn Hi Concern
                f"{cv.dyn_target_concern:.4f}",             # 17 Dyn Tgt Concern
                f"{cv.dyn_lo_zone:.3f}",                    # 18 Dyn Lo Zone
                f"{cv.dyn_hi_zone:.3f}",                    # 19 Dyn Hi Zone
                "Yes" if hasattr(cv, 'use_limit_tracking') and cv.use_limit_tracking else "No",  # 20 Limit Track
                f"{cv.max_ss_cv_step:.3f}",                 # 21 Max SS Step
                f"{ecr:.4f}",                               # 22 ECR
                f"{cv.weight:.4f}",                         # 23 Weight
                "",                                         # 24 Predicted (result)
                "",                                         # 25 Delta (result)
                "",                                         # 26 Violation (result)
                "Yes" if cv.is_ramp else "No",              # 27 Ramp
                f"{cv.ramp_setpoint:.2f}",                  # 28 Ramp SP
                f"{cv.ramp_rate:.2f}",                      # 29 Ramp Rate
                f"{cv.ramp_max_imbalances}",                # 30 Max Imbal
                f"{cv.ramp_horizon}",                       # 31 Ramp Horizon
                f"{cv.ramp_rotation_factor:.2f}",           # 32 Rotation
                f"{cv.pred_error:.4f}",                     # 33 Pred Err
                cv.state_description,                       # 34 Status
                desc,                                       # 35 Desc
            ]
            for col, (txt, is_edit) in enumerate(zip(row_data, [e for _, e in _CV_COLS])):
                it = QTableWidgetItem(txt)
                if not is_edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(_CLR_EDITABLE)
                    self._cv_originals[(r, col)] = txt
                # Right-align numeric columns
                if col not in _CV_TEXT_COLS:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                # Tooltip on Name
                if col == 0:
                    it.setToolTip(f"{cv.name}\n{cv.description}\n"
                                  f"State: {cv.state_description}\n"
                                  f"Limits: [{cv.lo_limit:.3f}, {cv.hi_limit:.3f}]")
                # Color coding
                if cv.is_violated and not is_edit:
                    it.setBackground(_CLR_VIOLATED)
                elif cv.is_constrained and not is_edit:
                    it.setBackground(_CLR_CONSTRAINED)
                elif cv.state == "ramp" and not is_edit:
                    it.setBackground(_CLR_RAMP)
                elif cv.state in ("bad_value", "out_of_service") and not is_edit:
                    it.setBackground(_CLR_BAD)
                self.cv_table.setItem(r, col, it)

        for col in range(len(_CV_COLS)):
            self.cv_table.setColumnHidden(col, col not in _CV_DEFAULT_VISIBLE)
        self.cv_table.resizeColumnsToContents()

        # Connect cell change for edit highlighting
        self.mv_table.cellChanged.connect(self._on_mv_cell_changed)
        self.cv_table.cellChanged.connect(self._on_cv_cell_changed)

        # Init step sim
        self._init_step_sim()
        self._log_event("Ready", "info")

    # ================================================================ EDIT HIGHLIGHT
    def _on_mv_cell_changed(self, row, col):
        orig = self._mv_originals.get((row, col))
        if orig is None:
            return
        item = self.mv_table.item(row, col)
        if item is None:
            return
        current = item.text().strip()
        if current != orig:
            item.setBackground(_CLR_EDITED)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        else:
            item.setBackground(_CLR_EDITABLE)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
        self._update_edit_count()

    def _on_cv_cell_changed(self, row, col):
        orig = self._cv_originals.get((row, col))
        if orig is None:
            return
        item = self.cv_table.item(row, col)
        if item is None:
            return
        current = item.text().strip()
        if current != orig:
            item.setBackground(_CLR_EDITED)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        else:
            item.setBackground(_CLR_EDITABLE)
            font = item.font()
            font.setBold(False)
            item.setFont(font)
        self._update_edit_count()

    def _update_edit_count(self):
        n = 0
        for (r, c), orig in self._mv_originals.items():
            item = self.mv_table.item(r, c)
            if item and item.text().strip() != orig:
                n += 1
        for (r, c), orig in self._cv_originals.items():
            item = self.cv_table.item(r, c)
            if item and item.text().strip() != orig:
                n += 1
        self._n_edits = n
        if n > 0:
            self._edit_summary.setText(f"{n} value(s) changed")
        else:
            self._edit_summary.setText("")

    # ================================================================ GATHER VALUES
    def _gather_limits(self):
        mv_lo, mv_hi = {}, {}
        for r, mv in enumerate(self._mv_list):
            try:
                lo = float(self.mv_table.item(r, _MV_LO).text())
                if abs(lo - mv.lo_limit) > 1e-6:
                    mv_lo[mv.name] = lo
            except (ValueError, AttributeError):
                pass
            try:
                hi = float(self.mv_table.item(r, _MV_HI).text())
                if abs(hi - mv.hi_limit) > 1e-6:
                    mv_hi[mv.name] = hi
            except (ValueError, AttributeError):
                pass

        cv_lo, cv_hi = {}, {}
        for r, cv in enumerate(self._cv_list):
            try:
                lo = float(self.cv_table.item(r, _CV_LO).text())
                if abs(lo - cv.lo_limit) > 1e-6:
                    cv_lo[cv.name] = lo
            except (ValueError, AttributeError):
                pass
            try:
                hi = float(self.cv_table.item(r, _CV_HI).text())
                if abs(hi - cv.hi_limit) > 1e-6:
                    cv_hi[cv.name] = hi
            except (ValueError, AttributeError):
                pass

        return mv_lo, mv_hi, cv_lo, cv_hi

    def _gather_mv_tuning(self):
        tuning = {}
        for r, mv in enumerate(self._mv_list):
            tun = {}
            for col, key, orig in [
                (_MV_COST, "cost", mv.cost),
                (_MV_RANK, "rank", mv.cost_rank),
                (_MV_MAXMOVE, "max_move", mv.max_move),
                (_MV_MOVESUPP, "move_supp", mv.move_suppression),
            ]:
                try:
                    tun[key] = float(self.mv_table.item(r, col).text())
                except (ValueError, AttributeError):
                    tun[key] = orig
            tuning[mv.name] = tun
        return tuning

    # ================================================================ SIMULATE
    def _set_state(self, state):
        """Update the state indicator: IDLE, SIMULATING, RUNNING, STOPPED."""
        styles = {
            "IDLE": "background: #E8EAF0; color: #6B7394;",
            "SIMULATING": "background: #FFF3E0; color: #E65100;",
            "RUNNING": "background: #E8F5E9; color: #2E7D32;",
            "STOPPED": "background: #E8EAF0; color: #6B7394;",
        }
        self._state_lbl.setText(f"  {state}  ")
        self._state_lbl.setStyleSheet(
            f"QLabel#stateIndicator {{ {styles.get(state, styles['IDLE'])} }}")

    def _on_simulate(self):
        self._set_state("SIMULATING")
        if not self.agent or self.agent._K_u is None:
            self._feasible_lbl.setText("  No gain matrix  ")
            self._feasible_lbl.setStyleSheet(
                "QLabel#feasible { background: #FFEBEE; color: #C62828; }")
            self._set_state("IDLE")
            return

        c = self.agent._classification
        solver = self.agent._solver
        mv_lo, mv_hi, cv_lo, cv_hi = self._gather_limits()

        try:
            ss = solver.simulate_whatif(
                c.mvs, c.cvs,
                mv_lo_new=mv_lo, mv_hi_new=mv_hi,
                cv_lo_new=cv_lo, cv_hi_new=cv_hi)

            self._last_ss = ss
            self._last_limits = (mv_lo, mv_hi, cv_lo, cv_hi)
            self._show_results(ss, c, mv_lo, mv_hi, cv_lo, cv_hi)
            self._create_embedded_plot()
            self._init_step_sim()
            self._log_event(
                f"Simulate: {'FEASIBLE' if ss.feasible else f'INFEASIBLE ({ss.n_violations} violations)'}",
                "ok" if ss.feasible else "error")
            self._set_state("IDLE")
        except Exception as e:
            self._feasible_lbl.setText(f"  Error: {e}  ")
            self._log_event(f"Simulate error: {e}", "error")
            self._set_state("IDLE")

    def _show_results(self, ss, c, mv_lo, mv_hi, cv_lo, cv_hi):
        """Update the Predicted/Delta/Violation columns in the unified tables."""
        if ss.feasible:
            self._feasible_lbl.setText("  FEASIBLE  ")
            self._feasible_lbl.setStyleSheet(
                "QLabel#feasible { background: #E8F5E9; color: #2E7D32; }")
        else:
            self._feasible_lbl.setText(
                f"  INFEASIBLE \u2014 {ss.n_violations} violation(s)  ")
            self._feasible_lbl.setStyleSheet(
                "QLabel#feasible { background: #FFEBEE; color: #C62828; }")

        # Update MV result columns in the unified MV table
        # Map solver MV names to their index in ss_result arrays (FF-excluded)
        solver_mv_names = getattr(self.agent, '_mv_names', None) or [mv.name for mv in c.mvs]
        mv_idx_map = {name: i for i, name in enumerate(solver_mv_names)}
        for r, mv in enumerate(self._mv_list):
            gi = mv_idx_map.get(mv.name)
            if gi is None:
                continue
            delta = float(ss.u_delta[gi])
            pred_txt = f"{ss.u_after[gi]:.3f}"
            delta_txt = f"{delta:+.4f}" if abs(delta) > 1e-6 else ""

            for col, txt in [(_MV_PRED, pred_txt), (_MV_DELTA, delta_txt)]:
                item = self.mv_table.item(r, col)
                if item:
                    item.setText(txt)
                    if abs(delta) > 1e-4:
                        item.setBackground(_CLR_RESULT_CHANGE)
                    else:
                        item.setBackground(QColor("white"))

        # Update CV result columns in the unified CV table
        cv_idx_map = {cv.name: i for i, cv in enumerate(c.cvs)}
        for r, cv in enumerate(self._cv_list):
            gi = cv_idx_map.get(cv.name)
            if gi is None:
                continue
            delta = float(ss.y_delta[gi])
            lo = cv_lo.get(cv.name, cv.lo_limit)
            hi = cv_hi.get(cv.name, cv.hi_limit)
            pred_txt = f"{ss.y_after[gi]:.3f}"
            delta_txt = f"{delta:+.4f}" if abs(delta) > 1e-4 else ""
            viol_txt = ""
            is_viol = False
            if cv.is_active:
                if ss.y_after[gi] > hi + 1e-4:
                    viol_txt = f"+{ss.y_after[gi] - hi:.3f}"
                    is_viol = True
                elif ss.y_after[gi] < lo - 1e-4:
                    viol_txt = f"{ss.y_after[gi] - lo:.3f}"
                    is_viol = True

            for col, txt in [(_CV_PRED, pred_txt), (_CV_DELTA, delta_txt),
                             (_CV_VIOL, viol_txt)]:
                item = self.cv_table.item(r, col)
                if item:
                    item.setText(txt)
                    if is_viol:
                        item.setBackground(_CLR_RESULT_VIOL)
                    elif abs(delta) > 1e-4:
                        item.setBackground(_CLR_RESULT_CHANGE)
                    else:
                        item.setBackground(QColor("white"))

    # ================================================================ STEP SIM
    def _init_step_sim(self):
        if not self.agent or self.agent._K_u is None:
            return
        from .step_sim import StepSimulator
        c = self.agent._classification
        mv_lo, mv_hi, cv_lo, cv_hi = self._gather_limits()

        # StepSimulator needs ALL MVs (including FF) — use raw K_u
        K_raw = getattr(self.agent, '_K_u_raw', self.agent._K_u)
        self._step_sim = StepSimulator(
            K_raw, c.mvs, c.cvs,
            self.agent._fir, self.agent._num_coeff or 60,
            self.agent._cycle_time or 60)
        self._step_sim.set_limits(
            mv_lo_new=mv_lo, mv_hi_new=mv_hi,
            cv_lo_new=cv_lo, cv_hi_new=cv_hi)

        # Apply tuning from table
        mv_names = [m.name for m in c.mvs]
        for name, tun in self._gather_mv_tuning().items():
            if name in mv_names:
                idx = mv_names.index(name)
                if tun.get("max_move", 0) > 0:
                    self._step_sim._max_move[idx] = tun["max_move"]
                if tun.get("move_supp", 0) > 0:
                    self._step_sim._move_supp[idx] = max(tun["move_supp"], 1.0)

        ct = self._step_sim._cycle_time
        self._step_info.setText(f"Step 0 | Cycle {ct:.0f}s | Ready")

    def _on_step_one(self):
        if not self._step_sim:
            self._init_step_sim()
            if not self._step_sim:
                return
        # Create embedded plot on first step if not already present
        if not self._embedded_plot:
            self._on_simulate()  # run SS first to get _last_ss for plot
        state = self._step_sim.step()
        self._update_step_display(state)

    def _on_run(self):
        if not self._step_sim:
            self._init_step_sim()
            if not self._step_sim:
                return

        idx = self._speed_combo.currentIndex()
        _, mult = self._speed_options[idx]
        cycle_ms = self._step_sim._cycle_time * 1000

        if mult == -1:
            interval = 20
            self._steps_per_tick = 5
        elif mult >= 300:
            interval = 50
            self._steps_per_tick = max(1, int(mult * 0.05 / (cycle_ms / 1000)))
        else:
            interval = max(int(cycle_ms / mult), 20)
            self._steps_per_tick = 1

        self._run_timer.start(interval)
        self._run_btn.setEnabled(False)
        self._step_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._set_state("RUNNING")
        self._log_event("Run started", "info")

    def _on_tick(self):
        if not self._step_sim:
            self._on_stop()
            return
        for _ in range(self._steps_per_tick):
            state = self._step_sim.step()
        self._update_step_display(state)

    def _on_stop(self):
        self._run_timer.stop()
        self._run_btn.setEnabled(True)
        self._step_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._set_state("IDLE")
        self._log_event("Run stopped", "info")

    def _on_reset_sim(self):
        self._on_stop()
        self._init_step_sim()
        self._log_event("Simulation reset", "info")

    def _on_reset(self):
        self._on_stop()
        # Disconnect to avoid triggering cell change events during repopulate
        try:
            self.mv_table.cellChanged.disconnect()
            self.cv_table.cellChanged.disconnect()
        except RuntimeError:
            pass
        self._populate()
        self._log_event("Limits reset to original", "info")

    def _update_step_display(self, state):
        n = self._step_sim.history.n_steps() - 1
        viol = len(state.cv_violations)
        lim = len(state.mv_at_limit)
        aborts = len(state.ramp_aborts)

        color = "#81C784" if viol == 0 else "#E57373"
        self._step_info.setText(
            f"Step {n} | T={state.time_min:.1f}min | "
            f"{lim} at limit | {viol} viol")
        self._step_info.setStyleSheet(f"color: {color}; font-size: 8pt; font-weight: 600;")

        # Log significant events
        for ci, amt in state.cv_violations:
            cv_name = self.agent._classification.cvs[ci].name if ci < len(self.agent._classification.cvs) else f"CV[{ci}]"
            self._log_event(f"Step {n}: {cv_name} violated by {amt:+.3f}", "warn")
        for ci, msg in state.ramp_aborts:
            self._log_event(f"Step {n}: Ramp abort — {msg}", "error")

        # Update result tables in-place (fast)
        c = self.agent._classification
        h = self._step_sim.history
        initial = h.steps[0]

        # Update unified MV table result columns in-place
        mv_idx_map = {mv.name: i for i, mv in enumerate(c.mvs)}
        for r, mv in enumerate(self._mv_list):
            gi = mv_idx_map.get(mv.name)
            if gi is None:
                continue
            delta = state.u[gi] - initial.u[gi]
            pred_txt = f"{state.u[gi]:.3f}"
            delta_txt = f"{delta:+.4f}" if abs(delta) > 1e-6 else ""
            move_txt = f"{state.moves[gi]:+.4f}" if abs(state.moves[gi]) > 1e-8 else ""
            at_lim = any(idx == gi for idx, _ in state.mv_at_limit)

            for col, txt in [(_MV_PRED, pred_txt), (_MV_DELTA, delta_txt),
                             (_MV_LASTMOVE, move_txt)]:
                item = self.mv_table.item(r, col)
                if item:
                    item.setText(txt)
                    bg = _CLR_CONSTRAINED if at_lim else (
                        _CLR_RESULT_CHANGE if abs(delta) > 1e-4 else QColor("white"))
                    item.setBackground(bg)

        # Update unified CV table result columns in-place
        cv_idx_map = {cv.name: i for i, cv in enumerate(c.cvs)}
        for r, cv in enumerate(self._cv_list):
            gi = cv_idx_map.get(cv.name)
            if gi is None:
                continue
            delta = state.y[gi] - initial.y[gi]
            pred_txt = f"{state.y[gi]:.3f}"
            delta_txt = f"{delta:+.4f}" if abs(delta) > 1e-4 else ""
            viol_txt = ""
            is_viol = False
            for vi, va in state.cv_violations:
                if vi == gi:
                    viol_txt = f"{va:+.3f}"
                    is_viol = True

            for col, txt in [(_CV_PRED, pred_txt), (_CV_DELTA, delta_txt),
                             (_CV_VIOL, viol_txt)]:
                item = self.cv_table.item(r, col)
                if item:
                    item.setText(txt)
                    bg = _CLR_RESULT_VIOL if is_viol else (_CLR_RESULT_CHANGE if abs(delta) > 1e-4 else QColor("white"))
                    item.setBackground(bg)

        # Update plot if open
        self._update_plot()

    # ================================================================ PLOT
    def _create_initial_plot(self):
        """Create prediction plots immediately on open using current state (no changes)."""
        if not self.agent or self.agent._K_u is None:
            return
        try:
            c = self.agent._classification
            solver = self.agent._solver
            # Run baseline simulation with no limit changes
            ss = solver.simulate_whatif(c.mvs, c.cvs)
            self._last_ss = ss
            self._last_limits = ({}, {}, {}, {})
            self._create_embedded_plot()
            self._log_event("Plots loaded from current controller state", "ok")
        except Exception as e:
            self._log_event(f"Initial plot: {e}", "warn")

    def _create_embedded_plot(self):
        """Create or refresh the embedded prediction plot."""
        if not self.agent or not self.agent._solver:
            return
        if not hasattr(self, '_last_ss'):
            return

        c = self.agent._classification
        mv_lo, mv_hi, cv_lo, cv_hi = self._gather_limits()

        try:
            from .prediction import compute_predictions
            from .prediction_plot import PredictionPlotWindow

            pred = compute_predictions(
                self._last_ss, c.mvs, c.cvs,
                fir_data=self.agent._fir,
                num_coeff=self.agent._num_coeff or 60,
                cycle_time=self.agent._cycle_time or 60,
                mv_lo_new=mv_lo, mv_hi_new=mv_hi,
                cv_lo_new=cv_lo, cv_hi_new=cv_hi)

            # Remove old plot
            if self._embedded_plot:
                self._plot_container_lay.removeWidget(self._embedded_plot)
                self._embedded_plot.deleteLater()
                self._embedded_plot = None
            if self._plot_placeholder_lbl:
                self._plot_container_lay.removeWidget(self._plot_placeholder_lbl)
                self._plot_placeholder_lbl.deleteLater()
                self._plot_placeholder_lbl = None

            # Create new plot as embedded widget (not standalone window)
            plot = PredictionPlotWindow(
                pred, title=c.name,
                solver=self.agent._solver,
                mv_states=c.mvs, cv_states=c.cvs,
                fir_data=self.agent._fir,
                num_coeff=self.agent._num_coeff or 60,
                cycle_time=self.agent._cycle_time or 60,
                mv_lo_new=mv_lo, mv_hi_new=mv_hi,
                cv_lo_new=cv_lo, cv_hi_new=cv_hi,
                parent=self._plot_container)
            # Override: don't show as standalone window
            plot.setWindowFlags(Qt.Widget)
            self._plot_container_lay.addWidget(plot)
            self._embedded_plot = plot
            self._plot_window = plot  # for live update reference

        except Exception as e:
            self._log_event(f"Plot error: {e}", "error")

    def _update_plot(self):
        """Push step simulator history to embedded plot."""
        if self._embedded_plot and self._step_sim:
            try:
                self._embedded_plot.update_from_history(self._step_sim.history)
            except (RuntimeError, AttributeError):
                self._embedded_plot = None

    # ================================================================ SCENARIOS
    def _save_scenario(self):
        mv_lo, mv_hi, cv_lo, cv_hi = self._gather_limits()
        n = len(self._scenarios) + 1
        name = f"Scenario {n}"
        sc = Scenario(
            name=name, timestamp=datetime.now(),
            mv_lo=mv_lo, mv_hi=mv_hi, cv_lo=cv_lo, cv_hi=cv_hi,
            feasible=getattr(self, '_last_ss', None) is not None and
                     getattr(self, '_last_ss', None).feasible if hasattr(self, '_last_ss') else True,
            n_violations=getattr(self, '_last_ss', None).n_violations if hasattr(self, '_last_ss') and self._last_ss else 0,
        )
        self._scenarios.append(sc)
        self._scenario_combo.clear()
        for s in self._scenarios:
            label = f"{s.name} ({s.timestamp.strftime('%H:%M')}) — {'OK' if s.feasible else f'{s.n_violations} viol'}"
            self._scenario_combo.addItem(label)
        self._log_event(f"Saved: {name}", "ok")

    # ================================================================ ACTIVITY LOG
    def _log_event(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {"info": "#A8B4C8", "ok": "#81C784", "warn": "#FFB74D", "error": "#E57373"}
        color = colors.get(level, "#A8B4C8")
        self._log.append(
            f'<span style="color:#6B7394;">{ts}</span> '
            f'<span style="color:{color};">{msg}</span>')
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
