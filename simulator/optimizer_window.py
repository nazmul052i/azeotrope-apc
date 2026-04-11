"""DMC3-style three-layer optimizer configuration tab.

Provides three sub-tabs:
  - Layer 3 (NLP): re-linearization, IPOPT settings (deferred wiring)
  - Layer 2 (LP):  Smart Tune wizard for steady-state economic optimization
  - Layer 1 (QP):  Per-CV/MV tuning, concerns, weights, horizons
"""
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QFrame,
    QGroupBox, QGridLayout, QListWidget, QStackedWidget,
    QListWidgetItem, QSplitter, QMessageBox, QSlider,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from .models.config_loader import SimConfig
from .models.variables import MV_OPT_TYPES, CV_OPT_TYPES


# ============================================================================
# Color constants
# ============================================================================
_CLR_EDITABLE = QColor("#FFF8E8")
_CLR_HEADER_BG = "#E2E6EE"
_CLR_PRIMARY = "#1A2744"
_CLR_ACCENT = "#3B5998"


# ============================================================================
# Layer 1 (QP) Tuning Page
# ============================================================================
class Layer1TuningPage(QWidget):
    """Per-variable Q/R weights, concerns, and horizon settings."""

    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build_ui()
        self._populate()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Horizons section ──
        horiz_grp = QGroupBox("Horizons")
        horiz_grp.setStyleSheet(self._group_style())
        h_lay = QGridLayout(horiz_grp)
        h_lay.setContentsMargins(10, 16, 10, 10)
        h_lay.setSpacing(8)

        h_lay.addWidget(QLabel("Prediction Horizon (P):"), 0, 0)
        self.p_spin = QSpinBox()
        self.p_spin.setRange(1, 500)
        self.p_spin.setSuffix(" steps")
        self.p_spin.setMinimumWidth(100)
        self.p_spin.valueChanged.connect(self.changed)
        h_lay.addWidget(self.p_spin, 0, 1)

        h_lay.addWidget(QLabel("Control Horizon (M):"), 0, 2)
        self.m_spin = QSpinBox()
        self.m_spin.setRange(1, 100)
        self.m_spin.setSuffix(" steps")
        self.m_spin.setMinimumWidth(100)
        self.m_spin.valueChanged.connect(self.changed)
        h_lay.addWidget(self.m_spin, 0, 3)

        h_lay.addWidget(QLabel("Model Horizon (N):"), 0, 4)
        self.n_spin = QSpinBox()
        self.n_spin.setRange(10, 1000)
        self.n_spin.setSuffix(" steps")
        self.n_spin.setMinimumWidth(100)
        self.n_spin.valueChanged.connect(self.changed)
        h_lay.addWidget(self.n_spin, 0, 5)

        h_lay.setColumnStretch(6, 1)
        root.addWidget(horiz_grp)

        # ── CV tuning table ──
        cv_grp = QGroupBox("CV Tuning  (Q weight, soft concerns)")
        cv_grp.setStyleSheet(self._group_style())
        cv_lay = QVBoxLayout(cv_grp)
        cv_lay.setContentsMargins(8, 16, 8, 8)
        cv_lay.setSpacing(4)

        self.cv_table = QTableWidget()
        self.cv_table.setStyleSheet(self._table_style())
        self.cv_table.setColumnCount(7)
        self.cv_table.setHorizontalHeaderLabels([
            "Tag", "Description", "Q Weight",
            "Concern Lo", "Concern Hi", "Noise (std)", "Status"
        ])
        self.cv_table.verticalHeader().setVisible(False)
        self.cv_table.setAlternatingRowColors(True)
        self.cv_table.cellChanged.connect(self._on_cv_cell)
        cv_lay.addWidget(self.cv_table)

        cv_hint = QLabel(
            "<i>Concern values control soft constraint stiffness. "
            "Higher concern → tighter (closer to hard) constraint. "
            "Penalty cost = concern² per unit slack.</i>")
        cv_hint.setStyleSheet("color: #6B7394; font-size: 8pt;")
        cv_lay.addWidget(cv_hint)

        root.addWidget(cv_grp, 1)

        # ── MV tuning table ──
        mv_grp = QGroupBox("MV Tuning  (Move suppression, rate limits)")
        mv_grp.setStyleSheet(self._group_style())
        mv_lay = QVBoxLayout(mv_grp)
        mv_lay.setContentsMargins(8, 16, 8, 8)
        mv_lay.setSpacing(4)

        self.mv_table = QTableWidget()
        self.mv_table.setStyleSheet(self._table_style())
        self.mv_table.setColumnCount(5)
        self.mv_table.setHorizontalHeaderLabels([
            "Tag", "Description", "Move Suppress (R)", "Max Move", "Status"
        ])
        self.mv_table.verticalHeader().setVisible(False)
        self.mv_table.setAlternatingRowColors(True)
        self.mv_table.cellChanged.connect(self._on_mv_cell)
        mv_lay.addWidget(self.mv_table)

        mv_hint = QLabel(
            "<i>Move suppression (R) penalizes large moves. "
            "Higher R → smoother control, slower response. "
            "Auto-tune sets R = 1/(rate_limit²).</i>")
        mv_hint.setStyleSheet("color: #6B7394; font-size: 8pt;")
        mv_lay.addWidget(mv_hint)

        root.addWidget(mv_grp, 1)

        # ── Auto-tune button row ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        auto_btn = QPushButton("⚡ Auto-Tune (Smart Defaults)")
        auto_btn.setStyleSheet(self._button_style("#00897B"))
        auto_btn.clicked.connect(self._auto_tune)
        btn_row.addWidget(auto_btn)

        reset_btn = QPushButton("Reset to Loaded Values")
        reset_btn.setStyleSheet(self._button_style("#6B7394"))
        reset_btn.clicked.connect(self._populate)
        btn_row.addWidget(reset_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

    def _group_style(self):
        return """
        QGroupBox {
            font-weight: bold; font-size: 9pt; color: #1A2744;
            border: 1px solid #C0C8D8; border-radius: 4px;
            margin-top: 10px; padding-top: 6px;
            background: #FAFBFD;
        }
        QGroupBox::title {
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 0 6px; background: #FAFBFD;
        }
        """

    def _table_style(self):
        return """
        QTableWidget { background: white; alternate-background-color: #F6F7FA;
            border: 1px solid #D0D4DC; gridline-color: #E8EAF0;
            selection-background-color: #3B5998; selection-color: white;
            font-size: 9pt; }
        QHeaderView::section { background: #E2E6EE; border: none;
            border-right: 1px solid #D0D4DC; border-bottom: 1px solid #D0D4DC;
            padding: 4px 6px; font-weight: 600; font-size: 8pt; color: #2D3748; }
        """

    def _button_style(self, color):
        return f"""
        QPushButton {{ background: {color}; color: white; border: none;
            border-radius: 3px; padding: 6px 16px; font-size: 9pt; font-weight: 600; }}
        QPushButton:hover {{ background: #4A6BB5; }}
        """

    def _populate(self):
        cfg = self.cfg
        self.p_spin.blockSignals(True)
        self.m_spin.blockSignals(True)
        self.n_spin.blockSignals(True)
        self.p_spin.setValue(cfg.optimizer.prediction_horizon)
        self.m_spin.setValue(cfg.optimizer.control_horizon)
        self.n_spin.setValue(cfg.optimizer.model_horizon)
        self.p_spin.blockSignals(False)
        self.m_spin.blockSignals(False)
        self.n_spin.blockSignals(False)

        # CV table
        self.cv_table.blockSignals(True)
        self.cv_table.setRowCount(len(cfg.cvs))
        for r, cv in enumerate(cfg.cvs):
            items = [
                (cv.tag, False),
                (cv.name, False),
                (f"{cv.weight:.4f}", True),
                (f"{cv.concern_lo:.2f}", True),
                (f"{cv.concern_hi:.2f}", True),
                (f"{cv.noise:.4f}", True),
                ("OK", False),
            ]
            for c, (txt, edit) in enumerate(items):
                it = QTableWidgetItem(txt)
                if not edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(_CLR_EDITABLE)
                if c >= 2 and c <= 5:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.cv_table.setItem(r, c, it)
        self.cv_table.resizeColumnsToContents()
        self.cv_table.horizontalHeader().setStretchLastSection(True)
        self.cv_table.blockSignals(False)

        # MV table
        self.mv_table.blockSignals(True)
        self.mv_table.setRowCount(len(cfg.mvs))
        for r, mv in enumerate(cfg.mvs):
            items = [
                (mv.tag, False),
                (mv.name, False),
                (f"{mv.move_suppress:.4f}", True),
                (f"{mv.rate_limit:.3f}", True),
                ("OK", False),
            ]
            for c, (txt, edit) in enumerate(items):
                it = QTableWidgetItem(txt)
                if not edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(_CLR_EDITABLE)
                if c == 2 or c == 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.mv_table.setItem(r, c, it)
        self.mv_table.resizeColumnsToContents()
        self.mv_table.horizontalHeader().setStretchLastSection(True)
        self.mv_table.blockSignals(False)

    def _on_cv_cell(self, row, col):
        if row >= len(self.cfg.cvs):
            return
        cv = self.cfg.cvs[row]
        item = self.cv_table.item(row, col)
        if item is None:
            return
        try:
            val = float(item.text())
        except ValueError:
            return
        if col == 2:
            cv.weight = val
        elif col == 3:
            cv.concern_lo = val
        elif col == 4:
            cv.concern_hi = val
        elif col == 5:
            cv.noise = val
        self.changed.emit()

    def _on_mv_cell(self, row, col):
        if row >= len(self.cfg.mvs):
            return
        mv = self.cfg.mvs[row]
        item = self.mv_table.item(row, col)
        if item is None:
            return
        try:
            val = float(item.text())
        except ValueError:
            return
        if col == 2:
            mv.move_suppress = val
        elif col == 3:
            mv.rate_limit = val
        self.changed.emit()

    def _auto_tune(self):
        """Compute reasonable defaults from engineering ranges."""
        for cv in self.cfg.cvs:
            rng = cv.limits.engineering_hi - cv.limits.engineering_lo
            if rng > 0 and rng < 1e18:
                cv.weight = 1.0 / (rng * rng) * 100.0  # normalized weight
                cv.concern_lo = 1.0
                cv.concern_hi = 1.0
        for mv in self.cfg.mvs:
            if mv.rate_limit > 0 and mv.rate_limit < 1e18:
                mv.move_suppress = 0.1 / (mv.rate_limit * mv.rate_limit)
        self._populate()
        self.changed.emit()

    def apply_to_config(self):
        """Push spin box values back into config (called by parent on Apply)."""
        self.cfg.optimizer.prediction_horizon = self.p_spin.value()
        self.cfg.optimizer.control_horizon = self.m_spin.value()
        self.cfg.optimizer.model_horizon = self.n_spin.value()


# ============================================================================
# Layer 2 (LP) Smart Tune Wizard
# ============================================================================
class Layer2SmartTunePage(QWidget):
    """5-step DMC3-style wizard for steady-state economic optimization."""

    changed = Signal()

    STEPS = [
        ("1. Select CV Ranks", "Assign relaxation priority to each CV bound."),
        ("2. Select Preferences", "Choose Maximize / Minimize / Min Movement per variable."),
        ("3. Prioritize MVs",   "Assign cost rank for lexicographic LP tiers."),
        ("4. Evaluate Strategy", "Inspect the gain matrix and verify achievability."),
        ("5. Initialize Tuning", "Apply smart defaults across all variables."),
    ]

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left sidebar: workflow steps ──
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            "QFrame { background: #2C3345; border-right: 1px solid #1A2030; }"
        )
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(0, 8, 0, 8)
        side_lay.setSpacing(0)

        title = QLabel("  Smart Tune Workflow")
        title.setStyleSheet(
            "color: #A8B4C8; font-size: 8pt; font-weight: 600; "
            "padding: 4px 8px; text-transform: uppercase;")
        side_lay.addWidget(title)

        self.step_list = QListWidget()
        self.step_list.setStyleSheet("""
        QListWidget {
            background: #2C3345; border: none; outline: none;
            color: #E8EDF5; font-size: 9pt;
        }
        QListWidget::item {
            padding: 10px 14px; border-bottom: 1px solid #3A4560;
        }
        QListWidget::item:selected {
            background: #3B5998; color: white; font-weight: 600;
            border-left: 3px solid #6BBAFF;
        }
        QListWidget::item:hover {
            background: #3A4560;
        }
        """)
        for label, _ in self.STEPS:
            QListWidgetItem(label, self.step_list)
        self.step_list.setCurrentRow(0)
        self.step_list.currentRowChanged.connect(self._on_step_changed)
        side_lay.addWidget(self.step_list)

        side_lay.addStretch()

        # Help text at bottom of sidebar
        self.help_lbl = QLabel(self.STEPS[0][1])
        self.help_lbl.setWordWrap(True)
        self.help_lbl.setStyleSheet(
            "color: #A8B4C8; font-size: 8pt; padding: 8px 12px; "
            "background: #1F2535; border-top: 1px solid #1A2030;")
        side_lay.addWidget(self.help_lbl)

        root.addWidget(sidebar)

        # ── Right: stacked step content ──
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: #F5F6F8; }")

        self.step1 = Step1_CVRanks(self.cfg)
        self.step2 = Step2_Preferences(self.cfg)
        self.step3 = Step3_PrioritizeMVs(self.cfg)
        self.step4 = Step4_Evaluate(self.cfg)
        self.step5 = Step5_InitTuning(self.cfg)

        for w in (self.step1, self.step2, self.step3, self.step4, self.step5):
            w.changed.connect(self.changed)
            self.stack.addWidget(w)

        root.addWidget(self.stack, 1)

    def _on_step_changed(self, idx):
        self.stack.setCurrentIndex(idx)
        self.help_lbl.setText(self.STEPS[idx][1])

    def refresh(self):
        for w in (self.step1, self.step2, self.step3, self.step4, self.step5):
            if hasattr(w, "refresh"):
                w.refresh()


# ============================================================================
# Step 1: CV Ranks
# ============================================================================
class Step1_CVRanks(QWidget):
    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        header = QLabel("Step 1 — Select CV Ranks")
        header.setStyleSheet(
            "font-size: 13pt; font-weight: 600; color: #1A2744;")
        lay.addWidget(header)

        intro = QLabel(
            "Assign a rank value to each CV's lower and upper bound. "
            "Higher rank = more important = relaxed last when infeasible. "
            "Range: 1 (lowest priority) to 100 (highest)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #6B7394; font-size: 9pt; padding: 4px 0;")
        lay.addWidget(intro)

        self.table = QTableWidget()
        self.table.setStyleSheet("""
        QTableWidget { background: white; alternate-background-color: #F6F7FA;
            border: 1px solid #D0D4DC; gridline-color: #E8EAF0;
            selection-background-color: #3B5998; selection-color: white; font-size: 9pt; }
        QHeaderView::section { background: #E2E6EE; border: none;
            border-right: 1px solid #D0D4DC; border-bottom: 1px solid #D0D4DC;
            padding: 5px 8px; font-weight: 600; font-size: 8pt; color: #2D3748; }
        """)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "CV Tag", "Description", "Op Lo", "Op Hi", "Lo Rank", "Hi Rank"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellChanged.connect(self._on_cell)
        lay.addWidget(self.table, 1)

    def refresh(self):
        cfg = self.cfg
        self.table.blockSignals(True)
        self.table.setRowCount(len(cfg.cvs))
        for r, cv in enumerate(cfg.cvs):
            items = [
                (cv.tag, False),
                (cv.name, False),
                (f"{cv.limits.operating_lo:.3f}", False),
                (f"{cv.limits.operating_hi:.3f}", False),
                (str(cv.rank_lo), True),
                (str(cv.rank_hi), True),
            ]
            for c, (txt, edit) in enumerate(items):
                it = QTableWidgetItem(txt)
                if not edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(_CLR_EDITABLE)
                if c >= 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.blockSignals(False)

    def _on_cell(self, row, col):
        if row >= len(self.cfg.cvs):
            return
        item = self.table.item(row, col)
        if item is None:
            return
        try:
            val = int(float(item.text()))
        except ValueError:
            return
        cv = self.cfg.cvs[row]
        if col == 4:
            cv.rank_lo = val
        elif col == 5:
            cv.rank_hi = val
        self.changed.emit()


# ============================================================================
# Step 2: Select Preferences (placeholder for Phase A)
# ============================================================================
class Step2_Preferences(QWidget):
    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        header = QLabel("Step 2 — Select Preferences")
        header.setStyleSheet("font-size: 13pt; font-weight: 600; color: #1A2744;")
        lay.addWidget(header)

        intro = QLabel(
            "Choose an optimization preference for each MV and CV. "
            "<b>Maximize</b> drives toward upper limit; "
            "<b>Minimize</b> drives toward lower limit; "
            "<b>Min Movement</b> prefers no change; "
            "<b>None</b> leaves the variable free."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #6B7394; font-size: 9pt; padding: 4px 0;")
        lay.addWidget(intro)

        # Two side-by-side tables: MVs and CVs
        split = QHBoxLayout()
        split.setSpacing(12)

        # MV preferences
        mv_box = QGroupBox("Manipulated Variables")
        mv_box.setStyleSheet("""
        QGroupBox { font-weight: bold; font-size: 9pt; color: #1A2744;
            border: 1px solid #C0C8D8; border-radius: 4px;
            margin-top: 10px; padding-top: 6px; background: #FAFBFD; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
            padding: 0 6px; background: #FAFBFD; }
        """)
        mv_lay = QVBoxLayout(mv_box)
        mv_lay.setContentsMargins(8, 16, 8, 8)
        self.mv_table = self._make_pref_table(MV_OPT_TYPES)
        mv_lay.addWidget(self.mv_table)
        split.addWidget(mv_box, 1)

        cv_box = QGroupBox("Controlled Variables")
        cv_box.setStyleSheet(mv_box.styleSheet())
        cv_lay = QVBoxLayout(cv_box)
        cv_lay.setContentsMargins(8, 16, 8, 8)
        self.cv_table = self._make_pref_table(CV_OPT_TYPES)
        cv_lay.addWidget(self.cv_table)
        split.addWidget(cv_box, 1)

        lay.addLayout(split, 1)

    def _make_pref_table(self, opt_types):
        t = QTableWidget()
        t.setStyleSheet("""
        QTableWidget { background: white; alternate-background-color: #F6F7FA;
            border: 1px solid #D0D4DC; gridline-color: #E8EAF0;
            selection-background-color: #3B5998; selection-color: white; font-size: 9pt; }
        QHeaderView::section { background: #E2E6EE; border: none;
            border-right: 1px solid #D0D4DC; border-bottom: 1px solid #D0D4DC;
            padding: 5px 8px; font-weight: 600; font-size: 8pt; color: #2D3748; }
        """)
        t.setColumnCount(3)
        t.setHorizontalHeaderLabels(["Tag", "Description", "Preference"])
        t.verticalHeader().setVisible(False)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setStretchLastSection(True)
        return t

    def refresh(self):
        # MVs
        self.mv_table.setRowCount(len(self.cfg.mvs))
        for r, mv in enumerate(self.cfg.mvs):
            it_tag = QTableWidgetItem(mv.tag)
            it_tag.setFlags(it_tag.flags() & ~Qt.ItemIsEditable)
            self.mv_table.setItem(r, 0, it_tag)

            it_desc = QTableWidgetItem(mv.name)
            it_desc.setFlags(it_desc.flags() & ~Qt.ItemIsEditable)
            self.mv_table.setItem(r, 1, it_desc)

            combo = QComboBox()
            combo.addItems(MV_OPT_TYPES)
            combo.setCurrentText(mv.opt_type)
            combo.setStyleSheet(
                "QComboBox { background: #FFF8E8; padding: 2px 6px; "
                "border: 1px solid #C0C8D8; }")
            combo.currentTextChanged.connect(
                lambda txt, idx=r: self._on_mv_pref(idx, txt))
            self.mv_table.setCellWidget(r, 2, combo)
        self.mv_table.resizeColumnsToContents()
        self.mv_table.horizontalHeader().setStretchLastSection(True)

        # CVs
        self.cv_table.setRowCount(len(self.cfg.cvs))
        for r, cv in enumerate(self.cfg.cvs):
            it_tag = QTableWidgetItem(cv.tag)
            it_tag.setFlags(it_tag.flags() & ~Qt.ItemIsEditable)
            self.cv_table.setItem(r, 0, it_tag)

            it_desc = QTableWidgetItem(cv.name)
            it_desc.setFlags(it_desc.flags() & ~Qt.ItemIsEditable)
            self.cv_table.setItem(r, 1, it_desc)

            combo = QComboBox()
            combo.addItems(CV_OPT_TYPES)
            combo.setCurrentText(cv.opt_type)
            combo.setStyleSheet(
                "QComboBox { background: #FFF8E8; padding: 2px 6px; "
                "border: 1px solid #C0C8D8; }")
            combo.currentTextChanged.connect(
                lambda txt, idx=r: self._on_cv_pref(idx, txt))
            self.cv_table.setCellWidget(r, 2, combo)
        self.cv_table.resizeColumnsToContents()
        self.cv_table.horizontalHeader().setStretchLastSection(True)

    def _on_mv_pref(self, idx, txt):
        self.cfg.mvs[idx].opt_type = txt
        self.changed.emit()

    def _on_cv_pref(self, idx, txt):
        self.cfg.cvs[idx].opt_type = txt
        self.changed.emit()


# ============================================================================
# Step 3: Prioritize MVs (cost ranks)
# ============================================================================
class Step3_PrioritizeMVs(QWidget):
    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        header = QLabel("Step 3 — Prioritize MVs (Lexicographic LP Ranks)")
        header.setStyleSheet("font-size: 13pt; font-weight: 600; color: #1A2744;")
        lay.addWidget(header)

        intro = QLabel(
            "Assign a cost rank to each MV. The Layer 2 LP solves "
            "<b>highest rank first</b> -- those MVs hit their economic targets, "
            "then lower-rank MVs are optimized within what remains. "
            "Rank 0 means \"no priority\" (solved last)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #6B7394; font-size: 9pt; padding: 4px 0;")
        lay.addWidget(intro)

        self.table = QTableWidget()
        self.table.setStyleSheet("""
        QTableWidget { background: white; alternate-background-color: #F6F7FA;
            border: 1px solid #D0D4DC; gridline-color: #E8EAF0;
            selection-background-color: #3B5998; selection-color: white; font-size: 9pt; }
        QHeaderView::section { background: #E2E6EE; border: none;
            border-right: 1px solid #D0D4DC; border-bottom: 1px solid #D0D4DC;
            padding: 5px 8px; font-weight: 600; font-size: 8pt; color: #2D3748; }
        """)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "MV Tag", "Description", "Preference", "LP Cost", "Cost Rank"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellChanged.connect(self._on_cell)
        lay.addWidget(self.table, 1)

    def refresh(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.cfg.mvs))
        for r, mv in enumerate(self.cfg.mvs):
            items = [
                (mv.tag, False),
                (mv.name, False),
                (mv.opt_type, False),
                (f"{mv.cost:.4f}", True),
                (str(mv.cost_rank), True),
            ]
            for c, (txt, edit) in enumerate(items):
                it = QTableWidgetItem(txt)
                if not edit:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                else:
                    it.setBackground(_CLR_EDITABLE)
                if c >= 3:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.blockSignals(False)

    def _on_cell(self, row, col):
        if row >= len(self.cfg.mvs):
            return
        item = self.table.item(row, col)
        if item is None:
            return
        try:
            val = float(item.text())
        except ValueError:
            return
        mv = self.cfg.mvs[row]
        if col == 3:
            mv.cost = val
        elif col == 4:
            mv.cost_rank = int(val)
        self.changed.emit()


# ============================================================================
# Step 4: Evaluate Strategy (gain matrix viewer)
# ============================================================================
class Step4_Evaluate(QWidget):
    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()
        self.refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        header = QLabel("Step 4 — Evaluate Strategy (Gain Matrix)")
        header.setStyleSheet("font-size: 13pt; font-weight: 600; color: #1A2744;")
        lay.addWidget(header)

        intro = QLabel(
            "The plant gain matrix G[i,j] = ∂CV[i]/∂MV[j] at steady state. "
            "Cells colored <span style='color:#2E7D32'>green</span> show positive gain, "
            "<span style='color:#C62828'>red</span> show negative gain. "
            "Magnitude indicates sensitivity. "
            "Use this to verify your preferences are achievable."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #6B7394; font-size: 9pt; padding: 4px 0;")
        lay.addWidget(intro)

        self.table = QTableWidget()
        self.table.setStyleSheet("""
        QTableWidget { background: white; border: 1px solid #D0D4DC;
            gridline-color: #E8EAF0; font-size: 9pt; font-family: Consolas, monospace; }
        QHeaderView::section { background: #E2E6EE; border: none;
            border-right: 1px solid #D0D4DC; border-bottom: 1px solid #D0D4DC;
            padding: 5px 8px; font-weight: 600; font-size: 8pt; color: #2D3748; }
        """)
        self.table.verticalHeader().setStyleSheet(
            "QHeaderView::section { background: #E2E6EE; padding: 4px 8px; "
            "font-weight: 600; }")
        lay.addWidget(self.table, 1)

        refresh_btn = QPushButton("⟳ Recompute Gain Matrix")
        refresh_btn.setStyleSheet(
            "QPushButton { background: #3B5998; color: white; border: none; "
            "border-radius: 3px; padding: 6px 16px; font-size: 9pt; font-weight: 600; }"
            "QPushButton:hover { background: #4A6BB5; }")
        refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(refresh_btn, 0, Qt.AlignLeft)

    def refresh(self):
        cfg = self.cfg
        if cfg is None or cfg.plant is None:
            return

        ny = len(cfg.cvs)
        nu = len(cfg.mvs)

        # Steady-state gain G = -C * inv(A - I) * Bu (for SS plant)
        plant = cfg.plant
        try:
            if hasattr(plant, 'A'):
                A = plant.A
                Bu = plant.Bu
                C = plant.C
                I = np.eye(A.shape[0])
                G = -C @ np.linalg.solve(A - I, Bu)
            elif hasattr(plant, 'gains'):
                G = plant.gains
            else:
                G = np.zeros((ny, nu))
        except Exception:
            G = np.zeros((ny, nu))

        self.table.setRowCount(ny)
        self.table.setColumnCount(nu)
        self.table.setHorizontalHeaderLabels([mv.tag for mv in cfg.mvs])
        self.table.setVerticalHeaderLabels([cv.tag for cv in cfg.cvs])

        # Find max abs for normalization
        max_abs = float(np.max(np.abs(G))) if G.size > 0 else 1.0
        if max_abs < 1e-12:
            max_abs = 1.0

        for i in range(ny):
            for j in range(nu):
                val = float(G[i, j])
                it = QTableWidgetItem(f"{val:+.4g}")
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setTextAlignment(Qt.AlignCenter)

                # Color by sign and magnitude
                norm = abs(val) / max_abs
                if val > 1e-9:
                    # Green tint
                    intensity = int(255 - norm * 100)
                    it.setBackground(QColor(intensity, 255, intensity))
                elif val < -1e-9:
                    intensity = int(255 - norm * 100)
                    it.setBackground(QColor(255, intensity, intensity))
                else:
                    it.setBackground(QColor(245, 245, 245))

                self.table.setItem(i, j, it)

        self.table.resizeColumnsToContents()


# ============================================================================
# Step 5: Initialize Tuning (apply smart defaults)
# ============================================================================
class Step5_InitTuning(QWidget):
    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        header = QLabel("Step 5 — Initialize Tuning")
        header.setStyleSheet("font-size: 13pt; font-weight: 600; color: #1A2744;")
        lay.addWidget(header)

        intro = QLabel(
            "Apply smart defaults across all variables. This computes Q/R weights "
            "from engineering ranges and assigns reasonable concerns and ranks. "
            "You can fine-tune individual values afterward in the Layer 1 (QP) tab."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #6B7394; font-size: 9pt; padding: 4px 0;")
        lay.addWidget(intro)

        # Form: default values
        form = QGroupBox("Default Values")
        form.setStyleSheet("""
        QGroupBox { font-weight: bold; font-size: 9pt; color: #1A2744;
            border: 1px solid #C0C8D8; border-radius: 4px;
            margin-top: 10px; padding-top: 6px; background: #FAFBFD; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
            padding: 0 6px; background: #FAFBFD; }
        """)
        f_lay = QGridLayout(form)
        f_lay.setContentsMargins(12, 18, 12, 12)
        f_lay.setSpacing(10)

        f_lay.addWidget(QLabel("CV Concern (default):"), 0, 0)
        self.concern_spin = QDoubleSpinBox()
        self.concern_spin.setRange(0.01, 1000.0)
        self.concern_spin.setValue(1.0)
        self.concern_spin.setDecimals(2)
        self.concern_spin.setSingleStep(0.5)
        self.concern_spin.setMinimumWidth(120)
        f_lay.addWidget(self.concern_spin, 0, 1)
        f_lay.addWidget(QLabel("(higher = harder constraint)"), 0, 2)

        f_lay.addWidget(QLabel("CV Rank (default):"), 1, 0)
        self.rank_spin = QSpinBox()
        self.rank_spin.setRange(1, 100)
        self.rank_spin.setValue(20)
        self.rank_spin.setMinimumWidth(120)
        f_lay.addWidget(self.rank_spin, 1, 1)
        f_lay.addWidget(QLabel("(higher = relaxed last)"), 1, 2)

        f_lay.addWidget(QLabel("MV Move Suppression scale:"), 2, 0)
        self.r_scale = QDoubleSpinBox()
        self.r_scale.setRange(0.001, 1000.0)
        self.r_scale.setValue(0.1)
        self.r_scale.setDecimals(4)
        self.r_scale.setSingleStep(0.01)
        self.r_scale.setMinimumWidth(120)
        f_lay.addWidget(self.r_scale, 2, 1)
        f_lay.addWidget(QLabel("(R = scale / rate_limit²)"), 2, 2)

        f_lay.addWidget(QLabel("CV Q-weight scale:"), 3, 0)
        self.q_scale = QDoubleSpinBox()
        self.q_scale.setRange(0.01, 10000.0)
        self.q_scale.setValue(100.0)
        self.q_scale.setDecimals(2)
        self.q_scale.setSingleStep(10.0)
        self.q_scale.setMinimumWidth(120)
        f_lay.addWidget(self.q_scale, 3, 1)
        f_lay.addWidget(QLabel("(Q = scale / range²)"), 3, 2)

        f_lay.setColumnStretch(3, 1)
        lay.addWidget(form)

        apply_btn = QPushButton("⚡ Apply Smart Defaults to All Variables")
        apply_btn.setStyleSheet("""
        QPushButton { background: #00897B; color: white; border: none;
            border-radius: 4px; padding: 10px 20px; font-size: 10pt; font-weight: 600; }
        QPushButton:hover { background: #00ACC1; }
        """)
        apply_btn.clicked.connect(self._apply_smart_defaults)
        lay.addWidget(apply_btn, 0, Qt.AlignLeft)

        lay.addStretch()

    def _apply_smart_defaults(self):
        cv_concern = self.concern_spin.value()
        cv_rank = self.rank_spin.value()
        r_scale = self.r_scale.value()
        q_scale = self.q_scale.value()

        for cv in self.cfg.cvs:
            cv.concern_lo = cv_concern
            cv.concern_hi = cv_concern
            cv.rank_lo = cv_rank
            cv.rank_hi = cv_rank
            rng = cv.limits.engineering_hi - cv.limits.engineering_lo
            if rng > 0 and rng < 1e18:
                cv.weight = q_scale / (rng * rng)

        for mv in self.cfg.mvs:
            if mv.rate_limit > 0 and mv.rate_limit < 1e18:
                mv.move_suppress = r_scale / (mv.rate_limit * mv.rate_limit)

        QMessageBox.information(
            self, "Smart Defaults Applied",
            f"Applied defaults to {len(self.cfg.cvs)} CVs and {len(self.cfg.mvs)} MVs.")
        self.changed.emit()


# ============================================================================
# Layer 3 (NLP) Configuration Page
# ============================================================================
class Layer3ConfigPage(QWidget):
    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        header = QLabel("Layer 3 — Nonlinear Optimizer (CasADi / IPOPT)")
        header.setStyleSheet("font-size: 13pt; font-weight: 600; color: #1A2744;")
        lay.addWidget(header)

        intro = QLabel(
            "Layer 3 performs Real-Time Optimization (RTO) by solving a "
            "nonlinear economic optimization problem with IPOPT. It finds "
            "the optimal steady-state operating point, then re-linearizes "
            "the plant at that point and updates the Layer 2 gain matrix."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #6B7394; font-size: 9pt; padding: 4px 0;")
        lay.addWidget(intro)

        # Master enable
        l3 = getattr(self.cfg, "layer3", None)
        enabled = bool(l3 and l3.enabled)
        self.enable_chk = QCheckBox("Enable Layer 3 RTO")
        self.enable_chk.setChecked(enabled)
        self.enable_chk.setStyleSheet(
            "QCheckBox { font-weight: 600; font-size: 10pt; color: #1A2744; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }")
        self.enable_chk.toggled.connect(self._on_enable)
        lay.addWidget(self.enable_chk)

        # Settings group
        self.settings_grp = QGroupBox("NLP Settings")
        self.settings_grp.setStyleSheet("""
        QGroupBox { font-weight: bold; font-size: 9pt; color: #1A2744;
            border: 1px solid #C0C8D8; border-radius: 4px;
            margin-top: 10px; padding-top: 6px; background: #FAFBFD; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
            padding: 0 6px; background: #FAFBFD; }
        """)
        s_lay = QGridLayout(self.settings_grp)
        s_lay.setContentsMargins(12, 18, 12, 12)
        s_lay.setSpacing(10)

        s_lay.addWidget(QLabel("Execution Interval:"), 0, 0)
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(1.0, 86400.0)
        self.interval_spin.setValue(l3.execution_interval_sec if l3 else 3600.0)
        self.interval_spin.setDecimals(0)
        self.interval_spin.setSuffix(" sec")
        self.interval_spin.setMinimumWidth(140)
        self.interval_spin.valueChanged.connect(self.changed)
        s_lay.addWidget(self.interval_spin, 0, 1)
        s_lay.addWidget(QLabel("(how often to re-linearize)"), 0, 2)

        s_lay.addWidget(QLabel("Max Iterations:"), 1, 0)
        self.max_iter_spin = QSpinBox()
        self.max_iter_spin.setRange(10, 10000)
        self.max_iter_spin.setValue(l3.max_iter if l3 else 500)
        self.max_iter_spin.setMinimumWidth(140)
        self.max_iter_spin.valueChanged.connect(self.changed)
        s_lay.addWidget(self.max_iter_spin, 1, 1)
        s_lay.addWidget(QLabel("(IPOPT iteration limit)"), 1, 2)

        s_lay.addWidget(QLabel("Tolerance:"), 2, 0)
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(1e-12, 1.0)
        self.tol_spin.setValue(l3.tolerance if l3 else 1e-6)
        self.tol_spin.setDecimals(12)
        self.tol_spin.setSingleStep(1e-7)
        self.tol_spin.setMinimumWidth(140)
        self.tol_spin.valueChanged.connect(self.changed)
        s_lay.addWidget(self.tol_spin, 2, 1)
        s_lay.addWidget(QLabel("(NLP convergence)"), 2, 2)

        s_lay.setColumnStretch(3, 1)
        lay.addWidget(self.settings_grp)

        # Manual run button
        run_btn = QPushButton("⚡ Run RTO Now")
        run_btn.setStyleSheet("""
        QPushButton { background: #00897B; color: white; border: none;
            border-radius: 4px; padding: 8px 18px; font-size: 9pt; font-weight: 600; }
        QPushButton:hover { background: #00ACC1; }
        """)
        run_btn.clicked.connect(self._on_run_rto)
        lay.addWidget(run_btn, 0, Qt.AlignLeft)

        # Last RTO result display
        self.result_lbl = QLabel("No RTO solve yet.")
        self.result_lbl.setStyleSheet(
            "QLabel { background: #ECEEF4; border: 1px solid #C0C8D8; "
            "border-radius: 4px; padding: 10px; font-family: Consolas, monospace; "
            "font-size: 9pt; color: #2D3748; }")
        self.result_lbl.setWordWrap(True)
        self.result_lbl.setMinimumHeight(120)
        self.result_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self.result_lbl)

        # Status note
        status_box = QFrame()
        status_box.setStyleSheet(
            "QFrame { background: #FFF8E8; border: 1px solid #D4B86A; "
            "border-radius: 4px; padding: 10px; }")
        sb_lay = QVBoxLayout(status_box)
        try:
            import casadi as ca
            casadi_status = (f"<b>CasADi {ca.__version__}</b> with IPOPT detected. "
                             "Layer 3 RTO is fully functional for nonlinear plants.")
            color = "#1B5E20"
        except ImportError:
            casadi_status = (
                "<b>CasADi not installed.</b> Install via "
                "<code>pip install casadi</code> to enable Layer 3 RTO. "
                "Layer 3 only works with nonlinear plant models.")
            color = "#5D4E00"
        status_lbl = QLabel(casadi_status)
        status_lbl.setWordWrap(True)
        status_lbl.setStyleSheet(
            f"color: {color}; font-size: 9pt; background: transparent;")
        sb_lay.addWidget(status_lbl)
        lay.addWidget(status_box)

        lay.addStretch()
        self._on_enable(enabled)

    def _on_enable(self, on):
        self.settings_grp.setEnabled(on)
        if hasattr(self.cfg, "layer3"):
            self.cfg.layer3.enabled = on
        self.changed.emit()

    def _on_run_rto(self):
        """Trigger Layer 3 RTO immediately. Connected by parent window."""
        # Walk parent chain to find a top-level handler
        w = self.parent()
        while w is not None:
            if hasattr(w, "trigger_rto"):
                w.trigger_rto()
                return
            w = w.parent() if hasattr(w, "parent") else None

        # If no parent handler, show what would happen
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Run RTO",
            "Apply settings first, then switch to the Simulation tab "
            "and click 'Run RTO Now' there.")

    def show_rto_result(self, result):
        """Display the most recent RTO solve result. Called by parent."""
        if result is None:
            self.result_lbl.setText("No RTO solve yet.")
            return
        if not result.success:
            self.result_lbl.setText(
                f"<b style='color:#C62828'>RTO FAILED</b>: {result.message}\n"
                f"Iterations: {result.iterations}\n"
                f"Time: {result.solve_time_ms:.1f} ms")
            return
        u_str = ", ".join(f"{v:.3f}" for v in result.u_ss)
        y_str = ", ".join(f"{v:.3f}" for v in result.y_ss)
        x_str = ", ".join(f"{v:.4f}" for v in result.x_ss)
        self.result_lbl.setText(
            f"<b style='color:#2E7D32'>RTO SUCCESS</b>  ({result.message})\n"
            f"Iter: {result.iterations}    Time: {result.solve_time_ms:.1f} ms    "
            f"Obj: {result.objective:.6g}\n\n"
            f"x_ss = [{x_str}]\n"
            f"u_ss = [{u_str}]\n"
            f"y_ss = [{y_str}]")

    def refresh(self):
        l3 = getattr(self.cfg, "layer3", None)
        if l3 is None:
            return
        self.enable_chk.blockSignals(True)
        self.interval_spin.blockSignals(True)
        self.max_iter_spin.blockSignals(True)
        self.tol_spin.blockSignals(True)
        self.enable_chk.setChecked(l3.enabled)
        self.interval_spin.setValue(l3.execution_interval_sec)
        self.max_iter_spin.setValue(l3.max_iter)
        self.tol_spin.setValue(l3.tolerance)
        self.enable_chk.blockSignals(False)
        self.interval_spin.blockSignals(False)
        self.max_iter_spin.blockSignals(False)
        self.tol_spin.blockSignals(False)
        self.settings_grp.setEnabled(l3.enabled)

    def apply_to_config(self):
        if not hasattr(self.cfg, "layer3"):
            return
        self.cfg.layer3.enabled = self.enable_chk.isChecked()
        self.cfg.layer3.execution_interval_sec = self.interval_spin.value()
        self.cfg.layer3.max_iter = self.max_iter_spin.value()
        self.cfg.layer3.tolerance = self.tol_spin.value()


# ============================================================================
# Main Optimizer Window (combines all three layers)
# ============================================================================
class OptimizerWindow(QWidget):
    """Three-layer optimizer configuration: NLP, LP, QP."""

    config_changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Inner tab widget for the three layers
        self.layer_tabs = QTabWidget()
        self.layer_tabs.setStyleSheet("""
        QTabWidget::pane {
            border: 1px solid #C0C8D8;
            background: #F5F6F8;
        }
        QTabBar::tab {
            background: #DDE2EC;
            border: 1px solid #C0C8D8;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: 8px 24px;
            margin-right: 2px;
            font-size: 10pt;
            color: #2D3748;
            min-width: 140px;
        }
        QTabBar::tab:selected {
            background: #F5F6F8;
            font-weight: 600;
            color: #1A2744;
            border-top: 2px solid #3B5998;
        }
        """)

        self.layer3_page = Layer3ConfigPage(self.cfg)
        self.layer2_page = Layer2SmartTunePage(self.cfg)
        self.layer1_page = Layer1TuningPage(self.cfg)

        self.layer_tabs.addTab(self.layer3_page, "Layer 3  ·  NLP (RTO)")
        self.layer_tabs.addTab(self.layer2_page, "Layer 2  ·  LP (Steady-State)")
        self.layer_tabs.addTab(self.layer1_page, "Layer 1  ·  QP (Dynamic)")
        # Default to Layer 2 (most common)
        self.layer_tabs.setCurrentIndex(1)

        # Wire change signals
        self.layer3_page.changed.connect(self._mark_dirty)
        self.layer2_page.changed.connect(self._mark_dirty)
        self.layer1_page.changed.connect(self._mark_dirty)

        root.addWidget(self.layer_tabs, 1)

        # Bottom action bar
        action_bar = QFrame()
        action_bar.setFixedHeight(48)
        action_bar.setStyleSheet(
            "QFrame { background: #ECEEF4; border-top: 1px solid #C0C8D8; }")
        a_lay = QHBoxLayout(action_bar)
        a_lay.setContentsMargins(12, 6, 12, 6)
        a_lay.setSpacing(8)

        self.dirty_lbl = QLabel("")
        self.dirty_lbl.setStyleSheet(
            "color: #C62828; font-size: 8pt; font-weight: 600;")
        a_lay.addWidget(self.dirty_lbl)

        a_lay.addStretch()

        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(
            "QPushButton { background: #6B7394; color: white; border: none; "
            "border-radius: 3px; padding: 6px 18px; font-size: 9pt; font-weight: 600; }"
            "QPushButton:hover { background: #8899BB; }")
        reset_btn.clicked.connect(self._reset)
        a_lay.addWidget(reset_btn)

        apply_btn = QPushButton("Apply to Simulator")
        apply_btn.setStyleSheet(
            "QPushButton { background: #2E7D32; color: white; border: none; "
            "border-radius: 3px; padding: 6px 18px; font-size: 9pt; font-weight: 600; }"
            "QPushButton:hover { background: #388E3C; }")
        apply_btn.clicked.connect(self._apply)
        a_lay.addWidget(apply_btn)

        root.addWidget(action_bar)

        self._dirty = False

    def _mark_dirty(self):
        self._dirty = True
        self.dirty_lbl.setText("● Unsaved changes")

    def _apply(self):
        self.layer1_page.apply_to_config()
        self.layer3_page.apply_to_config()
        self._dirty = False
        self.dirty_lbl.setText("")
        self.config_changed.emit()

    def _reset(self):
        self.refresh()
        self._dirty = False
        self.dirty_lbl.setText("")

    def refresh(self):
        self.layer1_page._populate()
        self.layer2_page.refresh()
        self.layer3_page.refresh()
