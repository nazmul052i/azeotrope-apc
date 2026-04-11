"""Standalone What-If Simulator.

Unified layout with:
- Left panel: editable MV/CV tables with column visibility, edit highlighting
- Right panel: embedded prediction strip charts (pyqtgraph)
- Bottom: activity log + step simulation toolbar with keyboard shortcuts
"""

import os
import sys
import numpy as np
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QHeaderView,
    QTextEdit, QFrame, QComboBox, QMenu, QSpinBox, QScrollArea,
    QRadioButton, QButtonGroup,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut

import pyqtgraph as pg


class TimeAxisItem(pg.AxisItem):
    """Custom x-axis that converts cycle offsets to time labels.

    The plot's x-coordinate is "samples relative to now" (e.g., -200..+30).
    This axis converts each tick to a time string showing minutes/seconds
    relative to the current moment.
    """

    def __init__(self, sample_time_min: float = 1.0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sample_time_min = sample_time_min

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            mins = v * self.sample_time_min
            if mins == 0:
                out.append("now")
            elif abs(mins) >= 60:
                hh = int(mins // 60)
                mm = int(abs(mins) % 60)
                sign = "-" if mins < 0 else "+"
                out.append(f"{sign}{abs(hh)}h{mm:02d}")
            elif abs(mins) >= 1:
                sign = "-" if mins < 0 else "+"
                out.append(f"{sign}{int(abs(mins))}m")
            else:
                ss = int(abs(mins) * 60)
                sign = "-" if mins < 0 else "+"
                out.append(f"{sign}{ss}s")
        return out


# ---- C++ core bindings ----
# __file__ is apps/apc_architect/whatif_window.py -- climb to repo root,
# then into build/bindings/Release.
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'build', 'bindings', 'Release')))
try:
    import _azeoapc_core as core
    _HAS_CORE = True
except ImportError:
    _HAS_CORE = False

from azeoapc.sim_engine import SimEngine
from azeoapc.models.config_loader import SimConfig
from azeoapc.models.variables import MV_OPT_TYPES, CV_OPT_TYPES

from .theme.deltav_silver import COLORS

# ---- Column definitions (matching DMC3 Builder) ----
# Each: (header, editable, group)
# Groups: "ident"=identity, "oper"=operating, "limits"=limits,
#         "tuning"=tuning, "econ"=economics, "result"=results, "ctrl"=control, "plot"=plot

MV_COLS = [
    # Identity
    ("Inputs", False, "ident"),              # 0
    ("Description", False, "ident"),         # 1
    ("Units", False, "ident"),               # 2
    ("Subcontroller", False, "ident"),       # 3
    # Status
    ("Combined Status", False, "oper"),      # 4
    ("Service Request", False, "oper"),      # 5
    ("Service Status", False, "oper"),       # 6
    # Operating
    ("Measurement", False, "oper"),          # 7
    # Limits: Val Lo | Eng Lo | OP Lo | SS Value | OP Hi | Eng Hi | Val Hi
    ("Validity Lo", False, "limits"),        # 8
    ("Eng Lo", False, "limits"),             # 9
    ("Operator Lo", True, "limits"),         # 10
    ("SS Value", False, "oper"),             # 11
    ("Operator Hi", True, "limits"),         # 12
    ("Eng Hi", False, "limits"),             # 13
    ("Validity Hi", False, "limits"),        # 14
    # SS results
    ("Ideal SS", False, "result"),           # 15
    ("Ideal Constraint", False, "result"),   # 16
    ("Current Move", False, "result"),       # 17
    # Tuning
    ("Move Suppression", True, "tuning"),    # 18
    ("Move Supp Incr", True, "tuning"),      # 19
    ("Max Move", True, "tuning"),            # 20
    ("Move Resolution", True, "tuning"),     # 21
    ("Move Accumulation", True, "tuning"),   # 22
    ("Target Suppression", True, "tuning"),  # 23
    ("MinMove Criterion", False, "tuning"),  # 24
    ("Dyn Min Movement", False, "tuning"),   # 25
    # Economics
    ("LP Cost", True, "econ"),               # 26
    ("Shadow Price", False, "econ"),         # 27
    ("Cost Rank", True, "econ"),             # 28
    ("Active Constraint", False, "econ"),    # 29
    # Control
    ("Reverse Acting", False, "ctrl"),       # 30
    ("Anti Windup", False, "ctrl"),          # 31
    ("Loop Status", False, "ctrl"),          # 32
    ("Setpoint", False, "ctrl"),             # 33
    ("Is FeedForward", False, "ctrl"),       # 34
    ("Use Limit Track", False, "ctrl"),      # 35
    ("Shed Option", False, "ctrl"),          # 36
    # Plot
    ("Plot Lo", True, "plot"),               # 37
    ("Plot Hi", True, "plot"),               # 38
    ("Plot Auto Scale", False, "plot"),      # 39
    # Results
    ("Predicted", False, "result"),          # 40
    ("Delta", False, "result"),              # 41
    ("Last Move", False, "result"),          # 42
    ("Transformed Tgt", False, "result"),    # 43
    ("Transformed Meas", False, "result"),   # 44
    ("Status", False, "result"),             # 45
    ("Opt Type", True, "econ"),              # 46  <-- NEW: combo box
]
_MV_TAG = 0; _MV_DESC = 1; _MV_UNITS = 2
_MV_VALUE = 7
_MV_VAL_LO = 8; _MV_ENG_LO = 9; _MV_LO = 10
_MV_SS = 11
_MV_HI = 12; _MV_ENG_HI = 13; _MV_VAL_HI = 14
_MV_IDEAL_SS = 15; _MV_CURMOVE = 17
_MV_MOVESUPP = 18; _MV_MAXMOVE = 20; _MV_MOVERES = 21; _MV_MOVEACC = 22
_MV_COST = 26; _MV_RANK = 28; _MV_SETPOINT = 33
_MV_PLOTLO = 37; _MV_PLOTHI = 38
_MV_PRED = 40; _MV_DELTA = 41; _MV_LASTMOVE = 42
_MV_STATUS = 45
_MV_OPT_TYPE = 46
_MV_TEXT_COLS = {0, 1, 2, 3, 4, 5, 6, 24, 25, 30, 31, 32, 34, 35, 36, 39, 45, 46}

# Groups for Entry Type / Value Type radio filters
_MV_OPER_COLS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 26, 45, 46}
_MV_TUNING_COLS = {0, 1, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 46}
_MV_RESULT_COLS = {0, 1, 7, 11, 15, 16, 17, 40, 41, 42, 43, 44, 45, 46}
# Add Opt Type to default visible (right after Description)
_MV_DEFAULT_VISIBLE = {0, 1, 46, 2, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 26, 45}

DV_COLS = [
    ("Inputs", False, "ident"),              # 0
    ("Description", False, "ident"),         # 1
    ("Units", False, "ident"),               # 2
    ("Measurement", False, "oper"),          # 3
    ("Value", True, "oper"),                 # 4
    ("Eng Lo", False, "limits"),             # 5
    ("Eng Hi", False, "limits"),             # 6
    ("Plot Lo", True, "plot"),               # 7
    ("Plot Hi", True, "plot"),               # 8
    ("Status", False, "oper"),               # 9
]
_DV_VALUE = 4; _DV_MEAS = 3
_DV_TEXT_COLS = {0, 1, 2, 9}
_DV_DEFAULT_VISIBLE = {0, 1, 2, 3, 4, 5, 6, 9}

CV_COLS = [
    # Identity
    ("Outputs", False, "ident"),             # 0
    ("Description", False, "ident"),         # 1
    ("Units", False, "ident"),               # 2
    ("Subcontroller", False, "ident"),       # 3
    # Status
    ("Combined Status", False, "oper"),      # 4
    ("Service Request", False, "oper"),      # 5
    ("Service Status", False, "oper"),       # 6
    # Operating
    ("Measurement", False, "oper"),          # 7
    # Limits: Val Lo | Eng Lo | OP Lo | SS Value | OP Hi | Eng Hi | Val Hi
    ("Validity Lo", False, "limits"),        # 8
    ("Eng Lo", False, "limits"),             # 9
    ("Operator Lo", True, "limits"),         # 10
    ("SS Value", False, "oper"),             # 11
    ("Operator Hi", True, "limits"),         # 12
    ("Eng Hi", False, "limits"),             # 13
    ("Validity Hi", False, "limits"),        # 14
    # SS results
    ("Ideal SS", False, "result"),           # 15
    ("Ideal Constraint", False, "result"),   # 16
    # SS Tuning
    ("SS Lo Rank", True, "tuning"),          # 17
    ("SS Hi Concern", True, "tuning"),       # 18
    ("SS Hi Rank", True, "tuning"),          # 19
    ("Cost Rank", True, "econ"),             # 20
    ("LP Cost", True, "econ"),               # 21
    ("Control Weight", True, "tuning"),      # 22
    ("Max SS Step", True, "tuning"),         # 23
    # Dynamic Tuning
    ("Dyn Lo Concern", True, "tuning"),      # 24
    ("Dyn Hi Concern", True, "tuning"),      # 25
    ("Dyn Tgt Concern", True, "tuning"),     # 26
    ("Dyn Lo Zone", True, "tuning"),         # 27
    ("Dyn Hi Zone", True, "tuning"),         # 28
    # Ramp
    ("Ramp", False, "ctrl"),                 # 29
    ("Ramp SP", True, "ctrl"),               # 30
    ("Ramp Rate", True, "ctrl"),             # 31
    ("Ramp Horizon", True, "ctrl"),          # 32
    ("Rotation Factor", True, "ctrl"),       # 33
    ("Max Imbalance", True, "ctrl"),         # 34
    # Noise / transform
    ("Simulation Noise", True, "tuning"),    # 35
    ("Pred Error", False, "result"),         # 36
    # Plot
    ("Plot Lo", True, "plot"),               # 37
    ("Plot Hi", True, "plot"),               # 38
    ("Plot Auto Scale", False, "plot"),      # 39
    # Results
    ("Prediction", False, "result"),         # 40
    ("Delta", False, "result"),              # 41
    ("Violation", False, "result"),          # 42
    ("Model Prediction", False, "result"),   # 43
    ("Pred Next Cycle", False, "result"),    # 44
    ("Status", False, "result"),             # 45
    ("Critical", False, "result"),           # 46
    ("Opt Type", True, "econ"),              # 47  <-- NEW: combo box
]
_CV_TAG = 0; _CV_DESC = 1; _CV_UNITS = 2
_CV_VALUE = 7
_CV_VAL_LO = 8; _CV_ENG_LO = 9; _CV_LO = 10
_CV_SS = 11
_CV_HI = 12; _CV_ENG_HI = 13; _CV_VAL_HI = 14
_CV_IDEAL_SS = 15
_CV_SSLORANK = 17; _CV_SSHICONCERN = 18; _CV_SSHIRANK = 19
_CV_COSTRANK = 20; _CV_LPCOST = 21
_CV_WEIGHT = 22; _CV_MAXSSSTEP = 23
_CV_DYNLOCONCERN = 24; _CV_DYNHICONCERN = 25; _CV_DYNTGTCONCERN = 26
_CV_RAMP = 29; _CV_RAMPSP = 30; _CV_RAMPRATE = 31
_CV_NOISE = 35; _CV_PREDERR = 36
_CV_PLOTLO = 37; _CV_PLOTHI = 38
_CV_PRED = 40; _CV_DELTA = 41; _CV_VIOL = 42
_CV_STATUS = 45
_CV_OPT_TYPE = 47
_CV_TEXT_COLS = {0, 1, 2, 3, 4, 5, 6, 29, 39, 45, 46, 47}

_CV_OPER_COLS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 21, 40, 36, 45, 47}
_CV_TUNING_COLS = {0, 1, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 37, 38, 39, 47}
_CV_RESULT_COLS = {0, 1, 7, 11, 15, 16, 40, 41, 42, 43, 44, 36, 45, 46, 47}
_CV_DEFAULT_VISIBLE = {0, 1, 47, 2, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 21, 36, 40, 45}

# ---- Style (matches whatif.py) ----

# The bulk of the chrome (background, fonts, tables, tabs, scroll bars,
# group boxes, line edits, etc.) now comes from the canonical
# DeltaV Live Silver stylesheet installed at the QApplication level
# in app.py. This local block keeps only the named-button colours
# (toolBtn / stopBtn / greenBtn / tealBtn / resetBtn) and the few
# Qt object-name selectors that the WhatIf simulator uses, all
# routed through the shared palette so they stay in sync.
from azeoapc.theme import SILVER as _SILVER

_STYLE = f"""
QLabel#title {{ font-size: 12pt; font-weight: 600;
    color: {_SILVER['text_primary']}; }}
QLabel#subtitle {{ font-size: 8pt; color: {_SILVER['text_muted']}; }}
QLabel#feasible {{ font-size: 9pt; font-weight: bold;
    padding: 3px 10px; border-radius: 4px; }}
QLabel#editSummary {{ font-size: 8pt; color: {_SILVER['accent_blue']};
    font-weight: 500; padding: 2px 6px;
    background: {_SILVER['bg_secondary']}; border-radius: 3px; }}
QLabel#stateIndicator {{ font-size: 8pt; padding: 2px 8px;
    border-radius: 3px; font-weight: 600; }}

QTextEdit#activityLog {{ background: {_SILVER['bg_input']};
    color: {_SILVER['text_primary']}; border: 1px solid {_SILVER['border']};
    font-family: Consolas, monospace; font-size: 8pt; padding: 6px; }}

QPushButton#toolBtn {{ background: {_SILVER['accent_blue']}; color: white;
    border: none; border-radius: 3px; padding: 4px 14px;
    font-size: 8pt; font-weight: 600; }}
QPushButton#toolBtn:hover {{ background: {_SILVER['border_accent']}; }}
QPushButton#toolBtn:disabled {{ background: {_SILVER['border']};
    color: {_SILVER['text_muted']}; }}
QPushButton#stopBtn {{ background: {_SILVER['accent_red']}; color: white;
    border: none; border-radius: 3px; padding: 4px 14px;
    font-size: 8pt; font-weight: 600; }}
QPushButton#stopBtn:hover {{ background: {_SILVER['accent_orange']}; }}
QPushButton#resetBtn {{ background: {_SILVER['text_muted']}; color: white;
    border: none; border-radius: 3px; padding: 4px 12px;
    font-size: 8pt; font-weight: 600; }}
QPushButton#resetBtn:hover {{ background: {_SILVER['text_secondary']}; }}
QPushButton#greenBtn {{ background: {_SILVER['accent_green']}; color: white;
    border: none; border-radius: 3px; padding: 4px 14px;
    font-size: 8pt; font-weight: 600; }}
QPushButton#greenBtn:hover {{ background: {_SILVER['accent_green']}; }}
QPushButton#tealBtn {{ background: {_SILVER['accent_cyan']}; color: white;
    border: none; border-radius: 3px; padding: 4px 14px;
    font-size: 8pt; font-weight: 600; }}
QPushButton#tealBtn:hover {{ background: {_SILVER['accent_blue']}; }}
"""

# Cell state colours -- routed through the canonical palette so the
# WhatIf data table picks the same accents as the rest of the app.
# These are intentionally LIGHT tints so they read on the silver
# background; the named accents stay vivid for borders and text.
_CLR_EDITABLE = QColor("#FFF8E8")       # warm cream -- editable
_CLR_EDITED = QColor("#DBEAFE")         # blue tint -- user changed
_CLR_CONSTRAINED = QColor("#FFF3E0")    # amber -- at limit
_CLR_VIOLATED = QColor("#FFCDD2")       # red -- violated
_CLR_RESULT_CHANGE = QColor("#E8F5E9")  # green tint -- changed in results
_CLR_RESULT_VIOL = QColor("#FFCDD2")


class WhatIfSimulator(QWidget):
    """Standalone What-If Simulator with tables, plots, and step simulation.

    Operates on a SimConfig loaded from YAML. Uses the C++ core bindings
    (_azeoapc_core) for MPC via SimEngine, and a StateSpacePlant for the
    simulated process.
    """

    def __init__(self, config: SimConfig = None, parent=None):
        super().__init__(parent)
        self.cfg = config
        self.engine = None
        title = config.name if config else "No Config"
        self.setWindowTitle(f"What-If Simulator -- {title}")
        self.setMinimumSize(1400, 800)
        self.setWindowFlags(Qt.Window)
        # Apply the named-button + log overrides locally so this widget
        # works whether instantiated standalone or hosted inside the
        # architect MainWindow (which inherits the global theme).
        self.setStyleSheet(_STYLE)

        self._mv_originals = {}   # {(row, col): original_text}
        self._dv_originals = {}
        self._cv_originals = {}
        self._n_edits = 0
        self._steps_per_tick = 1
        self._noise_enabled = False
        self._noise_factor = 1.0

        # History buffers for plots
        self._history_len = config.display.history_length if config else 200
        self._forecast_len = config.optimizer.prediction_horizon if config else 30
        self._cycle = 0

        # Plot widgets
        self._cv_strips = []
        self._mv_strips = []
        self._dv_strips = []

        self._build_ui()
        if config:
            self._init_engine()
            self._populate()
        self._setup_shortcuts()

    # ================================================================ ENGINE
    def _init_engine(self):
        """Create SimEngine from config."""
        if self.cfg is None:
            return
        self.engine = SimEngine(self.cfg)
        self._cycle = 0

        nu = len(self.cfg.mvs)
        ny = len(self.cfg.cvs)
        nd = len(self.cfg.dvs)

        # History arrays for plotting
        self._y_hist = np.full((ny, self._history_len), np.nan)
        self._u_hist = np.full((nu, self._history_len), np.nan)
        self._d_hist = np.full((nd, self._history_len), np.nan)
        self._t_hist = np.arange(-self._history_len, 0, dtype=float)

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
            "QLabel#stateIndicator { background: #B0B0B0; color: #707070; }")
        hdr.addWidget(self._state_lbl)

        self._feasible_lbl = QLabel("")
        self._feasible_lbl.setObjectName("feasible")
        hdr.addWidget(self._feasible_lbl)

        self._edit_summary = QLabel("")
        self._edit_summary.setObjectName("editSummary")
        hdr.addWidget(self._edit_summary)

        hdr.addStretch()
        root.addLayout(hdr)

        # --- Filter bar (matches DMC3 Entry Type / Value Type) ---
        filt = QHBoxLayout()
        filt.setSpacing(16)
        filt.setContentsMargins(6, 2, 6, 2)

        filt.addWidget(QLabel("<b>Entry Type:</b>"))
        self._entry_grp = QButtonGroup(self)
        for i, label in enumerate(["Show All", "Inputs", "Results"]):
            rb = QRadioButton(label)
            rb.setStyleSheet("font-size: 8pt;")
            if i == 0:
                rb.setChecked(True)
            self._entry_grp.addButton(rb, i)
            filt.addWidget(rb)
        self._entry_grp.idToggled.connect(self._on_filter_changed)

        filt.addSpacing(24)

        filt.addWidget(QLabel("<b>Value Type:</b>"))
        self._value_grp = QButtonGroup(self)
        for i, label in enumerate(["Show All", "Operating Values", "Tuning Values"]):
            rb = QRadioButton(label)
            rb.setStyleSheet("font-size: 8pt;")
            if i == 0:
                rb.setChecked(True)
            self._value_grp.addButton(rb, i)
            filt.addWidget(rb)
        self._value_grp.idToggled.connect(self._on_filter_changed)

        filt.addStretch()
        root.addLayout(filt)

        # --- Main body: horizontal splitter ---
        self._main_split = QSplitter(Qt.Horizontal)

        # ---- LEFT: tables ----
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        table_split = QSplitter(Qt.Vertical)
        table_split.setHandleWidth(4)
        table_split.setStyleSheet(
            "QSplitter::handle { background: #B0B8C8; }"
            "QSplitter::handle:hover { background: #909090; }")

        # Inputs section (MVs + DVs in one table, DVs at bottom)
        inp_panel = QWidget()
        inp_lay = QVBoxLayout(inp_panel)
        inp_lay.setContentsMargins(0, 0, 0, 0)
        inp_lay.setSpacing(0)
        inp_hdr = QLabel("  Inputs (MVs + DVs)")
        inp_hdr.setFixedHeight(20)
        inp_hdr.setStyleSheet(
            "font-size: 8pt; font-weight: 600; color: #1A1A1A; "
            "background: #DDE2EC; border-bottom: 1px solid #B0B0B0;")
        inp_lay.addWidget(inp_hdr)
        self.mv_table = self._make_table(editable=True)
        inp_lay.addWidget(self.mv_table, 1)
        table_split.addWidget(inp_panel)

        # CV section
        cv_panel = QWidget()
        cv_lay = QVBoxLayout(cv_panel)
        cv_lay.setContentsMargins(0, 0, 0, 0)
        cv_lay.setSpacing(0)
        cv_hdr = QLabel("  Dependents (CVs)")
        cv_hdr.setFixedHeight(20)
        cv_hdr.setStyleSheet(
            "font-size: 8pt; font-weight: 600; color: #1A1A1A; "
            "background: #DDE2EC; border-bottom: 1px solid #B0B0B0;")
        cv_lay.addWidget(cv_hdr)
        self.cv_table = self._make_table(editable=True)
        cv_lay.addWidget(self.cv_table, 1)
        table_split.addWidget(cv_panel)

        table_split.setSizes([350, 450])
        left_lay.addWidget(table_split, 1)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        sim_btn = QPushButton("Simulate (Ctrl+Enter)")
        sim_btn.setObjectName("toolBtn")
        sim_btn.clicked.connect(self._on_simulate)
        btn_row.addWidget(sim_btn)

        reset_btn = QPushButton("Reset Values")
        reset_btn.setObjectName("resetBtn")
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)

        btn_row.addStretch()
        left_lay.addLayout(btn_row)

        self._main_split.addWidget(left)

        # ---- RIGHT: Prediction plots (pyqtgraph) ----
        self._plot_container = QWidget()
        self._plot_layout = QVBoxLayout(self._plot_container)
        self._plot_layout.setContentsMargins(0, 0, 0, 0)
        self._plot_layout.setSpacing(0)

        # Wrap in scroll area for many variables
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._plot_container)
        scroll.setStyleSheet("QScrollArea { border: none; background: white; }")

        self._main_split.addWidget(scroll)
        self._main_split.setSizes([550, 550])

        root.addWidget(self._main_split, 1)

        # --- Step simulation toolbar ---
        step_bar = QFrame()
        step_bar.setFixedHeight(38)
        step_bar.setStyleSheet(
            "QFrame { background: #D8D8D8; border-top: 1px solid #ECECEC; }")
        sl = QHBoxLayout(step_bar)
        sl.setContentsMargins(8, 3, 8, 3)
        sl.setSpacing(6)

        sl.addWidget(QLabel(
            "<span style='color:#404040;font-size:8pt;'>Step Sim:</span>"))

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
        sl.addWidget(QLabel(
            "<span style='color:#404040;font-size:8pt;'>Steps:</span>"))
        self._step_count_spin = QSpinBox()
        self._step_count_spin.setRange(1, 500)
        self._step_count_spin.setValue(30)
        self._step_count_spin.setStyleSheet(
            "QSpinBox { font-size: 8pt; max-width: 60px; color: white; "
            "background: #E4E4E4; border: 1px solid #4A5570; }")
        self._step_count_spin.setToolTip("Number of steps for batch run")
        sl.addWidget(self._step_count_spin)

        # Speed
        sl.addWidget(QLabel(
            "<span style='color:#404040;font-size:8pt;'>Speed:</span>"))
        self._speed_combo = QComboBox()
        self._speed_combo.setStyleSheet(
            "QComboBox { font-size: 8pt; max-width: 120px; color: white; "
            "background: #E4E4E4; border: 1px solid #4A5570; }")
        self._speed_options = [
            ("1x Real", 1), ("10x", 10), ("60x (1min/s)", 60),
            ("120x", 120), ("300x", 300), ("MAX", -1),
        ]
        for label, _ in self._speed_options:
            self._speed_combo.addItem(label)
        self._speed_combo.setCurrentIndex(2)  # 60x default
        sl.addWidget(self._speed_combo)

        # Noise enable + factor
        from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox
        self._noise_chk = QCheckBox("Noise")
        self._noise_chk.setChecked(False)
        self._noise_chk.setStyleSheet(
            "QCheckBox { color: #404040; font-size: 8pt; spacing: 4px; }"
            "QCheckBox::indicator { width: 13px; height: 13px; }")
        self._noise_chk.setToolTip(
            "Enable measurement noise injection on all CVs.\n"
            "Noise std dev = base CV noise * factor.")
        self._noise_chk.toggled.connect(self._on_noise_toggled)
        sl.addWidget(self._noise_chk)

        self._noise_spin = QDoubleSpinBox()
        self._noise_spin.setRange(0.0, 100.0)
        self._noise_spin.setSingleStep(0.1)
        self._noise_spin.setDecimals(2)
        self._noise_spin.setValue(1.0)
        self._noise_spin.setStyleSheet(
            "QDoubleSpinBox { font-size: 8pt; max-width: 65px; color: white; "
            "background: #E4E4E4; border: 1px solid #4A5570; }")
        self._noise_spin.setToolTip("Noise multiplier (0 = off, 1 = base, 2 = 2x base)")
        self._noise_spin.valueChanged.connect(self._on_noise_factor_changed)
        sl.addWidget(self._noise_spin)

        # Step info
        self._step_info = QLabel("")
        self._step_info.setStyleSheet(
            "color: #81C784; font-size: 8pt; font-weight: 600;")
        sl.addWidget(self._step_info)
        sl.addStretch()

        root.addWidget(step_bar)

        # --- Activity log (collapsible) ---
        log_bar = QHBoxLayout()
        log_bar.setContentsMargins(4, 2, 4, 0)
        log_toggle = QPushButton("\u25bc Activity Log")
        log_toggle.setStyleSheet(
            "QPushButton { background: none; border: none; color: #707070; "
            "font-size: 8pt; font-weight: 600; text-align: left; padding: 0; }"
            "QPushButton:hover { color: #0066CC; }")
        log_toggle.clicked.connect(self._toggle_log)
        log_bar.addWidget(log_toggle)
        log_bar.addStretch()
        log_clear = QPushButton("Clear")
        log_clear.setStyleSheet(
            "QPushButton { background: none; border: none; color: #8899AA; "
            "font-size: 7pt; } QPushButton:hover { color: #0066CC; }")
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
    def _on_noise_toggled(self, checked):
        self._noise_enabled = checked
        if self.engine:
            self.engine.set_noise(checked, self._noise_factor)
        self._log_event(
            f"Measurement noise: {'ON' if checked else 'OFF'} (factor={self._noise_factor:.2f})",
            "info")

    def _on_noise_factor_changed(self, val):
        self._noise_factor = val
        if self.engine:
            self.engine.set_noise(self._noise_enabled, val)

    def _on_filter_changed(self, btn_id, checked):
        """Show/hide columns based on Entry Type and Value Type radio filters."""
        if not checked or not self.cfg:
            return
        entry = self._entry_grp.checkedId()    # 0=All, 1=Inputs, 2=Results
        value = self._value_grp.checkedId()    # 0=All, 1=Operating, 2=Tuning

        # MV columns
        for col in range(len(MV_COLS)):
            _, _, grp = MV_COLS[col]
            show = True
            if entry == 2:  # Results only
                show = col in _MV_RESULT_COLS
            if value == 1:  # Operating only
                show = show and col in _MV_OPER_COLS
            elif value == 2:  # Tuning only
                show = show and col in _MV_TUNING_COLS
            self.mv_table.setColumnHidden(col, not show)

        # CV columns
        for col in range(len(CV_COLS)):
            _, _, grp = CV_COLS[col]
            show = True
            if entry == 2:
                show = col in _CV_RESULT_COLS
            if value == 1:
                show = show and col in _CV_OPER_COLS
            elif value == 2:
                show = show and col in _CV_TUNING_COLS
            self.cv_table.setColumnHidden(col, not show)

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
        t.setMouseTracking(True)
        if not editable:
            t.setEditTriggers(QTableWidget.NoEditTriggers)
        # Right-click on header: column visibility
        t.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        t.horizontalHeader().customContextMenuRequested.connect(
            lambda pos, table=t: self._show_column_menu(table, pos))
        return t

    def _show_column_menu(self, table, pos):
        """Right-click on header to show/hide columns."""
        menu = QMenu(self)
        for col in range(table.columnCount()):
            hdr_item = table.horizontalHeaderItem(col)
            name = hdr_item.text() if hdr_item else f"Col {col}"
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(not table.isColumnHidden(col))
            act.toggled.connect(
                lambda checked, c=col: table.setColumnHidden(c, not checked))
        menu.exec(table.horizontalHeader().mapToGlobal(pos))

    # ================================================================ POPULATE
    def _install_mv_opt_combo(self, row: int, mv):
        """Place a QComboBox in the Opt Type column for an MV row."""
        combo = QComboBox()
        combo.addItems(MV_OPT_TYPES)
        combo.setCurrentText(mv.opt_type)
        combo.setStyleSheet(
            "QComboBox { font-size: 8pt; padding: 1px 4px; "
            "background: #FFF8E8; border: 1px solid #B0B0B0; }")
        combo.currentTextChanged.connect(
            lambda txt, r=row: self._on_mv_opt_changed(r, txt))
        self.mv_table.setCellWidget(row, _MV_OPT_TYPE, combo)

    def _install_cv_opt_combo(self, row: int, cv):
        """Place a QComboBox in the Opt Type column for a CV row."""
        combo = QComboBox()
        combo.addItems(CV_OPT_TYPES)
        combo.setCurrentText(cv.opt_type)
        combo.setStyleSheet(
            "QComboBox { font-size: 8pt; padding: 1px 4px; "
            "background: #FFF8E8; border: 1px solid #B0B0B0; }")
        combo.currentTextChanged.connect(
            lambda txt, r=row: self._on_cv_opt_changed(r, txt))
        self.cv_table.setCellWidget(row, _CV_OPT_TYPE, combo)

    def _on_mv_opt_changed(self, row: int, opt_type: str):
        """Handle change of MV Opt Type combo box."""
        if row >= self._n_mv_rows:
            return  # DV row, no opt type
        mv = self.cfg.mvs[row]
        mv.opt_type = opt_type
        if self.engine:
            self.engine.apply_opt_type()
        self._log_event(f"{mv.tag} opt type → {opt_type}", "info")

    def _on_cv_opt_changed(self, row: int, opt_type: str):
        """Handle change of CV Opt Type combo box."""
        cv = self.cfg.cvs[row]
        cv.opt_type = opt_type
        if self.engine:
            self.engine.apply_opt_type()
        self._log_event(f"{cv.tag} opt type → {opt_type}", "info")

    def _fmt(self, v, lo=-1e19, hi=1e19, fmt=".3f"):
        """Format a limit value, returning '' if out of range."""
        if v <= lo or v >= hi:
            return ""
        return f"{v:{fmt}}"

    def _populate(self):
        if self.cfg is None:
            return

        self._mv_originals.clear()
        self._dv_originals.clear()
        self._cv_originals.clear()
        self._n_edits = 0
        self._edit_summary.setText("")

        F = self._fmt

        # Track which rows are MVs vs DVs
        self._n_mv_rows = len(self.cfg.mvs)
        self._n_dv_rows = len(self.cfg.dvs)
        total_inputs = self._n_mv_rows + self._n_dv_rows

        # --- Inputs table (MVs + DVs, 46 columns, matches DMC3) ---
        headers = [h for h, _, _ in MV_COLS]
        self.mv_table.setColumnCount(len(headers))
        self.mv_table.setHorizontalHeaderLabels(headers)
        self.mv_table.setRowCount(total_inputs)

        for r, mv in enumerate(self.cfg.mvs):
            row = [
                mv.tag,                                          # 0  Inputs (tag)
                mv.name,                                         # 1  Description
                mv.units,                                        # 2  Units
                "",                                              # 3  Subcontroller
                "Normal",                                        # 4  Combined Status
                "On",                                            # 5  Service Request
                "On",                                            # 6  Service Status
                f"{mv.value:.2f}",                               # 7  Measurement
                # Limits: Val Lo | Eng Lo | OP Lo | SS | OP Hi | Eng Hi | Val Hi
                F(mv.limits.validity_lo),                        # 8  Validity Lo
                F(mv.limits.engineering_lo),                      # 9  Eng Lo
                f"{mv.limits.operating_lo:.3f}",                 # 10 Operator Lo
                f"{mv.steady_state:.2f}",                        # 11 SS Value
                f"{mv.limits.operating_hi:.3f}",                 # 12 Operator Hi
                F(mv.limits.engineering_hi),                      # 13 Eng Hi
                F(mv.limits.validity_hi),                        # 14 Validity Hi
                # SS results
                "",                                              # 15 Ideal SS
                "",                                              # 16 Ideal Constraint
                "",                                              # 17 Current Move
                # Tuning
                f"{mv.move_suppress:.4f}",                       # 18 Move Suppression
                "0",                                             # 19 Move Supp Incr
                f"{mv.rate_limit:.3f}",                          # 20 Max Move
                "0",                                             # 21 Move Resolution
                "0",                                             # 22 Move Accumulation
                "0",                                             # 23 Target Suppression
                "No",                                            # 24 MinMove Criterion
                "No",                                            # 25 Dyn Min Movement
                # Economics
                f"{mv.cost:.4f}",                                # 26 LP Cost
                "",                                              # 27 Shadow Price
                f"{mv.cost_rank}",                               # 28 Cost Rank
                "",                                              # 29 Active Constraint
                # Control
                "No",                                            # 30 Reverse Acting
                "Free",                                          # 31 Anti Windup
                "On",                                            # 32 Loop Status
                f"{mv.steady_state:.2f}",                        # 33 Setpoint
                "No",                                            # 34 Is FeedForward
                "No",                                            # 35 Use Limit Track
                "Shed Controller",                               # 36 Shed Option
                # Plot
                F(mv.plot_lo, fmt=".1f"),                        # 37 Plot Lo
                F(mv.plot_hi, fmt=".1f"),                        # 38 Plot Hi
                "No",                                            # 39 Plot Auto Scale
                # Results
                "",                                              # 40 Predicted
                "",                                              # 41 Delta
                "",                                              # 42 Last Move
                f"{mv.steady_state:.2f}",                        # 43 Transformed Tgt
                f"{mv.value:.2f}",                               # 44 Transformed Meas
                "Normal",                                        # 45 Status
                mv.opt_type,                                     # 46 Opt Type
            ]
            for col in range(len(MV_COLS)):
                txt = str(row[col]) if col < len(row) else ""
                _, is_edit, _ = MV_COLS[col]
                it = QTableWidgetItem(txt)
                if not is_edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(_CLR_EDITABLE)
                    self._mv_originals[(r, col)] = txt
                if col not in _MV_TEXT_COLS:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.mv_table.setItem(r, col, it)

            # Replace Opt Type cell with a QComboBox
            self._install_mv_opt_combo(r, mv)

        # Append DV rows at the bottom of the Inputs table (same as DMC3)
        for r_dv, dv in enumerate(self.cfg.dvs):
            r = self._n_mv_rows + r_dv  # row index in combined table
            # DV row uses same 46-col layout; most cols blank
            row = [""] * len(MV_COLS)
            row[0]  = dv.tag                                     # Inputs
            row[1]  = dv.name                                    # Description
            row[2]  = dv.units                                   # Units
            row[4]  = "Normal"                                   # Combined Status
            row[5]  = "On"                                       # Service Request
            row[6]  = "On"                                       # Service Status
            row[7]  = f"{dv.value:.2f}"                          # Measurement
            # Limits: Val Lo | Eng Lo | OP Lo | SS | OP Hi | Eng Hi | Val Hi
            row[8]  = F(dv.limits.validity_lo)                   # Val Lo
            row[9]  = F(dv.limits.engineering_lo)                 # Eng Lo
            row[11] = f"{dv.steady_state:.2f}"                   # SS Value
            row[13] = F(dv.limits.engineering_hi)                 # Eng Hi
            row[14] = F(dv.limits.validity_hi)                   # Val Hi
            row[37] = F(dv.plot_lo, fmt=".1f")                   # Plot Lo
            row[38] = F(dv.plot_hi, fmt=".1f")                   # Plot Hi
            row[44] = f"{dv.value:.2f}"                          # Transformed Meas
            row[45] = "Normal"                                   # Status
            # Pad to full column count
            while len(row) < len(MV_COLS):
                row.append("")

            for col in range(len(MV_COLS)):
                txt = str(row[col]) if col < len(row) else ""
                _, is_edit, _ = MV_COLS[col]
                # DVs: only measurement (col 7) is editable for injecting disturbances
                dv_editable = (col == _MV_VALUE)
                it = QTableWidgetItem(txt)
                if dv_editable:
                    it.setBackground(_CLR_EDITABLE)
                    self._mv_originals[(r, col)] = txt
                else:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if col not in _MV_TEXT_COLS:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                # Gray background for DV rows to distinguish from MVs
                if not dv_editable:
                    it.setBackground(QColor("#F0F0F0"))
                self.mv_table.setItem(r, col, it)

        for col in range(len(MV_COLS)):
            self.mv_table.setColumnHidden(col, col not in _MV_DEFAULT_VISIBLE)
        self.mv_table.resizeColumnsToContents()

        # --- CV table (47 columns, matches DMC3 Outputs) ---
        cv_headers = [h for h, _, _ in CV_COLS]
        self.cv_table.setColumnCount(len(cv_headers))
        self.cv_table.setHorizontalHeaderLabels(cv_headers)
        self.cv_table.setRowCount(len(self.cfg.cvs))

        for r, cv in enumerate(self.cfg.cvs):
            row = [
                cv.tag,                                          # 0  Outputs (tag)
                cv.name,                                         # 1  Description
                cv.units,                                        # 2  Units
                "",                                              # 3  Subcontroller
                "Normal",                                        # 4  Combined Status
                "On",                                            # 5  Service Request
                "On",                                            # 6  Service Status
                f"{cv.value:.3f}",                               # 7  Measurement
                # Limits: Val Lo | Eng Lo | OP Lo | SS | OP Hi | Eng Hi | Val Hi
                F(cv.limits.validity_lo),                        # 8  Validity Lo
                F(cv.limits.engineering_lo),                      # 9  Eng Lo
                f"{cv.limits.operating_lo:.3f}",                 # 10 Operator Lo
                f"{cv.steady_state:.3f}",                        # 11 SS Value
                f"{cv.limits.operating_hi:.3f}",                 # 12 Operator Hi
                F(cv.limits.engineering_hi),                      # 13 Eng Hi
                F(cv.limits.validity_hi),                        # 14 Validity Hi
                # SS results
                "",                                              # 15 Ideal SS
                "",                                              # 16 Ideal Constraint
                f"{cv.rank_lo}",                                 # 17 SS Lo Rank
                f"{cv.concern_hi:.2f}",                          # 18 SS Hi Concern
                f"{cv.rank_hi}",                                 # 19 SS Hi Rank
                "1000",                                          # 20 Cost Rank
                f"{cv.cv_cost:.3f}",                             # 21 LP Cost
                f"{cv.weight:.4f}",                              # 22 Control Weight
                "0",                                             # 23 Max SS Step
                f"{cv.concern_lo:.2f}",                          # 24 Dyn Lo Concern
                f"{cv.concern_hi:.2f}",                          # 25 Dyn Hi Concern
                f"{cv.weight:.4f}",                              # 26 Dyn Tgt Concern
                "0",                                             # 27 Dyn Lo Zone
                "0",                                             # 28 Dyn Hi Zone
                "No",                                            # 29 Ramp
                f"{cv.setpoint:.3f}",                            # 30 Ramp SP
                "0",                                             # 31 Ramp Rate
                "0",                                             # 32 Ramp Horizon
                "0",                                             # 33 Rotation Factor
                "0",                                             # 34 Max Imbalance
                f"{cv.noise:.4f}",                               # 35 Simulation Noise
                "",                                              # 36 Pred Error (result)
                F(cv.plot_lo, fmt=".1f"),                         # 37 Plot Lo
                F(cv.plot_hi, fmt=".1f"),                         # 38 Plot Hi
                "No",                                            # 39 Plot Auto Scale
                "",                                              # 40 Prediction (result)
                "",                                              # 41 Delta (result)
                "",                                              # 42 Violation (result)
                "",                                              # 43 Model Prediction (result)
                "",                                              # 44 Pred Next Cycle (result)
                "Normal",                                        # 45 Status
                "No",                                            # 46 Critical
                cv.opt_type,                                     # 47 Opt Type
            ]
            for col in range(len(CV_COLS)):
                txt = str(row[col]) if col < len(row) else ""
                _, is_edit, _ = CV_COLS[col]
                it = QTableWidgetItem(txt)
                if not is_edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(_CLR_EDITABLE)
                    self._cv_originals[(r, col)] = txt
                if col not in _CV_TEXT_COLS:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.cv_table.setItem(r, col, it)

            # Replace Opt Type cell with a QComboBox
            self._install_cv_opt_combo(r, cv)

        for col in range(len(CV_COLS)):
            self.cv_table.setColumnHidden(col, col not in _CV_DEFAULT_VISIBLE)
        self.cv_table.resizeColumnsToContents()

        # Connect cell change for edit highlighting
        try:
            self.mv_table.cellChanged.disconnect()
            self.cv_table.cellChanged.disconnect()
        except RuntimeError:
            pass
        self.mv_table.cellChanged.connect(self._on_mv_cell_changed)
        self.cv_table.cellChanged.connect(self._on_cv_cell_changed)

        # Build plots
        self._build_plots()

        dt = self.cfg.sample_time
        self._step_info.setText(
            f"Step 0 | Cycle {dt:.0f}s | Ready")
        self._log_event("Ready", "info")
        if not _HAS_CORE:
            self._log_event(
                "C++ core not available -- running open-loop only", "warn")

    # ================================================================ PLOTS
    def _build_plots(self):
        """Create pyqtgraph strip charts for CVs and MVs."""
        # Clear old
        for strip in self._cv_strips + self._mv_strips + self._dv_strips:
            strip["pw"].setParent(None)
            strip["pw"].deleteLater()
        self._cv_strips.clear()
        self._mv_strips.clear()
        self._dv_strips.clear()

        if self.cfg is None:
            return

        H = self._history_len
        F = self._forecast_len
        t_hist = np.arange(-H, 0, dtype=float)
        t_fc = np.arange(0, F + 1, dtype=float)

        # CV strips
        dt = self.cfg.sample_time
        for i, cv in enumerate(self.cfg.cvs):
            time_axis = TimeAxisItem(sample_time_min=dt, orientation="bottom")
            pw = pg.PlotWidget(axisItems={"bottom": time_axis})
            pw.setBackground("w")
            pw.setYRange(cv.plot_lo, cv.plot_hi, padding=0.02)
            pw.setXRange(-H, max(F, 1), padding=0)
            pw.showGrid(x=True, y=True, alpha=0.2)
            pw.setMouseEnabled(x=False, y=False)
            pw.hideButtons()
            pw.setMinimumHeight(250)
            pw.setMaximumHeight(300)

            ax_left = pw.getAxis("left")
            ax_left.setWidth(60)
            ax_left.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 8))
            ax_left.setLabel(cv.tag, units=cv.units,
                             **{"font-size": "8pt", "color": "#333"})

            ax_bot = pw.getAxis("bottom")
            ax_bot.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 7),
                           tickLength=-4)
            ax_bot.setHeight(20)

            pw.setTitle(cv.name, size="9pt", color="#1A1A1A")

            # Limit lines
            lp = pg.mkPen(COLORS["trend_hi"], width=1, style=Qt.DashLine)
            hi_line = lo_line = None
            if cv.limits.operating_hi < 1e19:
                hi_line = pw.addLine(y=cv.limits.operating_hi, pen=lp)
            if cv.limits.operating_lo > -1e19:
                lo_line = pw.addLine(y=cv.limits.operating_lo, pen=lp)

            # Setpoint
            sp_line = pw.addLine(
                y=cv.setpoint,
                pen=pg.mkPen(COLORS["trend_sp"], width=1.5, style=Qt.DashLine))

            # Now line
            pw.addLine(x=0, pen=pg.mkPen("#CC0000", width=1.5))

            # History curve
            data = np.full(H, np.nan)
            hist_curve = pw.plot(t_hist, data,
                                pen=pg.mkPen(COLORS["trend_pv"], width=1.5))

            # Forecast curve
            fc_data = np.full(F + 1, np.nan)
            fc_curve = pw.plot(t_fc, fc_data,
                               pen=pg.mkPen(COLORS["trend_pred"], width=1.5))

            # Current value indicator (top-right of plot)
            value_text = pg.TextItem(
                text=f"{cv.value:.3f} {cv.units}",
                color=(26, 39, 68),
                anchor=(1, 0))
            value_text.setFont(pg.QtGui.QFont("Consolas", 11, pg.QtGui.QFont.Bold))
            pw.addItem(value_text)
            value_text.setPos(max(F, 1), cv.plot_hi)

            # Setpoint marker (top-left)
            sp_text = pg.TextItem(
                text=f"SP: {cv.setpoint:.3f}",
                color=(15, 123, 15),
                anchor=(0, 0))
            sp_text.setFont(pg.QtGui.QFont("Consolas", 8))
            pw.addItem(sp_text)
            sp_text.setPos(-H, cv.plot_hi)

            self._plot_layout.addWidget(pw)
            self._cv_strips.append({
                "pw": pw, "hist_curve": hist_curve, "fc_curve": fc_curve,
                "sp_line": sp_line, "hi_line": hi_line, "lo_line": lo_line,
                "data": data, "t_hist": t_hist, "t_fc": t_fc,
                "fc_data": fc_data,
                "value_text": value_text, "sp_text": sp_text,
                "units": cv.units,
            })

        # MV strips
        for i, mv in enumerate(self.cfg.mvs):
            time_axis = TimeAxisItem(sample_time_min=dt, orientation="bottom")
            pw = pg.PlotWidget(axisItems={"bottom": time_axis})
            pw.setBackground("w")
            pw.setYRange(mv.plot_lo, mv.plot_hi, padding=0.02)
            pw.setXRange(-H, max(F, 1), padding=0)
            pw.showGrid(x=True, y=True, alpha=0.2)
            pw.setMouseEnabled(x=False, y=False)
            pw.hideButtons()
            pw.setMinimumHeight(250)
            pw.setMaximumHeight(300)

            ax_left = pw.getAxis("left")
            ax_left.setWidth(60)
            ax_left.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 8))
            ax_left.setLabel(mv.tag, units=mv.units,
                             **{"font-size": "8pt", "color": "#333"})

            ax_bot = pw.getAxis("bottom")
            ax_bot.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 7),
                           tickLength=-4)
            ax_bot.setHeight(20)

            pw.setTitle(mv.name, size="9pt", color="#1A1A1A")

            # Limit lines
            lp = pg.mkPen(COLORS["trend_hi"], width=1, style=Qt.DashLine)
            if mv.limits.operating_hi < 1e19:
                pw.addLine(y=mv.limits.operating_hi, pen=lp)
            if mv.limits.operating_lo > -1e19:
                pw.addLine(y=mv.limits.operating_lo, pen=lp)

            # Now line
            pw.addLine(x=0, pen=pg.mkPen("#CC0000", width=1.5))

            # History curve (blue for MV)
            data = np.full(H, np.nan)
            hist_curve = pw.plot(t_hist, data,
                                pen=pg.mkPen(COLORS["accent"], width=1.5))

            # Current value indicator
            value_text = pg.TextItem(
                text=f"{mv.value:.3f} {mv.units}",
                color=(0, 85, 170),
                anchor=(1, 0))
            value_text.setFont(pg.QtGui.QFont("Consolas", 11, pg.QtGui.QFont.Bold))
            pw.addItem(value_text)
            value_text.setPos(max(F, 1), mv.plot_hi)

            self._plot_layout.addWidget(pw)
            self._mv_strips.append({
                "pw": pw, "hist_curve": hist_curve,
                "data": data, "t_hist": t_hist,
                "value_text": value_text,
                "units": mv.units,
            })

        # DV strips (orange, no forecast)
        for i, dv in enumerate(self.cfg.dvs):
            time_axis = TimeAxisItem(sample_time_min=dt, orientation="bottom")
            pw = pg.PlotWidget(axisItems={"bottom": time_axis})
            pw.setBackground("w")
            pw.setYRange(dv.plot_lo, dv.plot_hi, padding=0.02)
            pw.setXRange(-H, max(F, 1), padding=0)
            pw.showGrid(x=True, y=True, alpha=0.2)
            pw.setMouseEnabled(x=False, y=False)
            pw.hideButtons()
            pw.setMinimumHeight(250)
            pw.setMaximumHeight(300)

            ax_left = pw.getAxis("left")
            ax_left.setWidth(60)
            ax_left.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 8))
            ax_left.setLabel(dv.tag, units=dv.units,
                             **{"font-size": "8pt", "color": "#333"})

            ax_bot = pw.getAxis("bottom")
            ax_bot.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 7),
                           tickLength=-4)
            ax_bot.setHeight(20)

            pw.setTitle(f"dv - {dv.name}", size="9pt", color="#996600")

            # Now line
            pw.addLine(x=0, pen=pg.mkPen("#CC0000", width=1.5))

            # History curve (orange for DV)
            data = np.full(H, np.nan)
            hist_curve = pw.plot(t_hist, data,
                                pen=pg.mkPen("#CC7700", width=1.5))

            # Current value indicator
            value_text = pg.TextItem(
                text=f"{dv.value:.3f} {dv.units}",
                color=(204, 119, 0),
                anchor=(1, 0))
            value_text.setFont(pg.QtGui.QFont("Consolas", 11, pg.QtGui.QFont.Bold))
            pw.addItem(value_text)
            value_text.setPos(max(F, 1), dv.plot_hi)

            self._plot_layout.addWidget(pw)
            self._dv_strips.append({
                "pw": pw, "hist_curve": hist_curve,
                "data": data, "t_hist": t_hist,
                "value_text": value_text,
                "units": dv.units,
            })

        # Spacer at end
        self._plot_layout.addStretch()

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
            # If this is a DV row and the Value column changed, apply immediately
            if row >= self._n_mv_rows and col == _MV_VALUE and self.engine:
                dv_idx = row - self._n_mv_rows
                try:
                    self.engine.set_dv_value(dv_idx, float(current))
                except (ValueError, IndexError):
                    pass
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

    # ================================================================ GATHER
    def _apply_table_to_config(self):
        """Read editable cells back into the config and rebuild engine."""
        if self.cfg is None:
            return

        for r, mv in enumerate(self.cfg.mvs):
            try:
                mv.move_suppress = float(
                    self.mv_table.item(r, _MV_MOVESUPP).text())
            except (ValueError, AttributeError):
                pass
            try:
                mv.rate_limit = float(
                    self.mv_table.item(r, _MV_MAXMOVE).text())
            except (ValueError, AttributeError):
                pass
            try:
                mv.cost = float(
                    self.mv_table.item(r, _MV_COST).text())
            except (ValueError, AttributeError):
                pass
            try:
                mv.limits.operating_lo = float(
                    self.mv_table.item(r, _MV_LO).text())
            except (ValueError, AttributeError):
                pass
            try:
                mv.limits.operating_hi = float(
                    self.mv_table.item(r, _MV_HI).text())
            except (ValueError, AttributeError):
                pass

        for r, cv in enumerate(self.cfg.cvs):
            try:
                cv.setpoint = float(
                    self.cv_table.item(r, _CV_SP).text())
            except (ValueError, AttributeError):
                pass
            try:
                cv.weight = float(
                    self.cv_table.item(r, _CV_WEIGHT).text())
            except (ValueError, AttributeError):
                pass
            try:
                cv.limits.operating_lo = float(
                    self.cv_table.item(r, _CV_LO).text())
            except (ValueError, AttributeError):
                pass
            try:
                cv.limits.operating_hi = float(
                    self.cv_table.item(r, _CV_HI).text())
            except (ValueError, AttributeError):
                pass
            try:
                cv.noise = float(
                    self.cv_table.item(r, _CV_NOISE).text())
            except (ValueError, AttributeError):
                pass
            # DMC3 concerns and ranks
            try:
                cv.rank_lo = int(float(
                    self.cv_table.item(r, _CV_SSLORANK).text()))
            except (ValueError, AttributeError):
                pass
            try:
                cv.rank_hi = int(float(
                    self.cv_table.item(r, _CV_SSHIRANK).text()))
            except (ValueError, AttributeError):
                pass
            try:
                cv.concern_hi = float(
                    self.cv_table.item(r, _CV_SSHICONCERN).text())
            except (ValueError, AttributeError):
                pass
            try:
                cv.concern_lo = float(
                    self.cv_table.item(r, _CV_DYNLOCONCERN).text())
            except (ValueError, AttributeError):
                pass

        # MV cost ranks
        for r, mv in enumerate(self.cfg.mvs):
            try:
                mv.cost_rank = int(float(
                    self.mv_table.item(r, _MV_RANK).text()))
            except (ValueError, AttributeError):
                pass

        # Rebuild engine with updated config
        self._init_engine()

    # ================================================================ STATE
    def _set_state(self, state):
        styles = {
            "IDLE": "background: #B0B0B0; color: #707070;",
            "SIMULATING": "background: #FFF3E0; color: #E65100;",
            "RUNNING": "background: #E8F5E9; color: #2E8B57;",
            "STOPPED": "background: #B0B0B0; color: #707070;",
        }
        self._state_lbl.setText(f"  {state}  ")
        self._state_lbl.setStyleSheet(
            f"QLabel#stateIndicator {{ {styles.get(state, styles['IDLE'])} }}")

    # ================================================================ SIMULATE
    def _on_simulate(self):
        """Run one MPC cycle: step engine, update tables and plots."""
        if self.engine is None or self.cfg is None:
            self._feasible_lbl.setText("  No config loaded  ")
            self._feasible_lbl.setStyleSheet(
                "QLabel#feasible { background: #FFEBEE; color: #C0392B; }")
            return

        self._set_state("SIMULATING")
        self._apply_table_to_config()

        try:
            y, u, d, du = self.engine.step()
            ok = self.engine.last_ok

            # Update table results
            self._update_result_columns(y, u, du, ok)

            # Update plots
            self._push_to_plots(y, u, d)

            # Update feasibility
            if ok:
                self._feasible_lbl.setText("  FEASIBLE  ")
                self._feasible_lbl.setStyleSheet(
                    "QLabel#feasible { background: #E8F5E9; color: #2E8B57; }")
            else:
                self._feasible_lbl.setText("  INFEASIBLE  ")
                self._feasible_lbl.setStyleSheet(
                    "QLabel#feasible { background: #FFEBEE; color: #C0392B; }")

            self._cycle += 1
            total_ms = self.engine.last_total_ms
            self._log_event(
                f"Simulate: cycle={self._cycle} ok={ok} "
                f"solve={total_ms:.1f}ms",
                "ok" if ok else "error")
        except Exception as e:
            self._feasible_lbl.setText(f"  Error  ")
            self._log_event(f"Simulate error: {e}", "error")
            import traceback
            traceback.print_exc()

        self._set_state("IDLE")

    def _update_result_columns(self, y, u, du, ok):
        """Update Predicted/Delta/Violation columns in tables."""
        # MV results
        for r, mv in enumerate(self.cfg.mvs):
            pred_val = u[r]
            delta = u[r] - mv.steady_state
            pred_txt = f"{pred_val:.3f}"
            delta_txt = f"{delta:+.4f}" if abs(delta) > 1e-6 else ""
            status = "OK"
            at_limit = (abs(u[r] - mv.limits.operating_lo) < 1e-4 or
                        abs(u[r] - mv.limits.operating_hi) < 1e-4)
            if at_limit:
                status = "AT LIMIT"

            for col, txt in [(_MV_PRED, pred_txt), (_MV_DELTA, delta_txt),
                             (_MV_STATUS, status)]:
                item = self.mv_table.item(r, col)
                if item:
                    item.setText(txt)
                    if at_limit:
                        item.setBackground(_CLR_CONSTRAINED)
                    elif abs(delta) > 1e-4:
                        item.setBackground(_CLR_RESULT_CHANGE)
                    else:
                        item.setBackground(QColor("white"))

            # Also update the Value column
            val_item = self.mv_table.item(r, _MV_VALUE)
            if val_item:
                val_item.setText(f"{u[r]:.2f}")

        # CV results
        for r, cv in enumerate(self.cfg.cvs):
            pred_val = y[r]
            delta = y[r] - cv.steady_state
            lo = cv.limits.operating_lo
            hi = cv.limits.operating_hi
            pred_txt = f"{pred_val:.3f}"
            delta_txt = f"{delta:+.4f}" if abs(delta) > 1e-4 else ""
            viol_txt = ""
            is_viol = False
            if pred_val > hi + 1e-4:
                viol_txt = f"+{pred_val - hi:.3f}"
                is_viol = True
            elif pred_val < lo - 1e-4:
                viol_txt = f"{pred_val - lo:.3f}"
                is_viol = True

            status = "VIOLATED" if is_viol else "OK"

            for col, txt in [(_CV_PRED, pred_txt), (_CV_DELTA, delta_txt),
                             (_CV_VIOL, viol_txt), (_CV_STATUS, status)]:
                item = self.cv_table.item(r, col)
                if item:
                    item.setText(txt)
                    if is_viol:
                        item.setBackground(_CLR_RESULT_VIOL)
                    elif abs(delta) > 1e-4:
                        item.setBackground(_CLR_RESULT_CHANGE)
                    else:
                        item.setBackground(QColor("white"))

            # Also update the Value column
            val_item = self.cv_table.item(r, _CV_VALUE)
            if val_item:
                val_item.setText(f"{y[r]:.3f}")

    # ================================================================ PLOT UPDATE
    def _push_to_plots(self, y, u, d_vals=None):
        """Push new y, u, d values to strip charts and update value labels."""
        # CV strips
        for i, strip in enumerate(self._cv_strips):
            if i < len(y):
                buf = strip["data"]
                buf[:-1] = buf[1:]
                buf[-1] = y[i]
                strip["hist_curve"].setData(strip["t_hist"], buf)

                # Update current value label
                strip["value_text"].setText(f"{y[i]:.3f} {strip['units']}")
                # Update setpoint label
                cv = self.cfg.cvs[i]
                strip["sp_text"].setText(f"SP: {cv.setpoint:.3f}")
                strip["sp_line"].setValue(cv.setpoint)

                # Update forecast if we have prediction data
                if (self.engine and self.engine.last_y_predicted is not None
                        and len(self.engine.last_y_predicted) > 0):
                    P = self._forecast_len
                    ny = len(self.cfg.cvs)
                    pred_full = self.engine.last_y_predicted
                    y0 = self.cfg.cvs[i].steady_state
                    fc = np.full(P + 1, np.nan)
                    fc[0] = y[i]
                    if len(pred_full) >= ny:
                        cv_pred = []
                        for k in range(P):
                            idx = k * ny + i
                            if idx < len(pred_full):
                                cv_pred.append(pred_full[idx] + y0)
                        n = min(len(cv_pred), P)
                        fc[1:n + 1] = cv_pred[:n]
                    strip["fc_curve"].setData(strip["t_fc"], fc)

        # MV strips
        for i, strip in enumerate(self._mv_strips):
            if i < len(u):
                buf = strip["data"]
                buf[:-1] = buf[1:]
                buf[-1] = u[i]
                strip["hist_curve"].setData(strip["t_hist"], buf)
                strip["value_text"].setText(f"{u[i]:.3f} {strip['units']}")

        # DV strips
        if d_vals is not None:
            for i, strip in enumerate(self._dv_strips):
                if i < len(d_vals):
                    buf = strip["data"]
                    buf[:-1] = buf[1:]
                    buf[-1] = d_vals[i]
                    strip["hist_curve"].setData(strip["t_hist"], buf)
                    strip["value_text"].setText(f"{d_vals[i]:.3f} {strip['units']}")

    # ================================================================ STEP SIM
    def _on_step_one(self):
        if self.engine is None:
            if self.cfg:
                self._apply_table_to_config()
            else:
                return
        if self.engine is None:
            return

        y, u, d, du = self.engine.step()
        self._cycle += 1
        self._update_result_columns(y, u, du, self.engine.last_ok)
        self._push_to_plots(y, u, d)
        self._update_step_info()

    def _on_run(self):
        if self.engine is None:
            if self.cfg:
                self._apply_table_to_config()
            else:
                return

        idx = self._speed_combo.currentIndex()
        _, mult = self._speed_options[idx]
        cycle_ms = self.cfg.sample_time * 1000 if self.cfg else 60000

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
        if self.engine is None:
            self._on_stop()
            return
        for _ in range(self._steps_per_tick):
            y, u, d, du = self.engine.step()
            self._cycle += 1
        self._update_result_columns(y, u, du, self.engine.last_ok)
        self._push_to_plots(y, u, d)
        self._update_step_info()

    def _on_stop(self):
        self._run_timer.stop()
        self._run_btn.setEnabled(True)
        self._step_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._set_state("IDLE")
        self._log_event("Run stopped", "info")

    def _on_reset_sim(self):
        self._on_stop()
        if self.engine:
            self.engine.reset()
        self._cycle = 0

        # Clear plot data
        for strip in self._cv_strips:
            strip["data"][:] = np.nan
            strip["hist_curve"].setData(strip["t_hist"], strip["data"])
            strip["fc_data"][:] = np.nan
            strip["fc_curve"].setData(strip["t_fc"], strip["fc_data"])
        for strip in self._mv_strips:
            strip["data"][:] = np.nan
            strip["hist_curve"].setData(strip["t_hist"], strip["data"])

        # Also reset Y/U history
        if self.cfg:
            ny = len(self.cfg.cvs)
            nu = len(self.cfg.mvs)
            self._y_hist = np.full((ny, self._history_len), np.nan)
            self._u_hist = np.full((nu, self._history_len), np.nan)

        # Reset table result columns
        for r in range(self.mv_table.rowCount()):
            for col in [_MV_PRED, _MV_DELTA, _MV_STATUS]:
                item = self.mv_table.item(r, col)
                if item:
                    item.setText("" if col != _MV_STATUS else "OK")
                    item.setBackground(QColor("white"))
            val_item = self.mv_table.item(r, _MV_VALUE)
            if val_item and r < len(self.cfg.mvs):
                val_item.setText(f"{self.cfg.mvs[r].steady_state:.2f}")

        for r in range(self.cv_table.rowCount()):
            for col in [_CV_PRED, _CV_DELTA, _CV_VIOL, _CV_STATUS]:
                item = self.cv_table.item(r, col)
                if item:
                    item.setText("" if col != _CV_STATUS else "OK")
                    item.setBackground(QColor("white"))
            val_item = self.cv_table.item(r, _CV_VALUE)
            if val_item and r < len(self.cfg.cvs):
                val_item.setText(f"{self.cfg.cvs[r].steady_state:.3f}")

        self._step_info.setText(
            f"Step 0 | Cycle {self.cfg.sample_time:.0f}s | Ready"
            if self.cfg else "")
        self._log_event("Simulation reset", "info")

    def _on_reset(self):
        """Reset all table values to originals from config."""
        self._on_stop()
        if self.engine:
            self.engine.reset()
        self._cycle = 0

        # Disconnect to avoid triggering cell change events during repopulate
        try:
            self.mv_table.cellChanged.disconnect()
            self.cv_table.cellChanged.disconnect()
        except RuntimeError:
            pass

        # Reload config values
        if self.cfg:
            self._init_engine()
            self._populate()
        self._log_event("Values reset to original config", "info")

    def _update_step_info(self):
        t_min = self._cycle * (self.cfg.sample_time if self.cfg else 1.0)
        ok = self.engine.last_ok if self.engine else True
        color = "#81C784" if ok else "#E57373"
        total_ms = self.engine.last_total_ms if self.engine else 0
        self._step_info.setText(
            f"Step {self._cycle} | T={t_min:.1f}min | "
            f"solve={total_ms:.1f}ms")
        self._step_info.setStyleSheet(
            f"color: {color}; font-size: 8pt; font-weight: 600;")

    # ================================================================ ACTIVITY LOG
    def _log_event(self, msg, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        colors = {
            "info": "#404040", "ok": "#81C784",
            "warn": "#FFB74D", "error": "#E57373",
        }
        color = colors.get(level, "#404040")
        self._log.append(
            f'<span style="color:#707070;">{ts}</span> '
            f'<span style="color:{color};">{msg}</span>')
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
