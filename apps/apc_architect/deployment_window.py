"""Deployment tab GUI -- mirrors DMC3's Deployment view.

Layout:
  ┌─ Deployment ─────────────────────────────────────────────────────────┐
  │ Server URL:  [opc.tcp://...]    [Connect] [Test Connections] [Deploy]│
  │ Status: ● CONNECTED / ○ DISCONNECTED       Cycle: 142  | 18.3 ms     │
  ├──────────────────────────────────────────────────────────────────────┤
  │ ┌─ [Online Settings] [IO Tags] [Activity] ─────────────────────────┐ │
  │ │                                                                   │ │
  │ │ ─ Online Settings sub-tab ─                                       │ │
  │ │   General Settings table     (1 row)                              │ │
  │ │   Input Validation Limits    (1 row per CV/DV)                    │ │
  │ │   Output Validation Limits   (1 row per MV)                       │ │
  │ │                                                                   │ │
  │ │ ─ IO Tags sub-tab ─                                               │ │
  │ │   Tag Browser tree   (top)                                        │ │
  │ │   Tag Generator      (middle, one row per variable)               │ │
  │ │   Variable Detail    (bottom, one row per parameter of selected)  │ │
  │ │                                                                   │ │
  │ │ ─ Activity sub-tab ─                                              │ │
  │ │   Live status per variable + log                                  │ │
  │ └───────────────────────────────────────────────────────────────────┘ │
  └──────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QGroupBox,
    QSplitter, QTreeWidget, QTreeWidgetItem, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QMessageBox, QFrame, QPlainTextEdit,
    QSizePolicy,
)

from azeoapc.deployment.tag_model import (
    DeploymentConfig, VariableDeployment, IOTag, GeneralSettings,
    ValidationLimits, VarType, ParamRole,
)
from azeoapc.deployment.tag_templates import (
    TAG_TEMPLATES, generate_io_tags, default_parameters_for,
)
from azeoapc.deployment.opcua_client import OpcUaClient
from azeoapc.deployment.embedded_server import EmbeddedPlantServer
from azeoapc.deployment.runtime import DeploymentRuntime


# ── Styles ────────────────────────────────────────────────────────────────
_BTN_PRIMARY = """
QPushButton {
    background: #0066CC; color: white; border: 1px solid #909090;
    padding: 5px 16px; font-weight: 600; font-size: 9pt;
    border-radius: 2px; min-width: 90px;
}
QPushButton:hover { background: #0066CC; }
QPushButton:disabled { background: #909090; color: #404040; }
"""

_BTN_DANGER = """
QPushButton {
    background: #C0392B; color: white; border: 1px solid #962D21;
    padding: 5px 16px; font-weight: 600; font-size: 9pt;
    border-radius: 2px; min-width: 90px;
}
QPushButton:hover { background: #D04A3B; }
QPushButton:disabled { background: #909090; color: #404040; }
"""

_BTN_NEUTRAL = """
QPushButton {
    background: #D8D8D8; color: white; border: 1px solid #B0B0B0;
    padding: 5px 14px; font-weight: 500; font-size: 9pt;
    border-radius: 2px;
}
QPushButton:hover { background: #909090; }
"""

_TABLE = """
QTableWidget {
    background: white; alternate-background-color: #F4F6FA;
    border: 1px solid #B0B0B0; gridline-color: #E0E4EC;
    selection-background-color: #0066CC; selection-color: white;
    font-size: 9pt;
}
QTableWidget::item { padding: 3px 6px; }
QHeaderView::section {
    background: #D8D8D8; color: #1A1A1A; border: none;
    border-right: 1px solid #ECECEC; padding: 5px 8px;
    font-weight: 600; font-size: 8.5pt;
}
"""

_GROUP = """
QGroupBox {
    background: #F8F9FB; border: 1px solid #B0B0B0;
    border-radius: 3px; margin-top: 10px;
    font-weight: 600; color: #1A1A1A; font-size: 9pt;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
"""


class DeploymentWindow(QWidget):
    """Deployment tab: bind controller to plant via OPC UA."""

    config_changed = Signal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.dep_cfg: DeploymentConfig = self._load_or_default()
        self.client: Optional[OpcUaClient] = None
        self.embedded: Optional[EmbeddedPlantServer] = None
        self.runtime: Optional[DeploymentRuntime] = None
        self._current_var: Optional[VariableDeployment] = None
        self._build()
        self._populate_all()

    # ------------------------------------------------------------------
    def _load_or_default(self) -> DeploymentConfig:
        """Pull deployment config off the engine.cfg if present, else build a
        fresh one with auto-generated tags for every CV/MV/DV."""
        cfg = self.engine.cfg
        existing = getattr(cfg, "deployment", None)
        if existing is not None:
            return existing
        dep = DeploymentConfig()
        for cv in cfg.cvs:
            vd = VariableDeployment(
                variable_tag=cv.tag, var_type=VarType.INPUT)
            vd.io_tags = generate_io_tags(cv.tag, VarType.INPUT)
            vd.validation = ValidationLimits(
                validity_lo=cv.limits.validity_lo,
                validity_hi=cv.limits.validity_hi,
                engineer_lo=cv.limits.engineering_lo,
                engineer_hi=cv.limits.engineering_hi,
                operator_lo=cv.limits.operating_lo,
                operator_hi=cv.limits.operating_hi,
            )
            dep.variables.append(vd)
        for mv in cfg.mvs:
            vd = VariableDeployment(
                variable_tag=mv.tag, var_type=VarType.OUTPUT)
            vd.io_tags = generate_io_tags(mv.tag, VarType.OUTPUT)
            vd.validation = ValidationLimits(
                validity_lo=mv.limits.validity_lo,
                validity_hi=mv.limits.validity_hi,
                engineer_lo=mv.limits.engineering_lo,
                engineer_hi=mv.limits.engineering_hi,
                operator_lo=mv.limits.operating_lo,
                operator_hi=mv.limits.operating_hi,
            )
            dep.variables.append(vd)
        for dv in cfg.dvs:
            vd = VariableDeployment(
                variable_tag=dv.tag, var_type=VarType.DISTURBANCE)
            vd.io_tags = generate_io_tags(dv.tag, VarType.DISTURBANCE)
            vd.validation = ValidationLimits(
                validity_lo=dv.limits.validity_lo,
                validity_hi=dv.limits.validity_hi,
                engineer_lo=dv.limits.engineering_lo,
                engineer_hi=dv.limits.engineering_hi,
            )
            dep.variables.append(vd)
        cfg.deployment = dep
        return dep

    # ==================================================================
    # UI construction
    # ==================================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addLayout(self._build_connection_bar())
        root.addWidget(self._build_status_bar())

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
        QTabWidget::pane { border: 1px solid #B0B0B0; background: #ECECEC; }
        QTabBar::tab { background: #D8D8D8; color: #404040; padding: 6px 22px;
                       font-weight: 600; font-size: 9pt; min-width: 130px; }
        QTabBar::tab:selected { background: #0066CC; color: white;
                                border-bottom: 2px solid #0066CC; }
        """)
        self.tabs.addTab(self._build_online_settings_tab(), "Online Settings")
        self.tabs.addTab(self._build_io_tags_tab(),         "IO Tags")
        self.tabs.addTab(self._build_activity_tab(),        "Activity")
        root.addWidget(self.tabs, 1)

    # ------------------------------------------------------------------
    def _build_connection_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(6)

        bar.addWidget(QLabel("Server URL:"))
        self.url_edit = QLineEdit(self.dep_cfg.server_url)
        self.url_edit.setMinimumWidth(380)
        self.url_edit.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #B0B0B0;"
            " padding: 4px 8px; font-family: Consolas; font-size: 9pt; }")
        self.url_edit.editingFinished.connect(
            lambda: setattr(self.dep_cfg, "server_url", self.url_edit.text()))
        bar.addWidget(self.url_edit, 1)

        self.embedded_chk = QCheckBox("Use embedded server")
        self.embedded_chk.setChecked(True)
        self.embedded_chk.setToolTip(
            "Start an in-process OPC UA server that publishes the simulator's "
            "plant model. Lets you exercise the deploy loop without external "
            "infrastructure.")
        self.embedded_chk.setStyleSheet(
            "QCheckBox { color: #1A1A1A; font-weight: 500; padding: 4px 8px; }")
        bar.addWidget(self.embedded_chk)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet(_BTN_PRIMARY)
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        bar.addWidget(self.connect_btn)

        self.test_btn = QPushButton("Test Connections")
        self.test_btn.setStyleSheet(_BTN_NEUTRAL)
        self.test_btn.clicked.connect(self._on_test_clicked)
        bar.addWidget(self.test_btn)

        self.deploy_btn = QPushButton("Deploy")
        self.deploy_btn.setStyleSheet(_BTN_PRIMARY)
        self.deploy_btn.clicked.connect(self._on_deploy_clicked)
        bar.addWidget(self.deploy_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(_BTN_DANGER)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.stop_btn.setEnabled(False)
        bar.addWidget(self.stop_btn)

        return bar

    # ------------------------------------------------------------------
    def _build_status_bar(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #ECECEC; border: 1px solid #B0B0B0;"
            " border-radius: 2px; }")
        frame.setFixedHeight(32)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(20)

        self.conn_dot = QLabel("●")
        self.conn_dot.setStyleSheet("color: #C0392B; font-size: 14pt;")
        lay.addWidget(self.conn_dot)

        self.conn_label = QLabel("DISCONNECTED")
        self.conn_label.setStyleSheet(
            "color: #1A1A1A; font-weight: 700; font-size: 9pt;"
            " letter-spacing: 1px;")
        lay.addWidget(self.conn_label)

        sep = QLabel("|")
        sep.setStyleSheet("color: #707070;")
        lay.addWidget(sep)

        self.cycle_label = QLabel("Cycle: -")
        self.cycle_label.setStyleSheet("color: #404040; font-size: 9pt;")
        lay.addWidget(self.cycle_label)

        self.cycle_ms_label = QLabel("Cycle Time: -")
        self.cycle_ms_label.setStyleSheet("color: #404040; font-size: 9pt;")
        lay.addWidget(self.cycle_ms_label)

        lay.addStretch()

        self.runtime_status_label = QLabel("Runtime: idle")
        self.runtime_status_label.setStyleSheet(
            "color: #0066CC; font-size: 9pt; font-weight: 500;")
        lay.addWidget(self.runtime_status_label)

        return frame

    # ==================================================================
    # Online Settings sub-tab
    # ==================================================================
    def _build_online_settings_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(8)

        # ── General Settings ──
        gs_box = QGroupBox("General Settings")
        gs_box.setStyleSheet(_GROUP)
        gs_lay = QVBoxLayout(gs_box)
        gs_lay.setContentsMargins(8, 16, 8, 8)
        self.gs_table = QTableWidget(1, 6)
        self.gs_table.setStyleSheet(_TABLE)
        self.gs_table.setHorizontalHeaderLabels([
            "Watchdog (sec)", "Cycle Offset (sec)",
            "Setpoint Extended Validation",
            "Write Failure Limit", "Read Failure Limit",
            "Pad IO Tag Length",
        ])
        self.gs_table.verticalHeader().setVisible(False)
        self.gs_table.setMaximumHeight(60)
        self.gs_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.gs_table.cellChanged.connect(self._on_gs_changed)
        gs_lay.addWidget(self.gs_table)
        lay.addWidget(gs_box)

        # ── Input Validation Limits ──
        in_box = QGroupBox("Input Validation Limits")
        in_box.setStyleSheet(_GROUP)
        in_lay = QVBoxLayout(in_box)
        in_lay.setContentsMargins(8, 16, 8, 8)
        self.in_table = QTableWidget()
        self.in_table.setStyleSheet(_TABLE)
        self.in_table.setColumnCount(8)
        self.in_table.setHorizontalHeaderLabels([
            "Variable Name", "Lower Validity", "Lower Engineer", "Lower Operator",
            "Upper Operator", "Upper Engineer", "Upper Validity", "Timeout (s)",
        ])
        self.in_table.verticalHeader().setVisible(False)
        self.in_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.in_table.cellChanged.connect(
            lambda r, c: self._on_validation_changed(self.in_table, "input", r, c))
        in_lay.addWidget(self.in_table)
        lay.addWidget(in_box, 1)

        # ── Output Validation Limits ──
        out_box = QGroupBox("Output Validation Limits")
        out_box.setStyleSheet(_GROUP)
        out_lay = QVBoxLayout(out_box)
        out_lay.setContentsMargins(8, 16, 8, 8)
        self.out_table = QTableWidget()
        self.out_table.setStyleSheet(_TABLE)
        self.out_table.setColumnCount(8)
        self.out_table.setHorizontalHeaderLabels([
            "Variable Name", "Lower Validity", "Lower Engineer", "Lower Operator",
            "Upper Operator", "Upper Engineer", "Upper Validity", "Timeout (s)",
        ])
        self.out_table.verticalHeader().setVisible(False)
        self.out_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.out_table.cellChanged.connect(
            lambda r, c: self._on_validation_changed(self.out_table, "output", r, c))
        out_lay.addWidget(self.out_table)
        lay.addWidget(out_box, 1)

        return w

    # ==================================================================
    # IO Tags sub-tab
    # ==================================================================
    def _build_io_tags_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # ── Generator ribbon ──
        ribbon = QHBoxLayout()
        ribbon.setSpacing(6)
        ribbon.addWidget(QLabel("Tag Template:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems(sorted(TAG_TEMPLATES.keys()))
        self.template_combo.setCurrentText(self.dep_cfg.default_template)
        ribbon.addWidget(self.template_combo)
        ribbon.addSpacing(20)
        ribbon.addWidget(QLabel("Default IO Source:"))
        self.io_src_edit = QLineEdit(self.dep_cfg.default_io_source)
        self.io_src_edit.setMaximumWidth(140)
        self.io_src_edit.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #B0B0B0;"
            " padding: 3px 6px; font-size: 9pt; }")
        ribbon.addWidget(self.io_src_edit)
        ribbon.addSpacing(20)
        gen_btn = QPushButton("Generate Tags")
        gen_btn.setStyleSheet(_BTN_PRIMARY)
        gen_btn.clicked.connect(self._on_generate_tags)
        ribbon.addWidget(gen_btn)
        ribbon.addStretch()
        lay.addLayout(ribbon)

        # ── Top splitter: tag browser | tag generator ──
        top_split = QSplitter(Qt.Horizontal)

        # Tag browser tree
        browse_box = QGroupBox("Tag Browser")
        browse_box.setStyleSheet(_GROUP)
        bl = QVBoxLayout(browse_box)
        bl.setContentsMargins(6, 16, 6, 6)
        self.browser_tree = QTreeWidget()
        self.browser_tree.setHeaderLabels(["Node", "NodeId"])
        self.browser_tree.setStyleSheet(
            "QTreeWidget { background: white; border: 1px solid #B0B0B0;"
            " font-size: 9pt; }")
        self.browser_tree.itemDoubleClicked.connect(self._on_browser_double_click)
        bl.addWidget(self.browser_tree)
        refresh_btn = QPushButton("Refresh from Server")
        refresh_btn.setStyleSheet(_BTN_NEUTRAL)
        refresh_btn.clicked.connect(self._on_refresh_browser)
        bl.addWidget(refresh_btn)
        top_split.addWidget(browse_box)

        # Tag generator table
        gen_box = QGroupBox("Tag Generator")
        gen_box.setStyleSheet(_GROUP)
        gl = QVBoxLayout(gen_box)
        gl.setContentsMargins(6, 16, 6, 6)
        self.gen_table = QTableWidget()
        self.gen_table.setStyleSheet(_TABLE)
        self.gen_table.setColumnCount(6)
        self.gen_table.setHorizontalHeaderLabels([
            "Variable Name", "Type", "Generate", "Measurement Prefix",
            "Measurement Suffix", "Interface Point",
        ])
        self.gen_table.verticalHeader().setVisible(False)
        self.gen_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.gen_table.itemSelectionChanged.connect(self._on_gen_select)
        self.gen_table.cellChanged.connect(self._on_gen_changed)
        gl.addWidget(self.gen_table)
        top_split.addWidget(gen_box)
        top_split.setStretchFactor(0, 1)
        top_split.setStretchFactor(1, 3)
        lay.addWidget(top_split, 2)

        # ── Variable detail (bottom) ──
        det_box = QGroupBox("Variable Detail")
        det_box.setStyleSheet(_GROUP)
        dl = QVBoxLayout(det_box)
        dl.setContentsMargins(6, 16, 6, 6)
        self.detail_table = QTableWidget()
        self.detail_table.setStyleSheet(_TABLE)
        self.detail_table.setColumnCount(7)
        self.detail_table.setHorizontalHeaderLabels([
            "Parameter", "Role", "IO Source", "NodeId",
            "Datatype", "String Length", "Test Value",
        ])
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.detail_table.cellChanged.connect(self._on_detail_changed)
        dl.addWidget(self.detail_table)
        lay.addWidget(det_box, 1)

        return w

    # ==================================================================
    # Activity sub-tab
    # ==================================================================
    def _build_activity_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        live_box = QGroupBox("Live Variable Status")
        live_box.setStyleSheet(_GROUP)
        ll = QVBoxLayout(live_box)
        ll.setContentsMargins(6, 16, 6, 6)
        self.live_table = QTableWidget()
        self.live_table.setStyleSheet(_TABLE)
        self.live_table.setColumnCount(5)
        self.live_table.setHorizontalHeaderLabels([
            "Variable", "Type", "Status", "Last Value", "Read Fails",
        ])
        self.live_table.verticalHeader().setVisible(False)
        self.live_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        ll.addWidget(self.live_table)
        lay.addWidget(live_box, 2)

        log_box = QGroupBox("Activity Log")
        log_box.setStyleSheet(_GROUP)
        gl = QVBoxLayout(log_box)
        gl.setContentsMargins(6, 16, 6, 6)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            "QPlainTextEdit { background: #FFFFFF; color: #1A1A1A;"
            " font-family: Consolas; font-size: 9pt; border: 1px solid #B0B0B0; }")
        gl.addWidget(self.log_view)
        lay.addWidget(log_box, 1)

        return w

    # ==================================================================
    # Population
    # ==================================================================
    def _populate_all(self):
        self._populate_general_settings()
        self._populate_validation_tables()
        self._populate_gen_table()
        self._populate_live_table()

    def _populate_general_settings(self):
        gs = self.dep_cfg.general_settings
        self.gs_table.blockSignals(True)
        vals = [
            f"{gs.watchdog_sec:g}",
            f"{gs.cycle_offset_sec:g}",
            "Yes" if gs.setpoint_extended_validation else "No",
            str(gs.write_failure_limit),
            str(gs.read_failure_limit),
            str(gs.pad_io_tag_length),
        ]
        for i, v in enumerate(vals):
            it = QTableWidgetItem(v)
            self.gs_table.setItem(0, i, it)
        self.gs_table.blockSignals(False)

    def _populate_validation_tables(self):
        cfg = self.engine.cfg
        # Inputs = CV + DV
        in_vars = [vd for vd in self.dep_cfg.variables
                   if vd.var_type in (VarType.INPUT, VarType.DISTURBANCE)]
        out_vars = [vd for vd in self.dep_cfg.variables
                    if vd.var_type == VarType.OUTPUT]
        self._populate_validation_table(self.in_table, in_vars)
        self._populate_validation_table(self.out_table, out_vars)

    def _populate_validation_table(self, table, vars_list):
        table.blockSignals(True)
        table.setRowCount(len(vars_list))
        for row, vd in enumerate(vars_list):
            v = vd.validation
            cells = [
                vd.variable_tag,
                f"{v.validity_lo:g}", f"{v.engineer_lo:g}", f"{v.operator_lo:g}",
                f"{v.operator_hi:g}", f"{v.engineer_hi:g}", f"{v.validity_hi:g}",
                f"{v.timeout_sec:g}",
            ]
            for c, val in enumerate(cells):
                it = QTableWidgetItem(val)
                if c == 0:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    it.setBackground(QColor("#F0F2F5"))
                    it.setFont(QFont("Consolas", 9, QFont.Bold))
                table.setItem(row, c, it)
        table.blockSignals(False)

    def _populate_gen_table(self):
        self.gen_table.blockSignals(True)
        self.gen_table.setRowCount(len(self.dep_cfg.variables))
        for row, vd in enumerate(self.dep_cfg.variables):
            cells = [
                vd.variable_tag, vd.var_type.value, "",
                vd.measurement_prefix, vd.measurement_suffix, vd.interface_point,
            ]
            for c, val in enumerate(cells):
                it = QTableWidgetItem(val)
                if c <= 1:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    if c == 0:
                        it.setFont(QFont("Consolas", 9, QFont.Bold))
                    else:
                        # Color the type column
                        bg = {
                            VarType.INPUT: "#D5E8D4",
                            VarType.OUTPUT: "#DAE8FC",
                            VarType.DISTURBANCE: "#FFE6CC",
                            VarType.GENERAL: "#E1D5E7",
                        }.get(vd.var_type, "#FFFFFF")
                        it.setBackground(QColor(bg))
                self.gen_table.setItem(row, c, it)
            # Generate-Tags checkbox column
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.Checked if vd.generate_tags_enabled else Qt.Unchecked)
            chk.setFlags(chk.flags() | Qt.ItemIsUserCheckable)
            chk.setTextAlignment(Qt.AlignCenter)
            self.gen_table.setItem(row, 2, chk)
        self.gen_table.blockSignals(False)
        if self.dep_cfg.variables:
            self.gen_table.selectRow(0)

    def _populate_detail_table(self, vd: VariableDeployment):
        self.detail_table.blockSignals(True)
        self.detail_table.setRowCount(len(vd.io_tags))
        for row, t in enumerate(vd.io_tags):
            cells = [
                t.parameter, t.role.value, t.io_source, t.node_id,
                t.datatype, str(t.string_length), t.last_test_value,
            ]
            for c, val in enumerate(cells):
                it = QTableWidgetItem(val)
                if c == 0 or c == 1:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    if c == 0:
                        it.setFont(QFont("Consolas", 9, QFont.Bold))
                if c == 6 and t.last_test_ok is not None:
                    it.setBackground(QColor("#D5E8D4" if t.last_test_ok
                                            else "#F8CECC"))
                self.detail_table.setItem(row, c, it)
        self.detail_table.blockSignals(False)

    def _populate_live_table(self):
        self.live_table.setRowCount(len(self.dep_cfg.variables))
        for row, vd in enumerate(self.dep_cfg.variables):
            self.live_table.setItem(row, 0, QTableWidgetItem(vd.variable_tag))
            self.live_table.setItem(row, 1, QTableWidgetItem(vd.var_type.value))
            self.live_table.setItem(row, 2, QTableWidgetItem(vd.last_status))
            self.live_table.setItem(row, 3, QTableWidgetItem(
                f"{vd.last_good_value:.4g}" if vd.last_good_value is not None else "-"))
            self.live_table.setItem(row, 4, QTableWidgetItem(
                str(vd.read_failure_count)))

    # ==================================================================
    # Slots: Online Settings table edits
    # ==================================================================
    def _on_gs_changed(self, row, col):
        gs = self.dep_cfg.general_settings
        try:
            txt = self.gs_table.item(row, col).text().strip()
            if col == 0:
                gs.watchdog_sec = float(txt)
            elif col == 1:
                gs.cycle_offset_sec = float(txt)
            elif col == 2:
                gs.setpoint_extended_validation = txt.lower() in ("yes", "true", "1", "on")
            elif col == 3:
                gs.write_failure_limit = int(txt)
            elif col == 4:
                gs.read_failure_limit = int(txt)
            elif col == 5:
                gs.pad_io_tag_length = int(txt)
        except (ValueError, AttributeError):
            self._populate_general_settings()
            return
        self.config_changed.emit()

    def _on_validation_changed(self, table, kind, row, col):
        if col == 0:  # variable name is read-only
            return
        vd_name = table.item(row, 0).text()
        vd = self.dep_cfg.find(vd_name)
        if vd is None:
            return
        try:
            val = float(table.item(row, col).text())
        except (ValueError, AttributeError):
            self._populate_validation_tables()
            return
        v = vd.validation
        if   col == 1: v.validity_lo = val
        elif col == 2: v.engineer_lo = val
        elif col == 3: v.operator_lo = val
        elif col == 4: v.operator_hi = val
        elif col == 5: v.engineer_hi = val
        elif col == 6: v.validity_hi = val
        elif col == 7: v.timeout_sec = val
        self.config_changed.emit()

    # ==================================================================
    # Slots: IO Tags
    # ==================================================================
    def _on_gen_select(self):
        rows = self.gen_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if 0 <= row < len(self.dep_cfg.variables):
            self._current_var = self.dep_cfg.variables[row]
            self._populate_detail_table(self._current_var)

    def _on_gen_changed(self, row, col):
        if row >= len(self.dep_cfg.variables):
            return
        vd = self.dep_cfg.variables[row]
        if col == 2:
            vd.generate_tags_enabled = (
                self.gen_table.item(row, col).checkState() == Qt.Checked)
        elif col == 3:
            vd.measurement_prefix = self.gen_table.item(row, col).text()
        elif col == 4:
            vd.measurement_suffix = self.gen_table.item(row, col).text()
        elif col == 5:
            vd.interface_point = self.gen_table.item(row, col).text()

    def _on_detail_changed(self, row, col):
        if self._current_var is None:
            return
        if row >= len(self._current_var.io_tags):
            return
        t = self._current_var.io_tags[row]
        txt = self.detail_table.item(row, col).text()
        if col == 2:
            t.io_source = txt
        elif col == 3:
            t.node_id = txt
        elif col == 4:
            t.datatype = txt
        elif col == 5:
            try:
                t.string_length = int(txt)
            except ValueError:
                pass

    def _on_generate_tags(self):
        """Apply the selected template to every variable that has Generate=true."""
        template = self.template_combo.currentText()
        io_src = self.io_src_edit.text() or "OPCUA"
        n = 0
        for vd in self.dep_cfg.variables:
            if not vd.generate_tags_enabled:
                continue
            vd.template_name = template
            vd.io_tags = generate_io_tags(
                vd.variable_tag, vd.var_type, template=template,
                prefix=vd.measurement_prefix, suffix=vd.measurement_suffix,
                interface_point=vd.interface_point, io_source=io_src,
            )
            n += 1
        self.dep_cfg.default_template = template
        self.dep_cfg.default_io_source = io_src
        if self._current_var is not None:
            self._populate_detail_table(self._current_var)
        self._log_line("info", f"Generated tags for {n} variables (template={template})")

    def _on_browser_double_click(self, item, column):
        nid = item.text(1)
        if not nid or self._current_var is None:
            return
        # Apply to currently selected detail row
        rows = self.detail_table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        if 0 <= r < len(self._current_var.io_tags):
            self._current_var.io_tags[r].node_id = nid
            self.detail_table.item(r, 3).setText(nid)

    def _on_refresh_browser(self):
        if self.client is None or not self.client.connected:
            QMessageBox.information(
                self, "Tag Browser",
                "Click Connect first to browse the OPC UA address space.")
            return
        tree = self.client.browse_root(max_depth=4)
        self.browser_tree.clear()
        for root in tree:
            self._add_browser_node(self.browser_tree.invisibleRootItem(), root)
        self.browser_tree.expandToDepth(2)

    def _add_browser_node(self, parent_item, node_dict):
        item = QTreeWidgetItem(parent_item, [node_dict["name"], node_dict["node_id"]])
        for c in node_dict.get("children", []):
            self._add_browser_node(item, c)

    # ==================================================================
    # Slots: top connection bar
    # ==================================================================
    def _on_connect_clicked(self):
        if self.client and self.client.connected:
            self.client.disconnect()
            self.client = None
            self._set_connected(False)
            self.connect_btn.setText("Connect")
            return

        if self.embedded_chk.isChecked():
            if self.embedded is None:
                self.embedded = EmbeddedPlantServer(
                    self.engine, endpoint=self.dep_cfg.server_url)
            ok = self.embedded.start()
            if not ok:
                QMessageBox.critical(
                    self, "Embedded Server",
                    f"Failed to start embedded OPC UA server:\n{self.embedded.last_error}")
                return
            self._log_line("info", f"embedded server started at {self.dep_cfg.server_url}")

        self.client = OpcUaClient(self.dep_cfg.server_url)
        ok, err = self.client.connect()
        if not ok:
            QMessageBox.critical(
                self, "Connect", f"OPC UA connect failed:\n{err}")
            self.client = None
            return
        self._set_connected(True)
        self.connect_btn.setText("Disconnect")
        self._log_line("info", f"connected to {self.dep_cfg.server_url}")
        # Auto-refresh browser
        self._on_refresh_browser()

    def _on_test_clicked(self):
        if self.client is None or not self.client.connected:
            QMessageBox.information(
                self, "Test", "Click Connect first.")
            return
        n_ok = 0
        n_err = 0
        for vd in self.dep_cfg.variables:
            for t in vd.io_tags:
                if t.role == ParamRole.DIAGNOSTIC:
                    continue
                ok, val, err = self.client.read_one(t.node_id)
                t.last_test_ok = ok
                if ok:
                    t.last_test_value = f"{val}"
                    n_ok += 1
                else:
                    t.last_test_value = err
                    t.last_test_error = err
                    n_err += 1
        if self._current_var is not None:
            self._populate_detail_table(self._current_var)
        self._log_line("info",
                       f"Test Connections: {n_ok} OK, {n_err} failed")
        QMessageBox.information(
            self, "Test Connections",
            f"Tested {n_ok + n_err} tags\n  OK: {n_ok}\n  Failed: {n_err}")

    def _on_deploy_clicked(self):
        if self.runtime is not None and self.runtime.isRunning():
            QMessageBox.information(self, "Deploy",
                                    "Runtime is already running.")
            return
        # Auto-connect if not connected
        if self.client is None or not self.client.connected:
            self._on_connect_clicked()
            if self.client is None:
                return
        # Hand the connection back to the runtime so it owns the lifecycle
        self.client.disconnect()
        self.client = None

        self.runtime = DeploymentRuntime(
            self.engine, self.dep_cfg, embedded_server=self.embedded)
        self.runtime.cycle_completed.connect(self._on_cycle_completed)
        self.runtime.status_changed.connect(self._on_runtime_status)
        self.runtime.variable_status.connect(self._on_variable_status)
        self.runtime.log.connect(self._log_line)
        self.runtime.start()
        self.deploy_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.connect_btn.setEnabled(False)
        self.test_btn.setEnabled(False)

    def _on_stop_clicked(self):
        if self.runtime is None:
            return
        self.runtime.request_stop()
        self.runtime.wait(3000)
        self.runtime = None
        self.deploy_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.connect_btn.setEnabled(True)
        self.test_btn.setEnabled(True)
        self._set_connected(False)

    # ==================================================================
    # Runtime signal handlers
    # ==================================================================
    @Slot(int, float)
    def _on_cycle_completed(self, cycle, ms):
        self.cycle_label.setText(f"Cycle: {cycle}")
        self.cycle_ms_label.setText(f"Cycle Time: {ms:.1f} ms")
        if cycle % 5 == 0:
            self._populate_live_table()

    @Slot(str)
    def _on_runtime_status(self, status):
        self.runtime_status_label.setText(f"Runtime: {status}")
        if status == "RUNNING":
            self._set_connected(True)
        elif status == "STOPPED" or status.startswith("ERROR"):
            self._set_connected(False)

    @Slot(str, str, float)
    def _on_variable_status(self, tag, status, value):
        # Find the row in live_table and update
        for row in range(self.live_table.rowCount()):
            it = self.live_table.item(row, 0)
            if it and it.text() == tag:
                self.live_table.item(row, 2).setText(status)
                self.live_table.item(row, 3).setText(f"{value:.4g}")
                color = {
                    "OK": "#D5E8D4",
                    "BAD": "#F8CECC",
                    "OFFLINE": "#FFE6CC",
                    "WRITE_FAIL": "#F8CECC",
                }.get(status, "#FFFFFF")
                self.live_table.item(row, 2).setBackground(QColor(color))
                break

    # ==================================================================
    # Helpers
    # ==================================================================
    def _set_connected(self, connected: bool):
        if connected:
            self.conn_dot.setStyleSheet("color: #27AE60; font-size: 14pt;")
            self.conn_label.setText("CONNECTED")
        else:
            self.conn_dot.setStyleSheet("color: #C0392B; font-size: 14pt;")
            self.conn_label.setText("DISCONNECTED")

    def _log_line(self, level: str, msg: str):
        from time import strftime
        ts = strftime("%H:%M:%S")
        color = {"error": "#FF6B6B", "warn": "#FFD56B"}.get(level, "#A0E0FF")
        line = f"<span style='color:#707070'>{ts}</span> " \
               f"<span style='color:{color}'>[{level.upper()}]</span> {msg}"
        self.log_view.appendHtml(line)

    def shutdown(self):
        """Called by MainWindow when the app is closing."""
        if self.runtime is not None:
            self.runtime.request_stop()
            self.runtime.wait(2000)
        if self.client is not None:
            self.client.disconnect()
        if self.embedded is not None:
            self.embedded.stop()

    def set_engine(self, engine):
        """Rebind to a new engine after the optimizer rebuilds it."""
        self.shutdown()
        self.engine = engine
        self.dep_cfg = self._load_or_default()
        self.client = None
        self.embedded = None
        self.runtime = None
        self._populate_all()
