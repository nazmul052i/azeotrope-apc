"""DMC3-style Configuration tab.

Provides three sub-tabs:
  - Summary           : read-only dashboard of plant + controller info
  - Feedback Filters  : per-CV disturbance filter configuration
  - Subcontrollers    : variable grouping for prioritization
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QGridLayout, QSpinBox, QDoubleSpinBox, QCheckBox,
    QButtonGroup, QRadioButton, QFrame, QComboBox, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from azeoapc.models.config_loader import SimConfig, Subcontroller


_CLR_EDITABLE = QColor("#FFF8E8")
_CLR_HEADER = "#E4E4E4"
_CLR_PRIMARY = "#1A1A1A"


# ============================================================================
# Common styles
# ============================================================================
_GROUP_STYLE = """
QGroupBox {
    font-weight: bold; font-size: 9pt; color: #1A1A1A;
    border: 1px solid #B0B0B0; border-radius: 4px;
    margin-top: 10px; padding-top: 6px;
    background: #FAFBFD;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0 6px; background: #FAFBFD;
}
"""

_TABLE_STYLE = """
QTableWidget {
    background: white; alternate-background-color: #F5F5F5;
    border: 1px solid #B0B0B0; gridline-color: #B0B0B0;
    selection-background-color: #0066CC; selection-color: white;
    font-size: 9pt;
}
QTableWidget::item { padding: 2px 5px; }
QHeaderView::section {
    background: #E4E4E4; border: none;
    border-right: 1px solid #B0B0B0; border-bottom: 1px solid #B0B0B0;
    padding: 4px 6px; font-weight: 600; font-size: 8pt; color: #404040;
}
"""


# ============================================================================
# Summary View
# ============================================================================
class SummaryView(QWidget):
    """Read-only dashboard showing controller counts, sample time, etc."""

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        header = QLabel("Configuration Summary")
        header.setStyleSheet("font-size: 14pt; font-weight: 600; color: #1A1A1A;")
        root.addWidget(header)

        intro = QLabel(
            "Read-only overview of the loaded controller application. "
            "Use the other sub-tabs to configure feedback filters and subcontroller groups."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #707070; font-size: 9pt; padding: 4px 0;")
        root.addWidget(intro)

        # ── Application section (key/value grid) ──
        app_box = QGroupBox("Application")
        app_box.setStyleSheet(_GROUP_STYLE)
        self.app_grid = QGridLayout(app_box)
        self.app_grid.setContentsMargins(14, 18, 14, 12)
        self.app_grid.setHorizontalSpacing(20)
        self.app_grid.setVerticalSpacing(8)
        root.addWidget(app_box)

        # ── Variable counts section ──
        cnt_box = QGroupBox("Variable Counts")
        cnt_box.setStyleSheet(_GROUP_STYLE)
        self.cnt_grid = QGridLayout(cnt_box)
        self.cnt_grid.setContentsMargins(14, 18, 14, 12)
        self.cnt_grid.setHorizontalSpacing(20)
        self.cnt_grid.setVerticalSpacing(8)
        root.addWidget(cnt_box)

        # ── Subcontrollers table ──
        sub_box = QGroupBox("Subcontrollers")
        sub_box.setStyleSheet(_GROUP_STYLE)
        sub_lay = QVBoxLayout(sub_box)
        sub_lay.setContentsMargins(8, 16, 8, 8)
        self.sub_table = QTableWidget()
        self.sub_table.setStyleSheet(_TABLE_STYLE)
        self.sub_table.setColumnCount(6)
        self.sub_table.setHorizontalHeaderLabels(
            ["Name", "Description", "MVs", "DVs", "CVs", "Critical"])
        self.sub_table.verticalHeader().setVisible(False)
        self.sub_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sub_table.setMaximumHeight(140)
        sub_lay.addWidget(self.sub_table)
        root.addWidget(sub_box)

        # ── Feedback filter summary ──
        flt_box = QGroupBox("Feedback Filters Summary")
        flt_box.setStyleSheet(_GROUP_STYLE)
        flt_lay = QVBoxLayout(flt_box)
        flt_lay.setContentsMargins(8, 16, 8, 8)
        self.flt_table = QTableWidget()
        self.flt_table.setStyleSheet(_TABLE_STYLE)
        self.flt_table.setColumnCount(4)
        self.flt_table.setHorizontalHeaderLabels(
            ["CV Tag", "Description", "Filter Type", "Intermittent"])
        self.flt_table.verticalHeader().setVisible(False)
        self.flt_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.flt_table.setMaximumHeight(180)
        flt_lay.addWidget(self.flt_table)
        root.addWidget(flt_box)

        root.addStretch()

    def _make_value(self, text, bold=True):
        lbl = QLabel(str(text))
        font_weight = "bold" if bold else "normal"
        lbl.setStyleSheet(
            f"font-size: 11pt; font-weight: {font_weight}; color: #1A1A1A; "
            f"font-family: Consolas, monospace;")
        return lbl

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 9pt; color: #707070;")
        return lbl

    def _clear_grid(self, grid):
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def refresh(self):
        cfg = self.cfg

        # Application info
        self._clear_grid(self.app_grid)
        plant_type = type(cfg.plant).__name__ if cfg.plant else "None"
        layer3 = "Enabled" if (getattr(cfg, "layer3", None)
                               and cfg.layer3.enabled) else "Disabled"
        rows = [
            ("Application Name:", cfg.name),
            ("Description:", cfg.description or "—"),
            ("Plant Model Type:", plant_type),
            ("Sample Time:", f"{cfg.sample_time} min"),
            ("Time to Steady State:", f"{cfg.time_to_steady_state} min"
                if cfg.time_to_steady_state > 0 else "(auto)"),
            ("Prediction Horizon:", f"{cfg.optimizer.prediction_horizon} steps"),
            ("Control Horizon:", f"{cfg.optimizer.control_horizon} steps"),
            ("Model Horizon:", f"{cfg.optimizer.model_horizon} steps"),
            ("Layer 3 RTO:", layer3),
        ]
        for r, (k, v) in enumerate(rows):
            self.app_grid.addWidget(self._make_label(k), r, 0)
            self.app_grid.addWidget(self._make_value(v), r, 1)
        self.app_grid.setColumnStretch(2, 1)

        # Variable counts
        self._clear_grid(self.cnt_grid)
        n_mv = len(cfg.mvs)
        n_cv = len(cfg.cvs)
        n_dv = len(cfg.dvs)
        n_sub = len(cfg.subcontrollers)
        cnts = [
            ("Manipulated Variables:", n_mv),
            ("Disturbance Variables:", n_dv),
            ("Controlled Variables:", n_cv),
            ("Subcontrollers:", n_sub),
        ]
        for r, (k, v) in enumerate(cnts):
            self.cnt_grid.addWidget(self._make_label(k), r, 0)
            self.cnt_grid.addWidget(self._make_value(v), r, 1)
        self.cnt_grid.setColumnStretch(2, 1)

        # Subcontrollers table
        self.sub_table.setRowCount(len(cfg.subcontrollers))
        for r, sub in enumerate(cfg.subcontrollers):
            n_mvs = sum(1 for mv in cfg.mvs if mv.subcontroller == sub.name)
            n_dvs = sum(1 for dv in cfg.dvs if dv.subcontroller == sub.name)
            n_cvs = sum(1 for cv in cfg.cvs if cv.subcontroller == sub.name)
            items = [sub.name, sub.description or "—",
                     str(n_mvs), str(n_dvs), str(n_cvs),
                     "Yes" if sub.is_critical else "No"]
            for c, txt in enumerate(items):
                it = QTableWidgetItem(txt)
                if c >= 2 and c <= 4:
                    it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.sub_table.setItem(r, c, it)
        self.sub_table.resizeColumnsToContents()
        self.sub_table.horizontalHeader().setStretchLastSection(True)

        # Feedback filter summary
        self.flt_table.setRowCount(len(cfg.cvs))
        for r, cv in enumerate(cfg.cvs):
            items = [cv.tag, cv.name, cv.filter_type,
                     "Yes" if cv.intermittent else "No"]
            for c, txt in enumerate(items):
                it = QTableWidgetItem(txt)
                if c == 3:
                    it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.flt_table.setItem(r, c, it)
        self.flt_table.resizeColumnsToContents()
        self.flt_table.horizontalHeader().setStretchLastSection(True)


# ============================================================================
# Feedback Filters View
# ============================================================================
class FeedbackFiltersView(QWidget):
    """Per-CV disturbance filter configuration."""

    changed = Signal()

    FILTER_TYPES = ["Full Feedback", "First Order", "Moving Average"]

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        header = QLabel("Feedback Filters")
        header.setStyleSheet("font-size: 14pt; font-weight: 600; color: #1A1A1A;")
        root.addWidget(header)

        intro = QLabel(
            "Configure the disturbance filter for each CV. The filter determines "
            "how prediction error is fed back to update the model.<br>"
            "<b>Full Feedback</b>: full bias applied each cycle (use for trusted measurements).<br>"
            "<b>First Order</b>: exponential filter, dampens noisy CVs (set <i>Pred Error Lag</i>).<br>"
            "<b>Moving Average</b>: averages past N errors (set <i>Pred Err Horizon</i>)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #707070; font-size: 9pt; padding: 4px 0;")
        root.addWidget(intro)

        self.table = QTableWidget()
        self.table.setStyleSheet(_TABLE_STYLE)
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "CV Tag", "Description", "Units",
            "Full Feedback", "First Order", "Moving Average",
            "Intermittent", "Pred Error Lag", "Pred Err Horizon", "Rotation Factor"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

        # Bottom action row
        btn_row = QHBoxLayout()
        apply_all_btn = QPushButton("Apply Full Feedback to All")
        apply_all_btn.setStyleSheet(
            "QPushButton { background: #707070; color: white; border: none; "
            "border-radius: 3px; padding: 6px 16px; font-size: 9pt; font-weight: 600; }"
            "QPushButton:hover { background: #8899BB; }")
        apply_all_btn.clicked.connect(self._apply_full_to_all)
        btn_row.addWidget(apply_all_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

    def _apply_full_to_all(self):
        for cv in self.cfg.cvs:
            cv.filter_type = "Full Feedback"
        self.refresh()
        self.changed.emit()

    def refresh(self):
        cfg = self.cfg
        self.table.setRowCount(len(cfg.cvs))
        for r, cv in enumerate(cfg.cvs):
            # Tag, description, units (read-only)
            for c, txt in enumerate([cv.tag, cv.name, cv.units]):
                it = QTableWidgetItem(txt)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, it)

            # Mutually-exclusive filter type radios (cols 3, 4, 5)
            grp = QButtonGroup(self.table)
            for c, ft in enumerate(self.FILTER_TYPES):
                rb = QRadioButton()
                rb.setChecked(cv.filter_type == ft)
                rb.setStyleSheet(
                    "QRadioButton { background: transparent; padding: 4px; }"
                    "QRadioButton::indicator { width: 14px; height: 14px; }")
                rb.toggled.connect(
                    lambda checked, row=r, ftype=ft: self._on_filter_changed(row, ftype, checked))
                grp.addButton(rb)
                # Wrap radio in centered container
                cell = QWidget()
                lay = QHBoxLayout(cell)
                lay.setContentsMargins(0, 0, 0, 0)
                lay.addWidget(rb, alignment=Qt.AlignCenter)
                self.table.setCellWidget(r, 3 + c, cell)

            # Intermittent checkbox (col 6)
            chk = QCheckBox()
            chk.setChecked(cv.intermittent)
            chk.setStyleSheet(
                "QCheckBox { background: transparent; padding: 4px; }"
                "QCheckBox::indicator { width: 14px; height: 14px; }")
            chk.toggled.connect(
                lambda checked, row=r: self._on_intermittent(row, checked))
            chk_cell = QWidget()
            chk_lay = QHBoxLayout(chk_cell)
            chk_lay.setContentsMargins(0, 0, 0, 0)
            chk_lay.addWidget(chk, alignment=Qt.AlignCenter)
            self.table.setCellWidget(r, 6, chk_cell)

            # Pred Error Lag (col 7)
            lag = QDoubleSpinBox()
            lag.setRange(0.0, 1e6)
            lag.setValue(cv.pred_error_lag)
            lag.setDecimals(3)
            lag.setSuffix(" min")
            lag.setStyleSheet("QDoubleSpinBox { background: #FFF8E8; padding: 2px; }")
            lag.valueChanged.connect(
                lambda v, row=r: self._on_lag(row, v))
            self.table.setCellWidget(r, 7, lag)

            # Pred Err Horizon (col 8)
            hz = QSpinBox()
            hz.setRange(0, 10000)
            hz.setValue(cv.pred_error_horizon)
            hz.setSuffix(" steps")
            hz.setStyleSheet("QSpinBox { background: #FFF8E8; padding: 2px; }")
            hz.valueChanged.connect(
                lambda v, row=r: self._on_horizon(row, v))
            self.table.setCellWidget(r, 8, hz)

            # Rotation Factor (col 9, only meaningful for ramp variables)
            rot = QDoubleSpinBox()
            rot.setRange(0.0, 1.0)
            rot.setValue(cv.rotation_factor)
            rot.setDecimals(3)
            rot.setSingleStep(0.05)
            rot.setStyleSheet("QDoubleSpinBox { background: #FFF8E8; padding: 2px; }")
            rot.valueChanged.connect(
                lambda v, row=r: self._on_rotation(row, v))
            self.table.setCellWidget(r, 9, rot)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(False)

    def _on_filter_changed(self, row, ftype, checked):
        if not checked:
            return
        if row < len(self.cfg.cvs):
            self.cfg.cvs[row].filter_type = ftype
            self.changed.emit()

    def _on_intermittent(self, row, checked):
        if row < len(self.cfg.cvs):
            self.cfg.cvs[row].intermittent = checked
            self.changed.emit()

    def _on_lag(self, row, v):
        if row < len(self.cfg.cvs):
            self.cfg.cvs[row].pred_error_lag = v
            self.changed.emit()

    def _on_horizon(self, row, v):
        if row < len(self.cfg.cvs):
            self.cfg.cvs[row].pred_error_horizon = int(v)
            self.changed.emit()

    def _on_rotation(self, row, v):
        if row < len(self.cfg.cvs):
            self.cfg.cvs[row].rotation_factor = v
            self.changed.emit()


# ============================================================================
# Subcontrollers View
# ============================================================================
class SubcontrollersView(QWidget):
    """Variable grouping view -- assign each MV/DV/CV to a subcontroller."""

    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        header = QLabel("Subcontrollers")
        header.setStyleSheet("font-size: 14pt; font-weight: 600; color: #1A1A1A;")
        root.addWidget(header)

        intro = QLabel(
            "Organize MVs and CVs into subcontroller groups. Each MV must belong "
            "to exactly one subcontroller; CVs may belong to one or more. "
            "Use subcontrollers to logically partition large applications "
            "(e.g., one per unit operation)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #707070; font-size: 9pt; padding: 4px 0;")
        root.addWidget(intro)

        # Action toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        add_btn = QPushButton("+ Add Subcontroller")
        add_btn.setStyleSheet(
            "QPushButton { background: #2E8B57; color: white; border: none; "
            "border-radius: 3px; padding: 6px 14px; font-size: 9pt; font-weight: 600; }"
            "QPushButton:hover { background: #2E8B57; }")
        add_btn.clicked.connect(self._add_subcontroller)
        toolbar.addWidget(add_btn)

        del_btn = QPushButton("− Delete Selected")
        del_btn.setStyleSheet(
            "QPushButton { background: #C0392B; color: white; border: none; "
            "border-radius: 3px; padding: 6px 14px; font-size: 9pt; font-weight: 600; }"
            "QPushButton:hover { background: #C0392B; }")
        del_btn.clicked.connect(self._delete_subcontroller)
        toolbar.addWidget(del_btn)

        toolbar.addStretch()
        root.addLayout(toolbar)

        # ── Subcontroller properties table ──
        prop_box = QGroupBox("Subcontroller Properties")
        prop_box.setStyleSheet(_GROUP_STYLE)
        prop_lay = QVBoxLayout(prop_box)
        prop_lay.setContentsMargins(8, 16, 8, 8)

        self.prop_table = QTableWidget()
        self.prop_table.setStyleSheet(_TABLE_STYLE)
        self.prop_table.setColumnCount(5)
        self.prop_table.setHorizontalHeaderLabels(
            ["Name", "Description", "Is Critical", "Min Good MVs", "Min Good CVs"])
        self.prop_table.verticalHeader().setVisible(False)
        self.prop_table.setMaximumHeight(150)
        self.prop_table.cellChanged.connect(self._on_prop_changed)
        prop_lay.addWidget(self.prop_table)
        root.addWidget(prop_box)

        # ── Variable assignment table ──
        var_box = QGroupBox("Variable Assignment")
        var_box.setStyleSheet(_GROUP_STYLE)
        var_lay = QVBoxLayout(var_box)
        var_lay.setContentsMargins(8, 16, 8, 8)

        self.var_table = QTableWidget()
        self.var_table.setStyleSheet(_TABLE_STYLE)
        self.var_table.verticalHeader().setVisible(False)
        var_lay.addWidget(self.var_table)
        root.addWidget(var_box, 1)

    def refresh(self):
        cfg = self.cfg

        # ── Properties table ──
        self.prop_table.blockSignals(True)
        self.prop_table.setRowCount(len(cfg.subcontrollers))
        for r, sub in enumerate(cfg.subcontrollers):
            self.prop_table.setItem(r, 0, QTableWidgetItem(sub.name))
            self.prop_table.setItem(r, 1, QTableWidgetItem(sub.description))

            # Is Critical checkbox
            crit_chk = QCheckBox()
            crit_chk.setChecked(sub.is_critical)
            crit_chk.toggled.connect(
                lambda checked, row=r: self._on_critical(row, checked))
            crit_cell = QWidget()
            crit_lay = QHBoxLayout(crit_cell)
            crit_lay.setContentsMargins(0, 0, 0, 0)
            crit_lay.addWidget(crit_chk, alignment=Qt.AlignCenter)
            self.prop_table.setCellWidget(r, 2, crit_cell)

            mvs_spin = QSpinBox()
            mvs_spin.setRange(0, 1000)
            mvs_spin.setValue(sub.min_good_mvs)
            mvs_spin.valueChanged.connect(
                lambda v, row=r: self._on_min_mvs(row, v))
            self.prop_table.setCellWidget(r, 3, mvs_spin)

            cvs_spin = QSpinBox()
            cvs_spin.setRange(0, 1000)
            cvs_spin.setValue(sub.min_good_cvs)
            cvs_spin.valueChanged.connect(
                lambda v, row=r: self._on_min_cvs(row, v))
            self.prop_table.setCellWidget(r, 4, cvs_spin)

        for c in range(self.prop_table.columnCount()):
            self.prop_table.setColumnWidth(c, 140)
        self.prop_table.blockSignals(False)

        # ── Variable assignment table ──
        n_subs = len(cfg.subcontrollers)
        # Columns: Tag | Description | Type | <one column per subcontroller>
        self.var_table.setColumnCount(3 + n_subs)
        headers = ["Tag", "Description", "Type"]
        headers.extend([sub.name for sub in cfg.subcontrollers])
        self.var_table.setHorizontalHeaderLabels(headers)

        all_vars = (
            [("MV", mv) for mv in cfg.mvs] +
            [("DV", dv) for dv in cfg.dvs] +
            [("CV", cv) for cv in cfg.cvs]
        )
        self.var_table.setRowCount(len(all_vars))

        for r, (vtype, var) in enumerate(all_vars):
            tag_item = QTableWidgetItem(var.tag)
            tag_item.setFlags(tag_item.flags() & ~Qt.ItemIsEditable)
            self.var_table.setItem(r, 0, tag_item)

            name_item = QTableWidgetItem(var.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.var_table.setItem(r, 1, name_item)

            type_item = QTableWidgetItem(vtype)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            type_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            # Color by type
            if vtype == "MV":
                type_item.setForeground(QColor("#0055AA"))
            elif vtype == "DV":
                type_item.setForeground(QColor("#996600"))
            else:
                type_item.setForeground(QColor("#107C10"))
            self.var_table.setItem(r, 2, type_item)

            # MVs/DVs use radio buttons (single assignment), CVs use checkboxes
            if vtype in ("MV", "DV"):
                grp = QButtonGroup(self.var_table)
                for c, sub in enumerate(cfg.subcontrollers):
                    rb = QRadioButton()
                    rb.setChecked(var.subcontroller == sub.name)
                    rb.setStyleSheet(
                        "QRadioButton { background: transparent; padding: 4px; }"
                        "QRadioButton::indicator { width: 14px; height: 14px; }")
                    rb.toggled.connect(
                        lambda checked, vv=var, ss=sub.name:
                        self._on_var_assign(vv, ss, checked))
                    grp.addButton(rb)
                    cell = QWidget()
                    lay = QHBoxLayout(cell)
                    lay.setContentsMargins(0, 0, 0, 0)
                    lay.addWidget(rb, alignment=Qt.AlignCenter)
                    self.var_table.setCellWidget(r, 3 + c, cell)
            else:
                # CVs: checkbox per subcontroller
                for c, sub in enumerate(cfg.subcontrollers):
                    chk = QCheckBox()
                    chk.setChecked(var.subcontroller == sub.name)
                    chk.setStyleSheet(
                        "QCheckBox { background: transparent; padding: 4px; }"
                        "QCheckBox::indicator { width: 14px; height: 14px; }")
                    chk.toggled.connect(
                        lambda checked, vv=var, ss=sub.name:
                        self._on_cv_assign(vv, ss, checked))
                    cell = QWidget()
                    lay = QHBoxLayout(cell)
                    lay.setContentsMargins(0, 0, 0, 0)
                    lay.addWidget(chk, alignment=Qt.AlignCenter)
                    self.var_table.setCellWidget(r, 3 + c, cell)

        self.var_table.resizeColumnsToContents()
        for c in range(3, self.var_table.columnCount()):
            self.var_table.setColumnWidth(c, 100)

    def _add_subcontroller(self):
        existing = {s.name for s in self.cfg.subcontrollers}
        n = len(self.cfg.subcontrollers) + 1
        while f"SUB{n}" in existing:
            n += 1
        new_sub = Subcontroller(name=f"SUB{n}", description="")
        self.cfg.subcontrollers.append(new_sub)
        self.refresh()
        self.changed.emit()

    def _delete_subcontroller(self):
        if len(self.cfg.subcontrollers) <= 1:
            QMessageBox.warning(self, "Delete Subcontroller",
                                "Cannot delete the last subcontroller.")
            return
        rows = set()
        for it in self.prop_table.selectedItems():
            rows.add(it.row())
        if not rows:
            QMessageBox.information(self, "Delete Subcontroller",
                                    "Select a subcontroller row to delete.")
            return
        row = min(rows)
        sub = self.cfg.subcontrollers[row]
        # Reassign any variables from the deleted subcontroller to the first remaining
        target = self.cfg.subcontrollers[0].name if row != 0 else self.cfg.subcontrollers[1].name
        for mv in self.cfg.mvs:
            if mv.subcontroller == sub.name:
                mv.subcontroller = target
        for dv in self.cfg.dvs:
            if dv.subcontroller == sub.name:
                dv.subcontroller = target
        for cv in self.cfg.cvs:
            if cv.subcontroller == sub.name:
                cv.subcontroller = target
        del self.cfg.subcontrollers[row]
        self.refresh()
        self.changed.emit()

    def _on_prop_changed(self, row, col):
        if row >= len(self.cfg.subcontrollers):
            return
        sub = self.cfg.subcontrollers[row]
        item = self.prop_table.item(row, col)
        if item is None:
            return
        text = item.text().strip()
        if col == 0:
            new_name = text
            old_name = sub.name
            if new_name and new_name != old_name:
                # Update all variables with old name
                for mv in self.cfg.mvs:
                    if mv.subcontroller == old_name:
                        mv.subcontroller = new_name
                for dv in self.cfg.dvs:
                    if dv.subcontroller == old_name:
                        dv.subcontroller = new_name
                for cv in self.cfg.cvs:
                    if cv.subcontroller == old_name:
                        cv.subcontroller = new_name
                sub.name = new_name
                # Refresh var table headers
                self.var_table.setHorizontalHeaderItem(
                    3 + row, QTableWidgetItem(new_name))
                self.changed.emit()
        elif col == 1:
            sub.description = text
            self.changed.emit()

    def _on_critical(self, row, checked):
        if row < len(self.cfg.subcontrollers):
            self.cfg.subcontrollers[row].is_critical = checked
            self.changed.emit()

    def _on_min_mvs(self, row, v):
        if row < len(self.cfg.subcontrollers):
            self.cfg.subcontrollers[row].min_good_mvs = int(v)
            self.changed.emit()

    def _on_min_cvs(self, row, v):
        if row < len(self.cfg.subcontrollers):
            self.cfg.subcontrollers[row].min_good_cvs = int(v)
            self.changed.emit()

    def _on_var_assign(self, var, sub_name, checked):
        if checked:
            var.subcontroller = sub_name
            self.changed.emit()

    def _on_cv_assign(self, cv, sub_name, checked):
        if checked:
            cv.subcontroller = sub_name
            self.changed.emit()


# ============================================================================
# Variables View (editable MV / CV / DV properties)
# ============================================================================
class VariablesView(QWidget):
    """Editable table of all MVs, CVs, and DVs.

    The user can edit: tag, name, description, units, steady_state,
    engineering limits (lo/hi), operating limits (lo/hi), and — for
    CVs — setpoint and weight. Changes write directly back into the
    SimConfig objects.
    """

    changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        header = QLabel("Variable Properties")
        header.setStyleSheet(f"font-size: 14pt; font-weight: 600; color: {_CLR_PRIMARY};")
        root.addWidget(header)

        intro = QLabel(
            "Edit tag names, descriptions, units, steady-state values, and "
            "limits for every MV, CV, and DV. Changes are applied immediately "
            "to the controller configuration."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #707070; font-size: 9pt; padding: 4px 0;")
        root.addWidget(intro)

        self.table = QTableWidget()
        self.table.setStyleSheet(_TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        _cols = [
            "Type", "Tag", "Name", "Description", "Units",
            "Steady State", "Eng Lo", "Eng Hi", "Op Lo", "Op Hi",
            "Setpoint", "Weight",
        ]
        self.table.setColumnCount(len(_cols))
        self.table.setHorizontalHeaderLabels(_cols)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Interactive)
        hh.setSectionResizeMode(2, QHeaderView.Interactive)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        for c in range(4, len(_cols)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)

        self.table.cellChanged.connect(self._on_cell_changed)
        root.addWidget(self.table, 1)

    def refresh(self):
        self.table.blockSignals(True)
        rows = []
        for mv in self.cfg.mvs:
            rows.append(("MV", mv))
        for cv in self.cfg.cvs:
            rows.append(("CV", cv))
        for dv in self.cfg.dvs:
            rows.append(("DV", dv))

        self.table.setRowCount(len(rows))
        self._rows = rows

        for r, (typ, var) in enumerate(rows):
            # Type (read-only, colored)
            type_item = QTableWidgetItem(typ)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            type_colors = {"MV": "#0066CC", "CV": "#2E8B57", "DV": "#D9822B"}
            type_item.setForeground(QColor(type_colors.get(typ, "#707070")))
            type_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table.setItem(r, 0, type_item)

            # Tag
            self.table.setItem(r, 1, QTableWidgetItem(var.tag))
            # Name
            self.table.setItem(r, 2, QTableWidgetItem(var.name))
            # Description (MV/CV only — DVs may not have one)
            desc = ""
            self.table.setItem(r, 3, QTableWidgetItem(desc))
            # Units
            self.table.setItem(r, 4, QTableWidgetItem(var.units))
            # Steady state
            self.table.setItem(r, 5, QTableWidgetItem(f"{var.steady_state:g}"))

            # Limits
            lim = var.limits
            self.table.setItem(r, 6, QTableWidgetItem(
                f"{lim.engineering_lo:g}" if lim.engineering_lo > -1e19 else ""))
            self.table.setItem(r, 7, QTableWidgetItem(
                f"{lim.engineering_hi:g}" if lim.engineering_hi < 1e19 else ""))
            self.table.setItem(r, 8, QTableWidgetItem(
                f"{lim.operating_lo:g}" if lim.operating_lo > -1e19 else ""))
            self.table.setItem(r, 9, QTableWidgetItem(
                f"{lim.operating_hi:g}" if lim.operating_hi < 1e19 else ""))

            # Setpoint + weight (CV only)
            if typ == "CV":
                self.table.setItem(r, 10, QTableWidgetItem(f"{var.setpoint:g}"))
                self.table.setItem(r, 11, QTableWidgetItem(f"{var.weight:g}"))
            else:
                sp_item = QTableWidgetItem("")
                sp_item.setFlags(sp_item.flags() & ~Qt.ItemIsEditable)
                sp_item.setBackground(QColor("#F0F0F0"))
                self.table.setItem(r, 10, sp_item)
                wt_item = QTableWidgetItem("")
                wt_item.setFlags(wt_item.flags() & ~Qt.ItemIsEditable)
                wt_item.setBackground(QColor("#F0F0F0"))
                self.table.setItem(r, 11, wt_item)

            # Color editable cells
            for c in range(1, 10):
                item = self.table.item(r, c)
                if item is not None:
                    item.setBackground(_CLR_EDITABLE)

        self.table.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int):
        if row >= len(self._rows):
            return
        typ, var = self._rows[row]
        text = self.table.item(row, col).text().strip()

        try:
            if col == 1:
                var.tag = text
            elif col == 2:
                var.name = text
            elif col == 4:
                var.units = text
            elif col == 5 and text:
                var.steady_state = float(text)
            elif col == 6 and text:
                var.limits.engineering_lo = float(text)
            elif col == 7 and text:
                var.limits.engineering_hi = float(text)
            elif col == 8 and text:
                var.limits.operating_lo = float(text)
            elif col == 9 and text:
                var.limits.operating_hi = float(text)
            elif col == 10 and typ == "CV" and text:
                var.setpoint = float(text)
            elif col == 11 and typ == "CV" and text:
                var.weight = float(text)
        except (ValueError, AttributeError):
            self.refresh()
            return
        self.changed.emit()


# ============================================================================
# Main Configuration Window
# ============================================================================
class ConfigurationWindow(QWidget):
    """Top-level Configuration tab with four sub-tabs."""

    config_changed = Signal()

    def __init__(self, config: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
        QTabWidget::pane {
            border: 1px solid #B0B0B0;
            background: #ECECEC;
        }
        QTabBar::tab {
            background: #DDE2EC;
            border: 1px solid #B0B0B0;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: 8px 24px;
            margin-right: 2px;
            font-size: 10pt;
            color: #404040;
            min-width: 140px;
        }
        QTabBar::tab:selected {
            background: #ECECEC;
            font-weight: 600;
            color: #1A1A1A;
            border-top: 2px solid #0066CC;
        }
        """)

        self.summary_view = SummaryView(self.cfg)
        self.variables_view = VariablesView(self.cfg)
        self.filters_view = FeedbackFiltersView(self.cfg)
        self.subs_view = SubcontrollersView(self.cfg)

        self.tabs.addTab(self.summary_view, "  Summary  ")
        self.tabs.addTab(self.variables_view, "  Variables  ")
        self.tabs.addTab(self.filters_view, "  Feedback Filters  ")
        self.tabs.addTab(self.subs_view, "  Subcontrollers  ")

        # Refresh summary when other views change
        self.variables_view.changed.connect(self._on_changed)
        self.filters_view.changed.connect(self._on_changed)
        self.subs_view.changed.connect(self._on_changed)

        root.addWidget(self.tabs, 1)

    def _on_changed(self):
        # Refresh the summary when filters or subs change
        self.summary_view.refresh()
        self.config_changed.emit()

    def refresh(self):
        self.summary_view.refresh()
        self.variables_view.refresh()
        self.filters_view.refresh()
        self.subs_view.refresh()
