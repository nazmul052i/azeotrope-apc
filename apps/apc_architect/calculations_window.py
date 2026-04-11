"""Calculations tab GUI.

Layout:
  ┌─ Calculations ──────────────────  [Input Calcs ✓] [Output Calcs ✓] ─┐
  │ ┌─ List ──────────────────────┐ ┌─ Editor ──────────────────────┐  │
  │ │ # Type  Name      Status   │ │ # Python source code          │  │
  │ │ 1 Input AvgTemp   ✓ OK     │ │                                │  │
  │ │ 2 Input Validate  ✓ OK     │ │                                │  │
  │ │ 3 Out   Clamp     ⚠ ERR    │ │                                │  │
  │ │ [+New] [-Del] [↑] [↓]      │ │ [Apply Ctrl+S] [Test Run]     │  │
  │ └─────────────────────────────┘ └────────────────────────────────┘  │
  │ ┌─ Variables Browser ──┐ ┌─ Live State ──────────────────────────┐  │
  │ │ ▼ MVs                │ │ Variable          Value     Source    │  │
  │ │   FIC-101.SP         │ │ user.history     [752,...]  user      │  │
  │ │ ▼ CVs                │ │ TI-201.value     752.4      CV        │  │
  │ │   TI-201.PV          │ │ TI-201.weight    10.0       tuning    │  │
  │ │ ▼ DVs                │ └────────────────────────────────────────┘  │
  │ └──────────────────────┘ ┌─ Activity Log ────────────────────────┐  │
  │                           │ 14:32 ✓ AvgTemp 0.12ms                │  │
  │                           │ 14:32 ⚠ Adaptive KeyError             │  │
  │                           └────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
    QSplitter, QTreeWidget, QTreeWidgetItem, QGroupBox, QFrame,
    QCheckBox, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QKeySequence, QShortcut,
    QSyntaxHighlighter, QTextCharFormat,
)
import re

from azeoapc.calculations import Calculation, CalculationRunner


_TABLE_STYLE = """
QTableWidget {
    background: white; alternate-background-color: #F5F5F5;
    border: 1px solid #B0B0B0; gridline-color: #B0B0B0;
    selection-background-color: #0066CC; selection-color: white;
    font-size: 9pt;
}
QTableWidget::item { padding: 3px 6px; }
QHeaderView::section {
    background: #E4E4E4; border: none;
    border-right: 1px solid #B0B0B0; border-bottom: 1px solid #B0B0B0;
    padding: 4px 8px; font-weight: 600; font-size: 8pt; color: #404040;
}
"""

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

_EDITOR_STYLE = """
QPlainTextEdit {
    background: #FFFFFF; color: #1A1A1A;
    font-family: Consolas, "Courier New", monospace;
    font-size: 10pt;
    border: 1px solid #D8D8D8;
    selection-background-color: #0066CC;
}
"""


# ============================================================================
# Python syntax highlighter (basic)
# ============================================================================
class PythonHighlighter(QSyntaxHighlighter):
    KEYWORDS = [
        "False", "None", "True", "and", "as", "assert", "async", "await",
        "break", "class", "continue", "def", "del", "elif", "else", "except",
        "finally", "for", "from", "global", "if", "import", "in", "is",
        "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
        "while", "with", "yield",
    ]
    BUILTINS = [
        "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
        "int", "len", "list", "map", "max", "min", "print", "range", "repr",
        "round", "set", "sorted", "str", "sum", "tuple", "type", "zip",
    ]
    SPECIAL_VARS = [
        "cvs", "mvs", "dvs", "cv", "mv", "dv", "user", "t", "cycle", "dt",
        "engine", "np", "numpy", "math", "log", "self",
    ]

    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        # Keywords
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#FF79C6"))
        kw_fmt.setFontWeight(QFont.Bold)
        for kw in self.KEYWORDS:
            self.rules.append((re.compile(r'\b' + kw + r'\b'), kw_fmt))

        # Builtins
        bi_fmt = QTextCharFormat()
        bi_fmt.setForeground(QColor("#8BE9FD"))
        for bi in self.BUILTINS:
            self.rules.append((re.compile(r'\b' + bi + r'\b'), bi_fmt))

        # Special vars
        sv_fmt = QTextCharFormat()
        sv_fmt.setForeground(QColor("#50FA7B"))
        sv_fmt.setFontWeight(QFont.Bold)
        for sv in self.SPECIAL_VARS:
            self.rules.append((re.compile(r'\b' + sv + r'\b'), sv_fmt))

        # Numbers
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#BD93F9"))
        self.rules.append((re.compile(r'\b\d+(\.\d+)?\b'), num_fmt))

        # Strings (single and double quoted)
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#F1FA8C"))
        self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
        self.rules.append((re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), str_fmt))

        # Comments
        cmt_fmt = QTextCharFormat()
        cmt_fmt.setForeground(QColor("#6272A4"))
        cmt_fmt.setFontItalic(True)
        self.rules.append((re.compile(r'#.*$'), cmt_fmt))

        # Decorators
        dec_fmt = QTextCharFormat()
        dec_fmt.setForeground(QColor("#FFB86C"))
        self.rules.append((re.compile(r'@\w+'), dec_fmt))

        # Function definitions
        fn_fmt = QTextCharFormat()
        fn_fmt.setForeground(QColor("#50FA7B"))
        fn_fmt.setFontWeight(QFont.Bold)
        self.rules.append((re.compile(r'\bdef\s+(\w+)'), fn_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                start = m.start()
                length = m.end() - start
                self.setFormat(start, length, fmt)


# ============================================================================
# Main window
# ============================================================================
class CalculationsWindow(QWidget):
    """Calculations tab: edit user Python scripts that run pre/post MPC."""

    config_changed = Signal()

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.runner: CalculationRunner = engine.calc_runner
        self._current_calc: Calculation = None
        self._dirty = False

        self._build()
        self._refresh_list()
        self._refresh_var_browser()

        # Live state polling timer
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._refresh_live_state)
        self._poll_timer.start(500)  # 2 Hz update

    # ------------------------------------------------------------------
    def set_engine(self, engine):
        """Rebind to a new SimEngine (e.g., after optimizer Apply rebuilt it).

        The new engine has a fresh CalculationRunner with calcs reloaded from
        cfg.calculations. We refresh the list and var browser to match.
        """
        self.engine = engine
        self.runner = engine.calc_runner
        self._current_calc = None
        # Sync the master enable toggles to the new runner state
        self.input_chk.blockSignals(True)
        self.output_chk.blockSignals(True)
        self.input_chk.setChecked(self.runner.input_enabled)
        self.output_chk.setChecked(self.runner.output_enabled)
        self.input_chk.blockSignals(False)
        self.output_chk.blockSignals(False)
        self._refresh_list()
        self._refresh_var_browser()
        self.editor.blockSignals(True)
        self.editor.clear()
        self.editor.blockSignals(False)
        self._dirty = False

    # ------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Header bar with master enable toggles ──
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("Calculations")
        title.setStyleSheet("font-size: 14pt; font-weight: 600; color: #1A1A1A;")
        header.addWidget(title)

        intro = QLabel(
            "  Python scripts that run before and after the MPC each cycle. "
            "Full Python -- use classes, methods, imports, numpy.")
        intro.setStyleSheet("color: #707070; font-size: 9pt;")
        header.addWidget(intro)

        header.addStretch()

        self.input_chk = QCheckBox("Input Calc Processing")
        self.input_chk.setChecked(self.runner.input_enabled)
        self.input_chk.setStyleSheet(
            "QCheckBox { font-weight: 600; font-size: 9pt; color: #1A1A1A; padding: 4px 8px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }")
        self.input_chk.toggled.connect(self._on_input_toggle)
        header.addWidget(self.input_chk)

        self.output_chk = QCheckBox("Output Calc Processing")
        self.output_chk.setChecked(self.runner.output_enabled)
        self.output_chk.setStyleSheet(
            "QCheckBox { font-weight: 600; font-size: 9pt; color: #1A1A1A; padding: 4px 8px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }")
        self.output_chk.toggled.connect(self._on_output_toggle)
        header.addWidget(self.output_chk)

        root.addLayout(header)

        # ── Top splitter: list (left) | editor (right) ──
        top_split = QSplitter(Qt.Horizontal)
        top_split.setStyleSheet(
            "QSplitter::handle { background: #B0B0B0; }"
            "QSplitter::handle:hover { background: #909090; }")

        # ── Calculation List ──
        list_box = QGroupBox("Calculation List")
        list_box.setStyleSheet(_GROUP_STYLE)
        list_lay = QVBoxLayout(list_box)
        list_lay.setContentsMargins(8, 16, 8, 8)
        list_lay.setSpacing(4)

        self.list_table = QTableWidget()
        self.list_table.setStyleSheet(_TABLE_STYLE)
        self.list_table.setColumnCount(5)
        self.list_table.setHorizontalHeaderLabels(
            ["#", "Type", "Name", "Status", "Description"])
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.list_table.setSelectionMode(QTableWidget.SingleSelection)
        self.list_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.list_table.itemSelectionChanged.connect(self._on_select)
        list_lay.addWidget(self.list_table, 1)

        # List actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        add_in_btn = QPushButton("+ Input")
        add_in_btn.setStyleSheet(self._btn_style("#2E8B57"))
        add_in_btn.clicked.connect(lambda: self._add_calc(True))
        btn_row.addWidget(add_in_btn)

        add_out_btn = QPushButton("+ Output")
        add_out_btn.setStyleSheet(self._btn_style("#1565C0"))
        add_out_btn.clicked.connect(lambda: self._add_calc(False))
        btn_row.addWidget(add_out_btn)

        del_btn = QPushButton("- Delete")
        del_btn.setStyleSheet(self._btn_style("#C0392B"))
        del_btn.clicked.connect(self._delete_calc)
        btn_row.addWidget(del_btn)

        up_btn = QPushButton("\u2191")
        up_btn.setStyleSheet(self._btn_style("#707070"))
        up_btn.setFixedWidth(30)
        up_btn.clicked.connect(lambda: self._reorder(-1))
        btn_row.addWidget(up_btn)

        down_btn = QPushButton("\u2193")
        down_btn.setStyleSheet(self._btn_style("#707070"))
        down_btn.setFixedWidth(30)
        down_btn.clicked.connect(lambda: self._reorder(+1))
        btn_row.addWidget(down_btn)

        btn_row.addStretch()
        list_lay.addLayout(btn_row)
        top_split.addWidget(list_box)

        # ── Editor ──
        ed_box = QGroupBox("Code Editor")
        ed_box.setStyleSheet(_GROUP_STYLE)
        ed_lay = QVBoxLayout(ed_box)
        ed_lay.setContentsMargins(8, 16, 8, 8)
        ed_lay.setSpacing(4)

        # Header line: name + dirty indicator
        ed_hdr = QHBoxLayout()
        self.calc_name_lbl = QLabel("(no calculation selected)")
        self.calc_name_lbl.setStyleSheet(
            "font-size: 10pt; font-weight: 600; color: #1A1A1A;")
        ed_hdr.addWidget(self.calc_name_lbl)

        ed_hdr.addStretch()

        self.dirty_lbl = QLabel("")
        self.dirty_lbl.setStyleSheet("font-size: 8pt; color: #C0392B; font-weight: 600;")
        ed_hdr.addWidget(self.dirty_lbl)

        ed_lay.addLayout(ed_hdr)

        # Editor
        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet(_EDITOR_STYLE)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setTabStopDistance(28)
        self.editor.textChanged.connect(self._on_text_changed)
        self.highlighter = PythonHighlighter(self.editor.document())
        ed_lay.addWidget(self.editor, 1)

        # Action row
        act_row = QHBoxLayout()
        apply_btn = QPushButton("Apply (Ctrl+S)")
        apply_btn.setStyleSheet(self._btn_style("#2E8B57"))
        apply_btn.clicked.connect(self._apply_current)
        act_row.addWidget(apply_btn)

        test_btn = QPushButton("\u25B6 Test Run")
        test_btn.setStyleSheet(self._btn_style("#0066CC"))
        test_btn.clicked.connect(self._test_current)
        act_row.addWidget(test_btn)

        reset_btn = QPushButton("Reset State")
        reset_btn.setStyleSheet(self._btn_style("#707070"))
        reset_btn.clicked.connect(self._reset_state)
        act_row.addWidget(reset_btn)

        act_row.addStretch()

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(
            "font-size: 8pt; font-family: Consolas, monospace; padding: 2px 8px;")
        act_row.addWidget(self.status_lbl)

        ed_lay.addLayout(act_row)
        top_split.addWidget(ed_box)
        top_split.setSizes([400, 700])

        # ── Bottom splitter: variable browser | live state | activity log ──
        bot_split = QSplitter(Qt.Horizontal)

        # Variable browser
        var_box = QGroupBox("Variables Browser")
        var_box.setStyleSheet(_GROUP_STYLE)
        var_lay = QVBoxLayout(var_box)
        var_lay.setContentsMargins(8, 16, 8, 8)
        self.var_tree = QTreeWidget()
        self.var_tree.setHeaderLabel("Click to insert at cursor")
        self.var_tree.setStyleSheet(
            "QTreeWidget { background: white; border: 1px solid #B0B0B0; "
            "font-size: 8pt; font-family: Consolas, monospace; }"
            "QHeaderView::section { background: #E4E4E4; padding: 4px; "
            "font-weight: 600; font-size: 8pt; }")
        self.var_tree.itemDoubleClicked.connect(self._insert_var)
        var_lay.addWidget(self.var_tree)
        bot_split.addWidget(var_box)

        # Live state
        live_box = QGroupBox("Live State")
        live_box.setStyleSheet(_GROUP_STYLE)
        live_lay = QVBoxLayout(live_box)
        live_lay.setContentsMargins(8, 16, 8, 8)
        self.live_table = QTableWidget()
        self.live_table.setStyleSheet(_TABLE_STYLE)
        self.live_table.setColumnCount(3)
        self.live_table.setHorizontalHeaderLabels(["Variable", "Value", "Source"])
        self.live_table.verticalHeader().setVisible(False)
        self.live_table.setEditTriggers(QTableWidget.NoEditTriggers)
        live_lay.addWidget(self.live_table)
        bot_split.addWidget(live_box)

        # Activity log
        log_box = QGroupBox("Activity Log")
        log_box.setStyleSheet(_GROUP_STYLE)
        log_lay = QVBoxLayout(log_box)
        log_lay.setContentsMargins(8, 16, 8, 8)
        self.log_table = QTableWidget()
        self.log_table.setStyleSheet(_TABLE_STYLE)
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["Time", "Level", "Message"])
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        log_lay.addWidget(self.log_table)
        bot_split.addWidget(log_box)

        bot_split.setSizes([300, 450, 450])

        # Main vertical splitter
        v_split = QSplitter(Qt.Vertical)
        v_split.setStyleSheet(top_split.styleSheet())
        v_split.addWidget(top_split)
        v_split.addWidget(bot_split)
        v_split.setSizes([500, 300])
        root.addWidget(v_split, 1)

        # Ctrl+S = Apply
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._apply_current)
        QShortcut(QKeySequence("F5"), self, activated=self._test_current)

    def _btn_style(self, color):
        return f"""
        QPushButton {{
            background: {color}; color: white; border: none;
            border-radius: 3px; padding: 6px 14px;
            font-size: 9pt; font-weight: 600;
        }}
        QPushButton:hover {{ background: #0066CC; }}
        """

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------
    def _refresh_list(self):
        all_calcs = self.runner.all_calcs()
        self.list_table.setRowCount(len(all_calcs))
        for r, calc in enumerate(all_calcs):
            seq_item = QTableWidgetItem(str(r + 1))
            seq_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.list_table.setItem(r, 0, seq_item)

            type_item = QTableWidgetItem("Input" if calc.is_input else "Output")
            type_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            if calc.is_input:
                type_item.setForeground(QColor("#2E8B57"))
            else:
                type_item.setForeground(QColor("#1565C0"))
            self.list_table.setItem(r, 1, type_item)

            name_item = QTableWidgetItem(calc.name)
            if not calc.enabled:
                f = name_item.font()
                f.setStrikeOut(True)
                name_item.setFont(f)
                name_item.setForeground(QColor("#999999"))
            self.list_table.setItem(r, 2, name_item)

            status_item = QTableWidgetItem(self._status_text(calc))
            status_item.setForeground(self._status_color(calc))
            status_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.list_table.setItem(r, 3, status_item)

            desc_item = QTableWidgetItem(calc.description)
            self.list_table.setItem(r, 4, desc_item)

        self.list_table.resizeColumnsToContents()
        self.list_table.horizontalHeader().setStretchLastSection(True)

    def _status_text(self, calc):
        if not calc.enabled:
            return "OFF"
        if calc.last_status == "OK":
            return f"\u2713 {calc.last_time_ms:.1f}ms"
        if calc.last_status == "ERROR":
            return "\u26A0 ERR"
        if calc.last_status == "WARN":
            return "\u26A0 WARN"
        return calc.last_status

    def _status_color(self, calc):
        if not calc.enabled:
            return QColor("#999999")
        return {
            "OK": QColor("#2E8B57"),
            "ERROR": QColor("#C0392B"),
            "WARN": QColor("#FF8C00"),
            "READY": QColor("#707070"),
        }.get(calc.last_status, QColor("#000000"))

    def _on_select(self):
        rows = self.list_table.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        all_calcs = self.runner.all_calcs()
        if idx < len(all_calcs):
            self._current_calc = all_calcs[idx]
            self._load_into_editor(self._current_calc)

    def _load_into_editor(self, calc):
        self.calc_name_lbl.setText(
            f"{'Input' if calc.is_input else 'Output'}: {calc.name}")
        self.editor.blockSignals(True)
        self.editor.setPlainText(calc.code)
        self.editor.blockSignals(False)
        self._dirty = False
        self.dirty_lbl.setText("")
        self._show_status(calc)

    def _show_status(self, calc):
        if calc.last_status == "OK":
            self.status_lbl.setText(
                f"\u2713 OK   ran {calc.run_count}x   "
                f"last: {calc.last_time_ms:.2f}ms")
            self.status_lbl.setStyleSheet(
                "font-size: 8pt; font-family: Consolas, monospace; "
                "color: #2E8B57; padding: 2px 8px;")
        elif calc.last_status == "ERROR":
            self.status_lbl.setText(f"\u26A0 {calc.last_error}")
            self.status_lbl.setStyleSheet(
                "font-size: 8pt; font-family: Consolas, monospace; "
                "color: #C0392B; padding: 2px 8px;")
        else:
            self.status_lbl.setText("ready")
            self.status_lbl.setStyleSheet(
                "font-size: 8pt; font-family: Consolas, monospace; "
                "color: #707070; padding: 2px 8px;")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def _add_calc(self, is_input):
        name, ok = QInputDialog.getText(
            self, "New Calculation",
            f"{'Input' if is_input else 'Output'} calculation name:")
        if not ok or not name.strip():
            return
        template = (
            f"# {'Input' if is_input else 'Output'} calculation: {name}\n"
            f"# Available: cvs, mvs, dvs, user, t, cycle, dt, engine, np, math, log\n"
            f"#\n"
            f"# You can use full Python: classes, functions, imports.\n"
            f"# Define a `run()` function (called every cycle) and optionally\n"
            f"# an `init()` function (called once on Apply).\n"
            f"\n"
            f"def run():\n"
            f"    pass\n"
        )
        calc = Calculation(name=name.strip(), code=template, is_input=is_input)
        if is_input:
            self.runner.add_input(calc)
        else:
            self.runner.add_output(calc)
        self.runner.compile(calc)
        self._refresh_list()
        # Select the new calc
        all_calcs = self.runner.all_calcs()
        if calc in all_calcs:
            r = all_calcs.index(calc)
            self.list_table.selectRow(r)
        self.config_changed.emit()

    def _delete_calc(self):
        if self._current_calc is None:
            return
        confirm = QMessageBox.question(
            self, "Delete Calculation",
            f"Delete '{self._current_calc.name}'?")
        if confirm != QMessageBox.Yes:
            return
        self.runner.remove(self._current_calc)
        self._current_calc = None
        self.editor.clear()
        self.calc_name_lbl.setText("(no calculation selected)")
        self._refresh_list()
        self.config_changed.emit()

    def _reorder(self, direction):
        if self._current_calc is None:
            return
        self.runner.reorder(self._current_calc, direction)
        self._refresh_list()
        # Re-select
        all_calcs = self.runner.all_calcs()
        if self._current_calc in all_calcs:
            self.list_table.selectRow(all_calcs.index(self._current_calc))
        self.config_changed.emit()

    # ------------------------------------------------------------------
    # Editor / Apply / Test
    # ------------------------------------------------------------------
    def _on_text_changed(self):
        if self._current_calc is None:
            return
        self._dirty = True
        self.dirty_lbl.setText("\u25CF UNSAVED")

    def _apply_current(self):
        if self._current_calc is None:
            return
        new_code = self.editor.toPlainText()
        self._current_calc.code = new_code
        # Re-enable in case it was auto-disabled
        if self._current_calc.last_status == "ERROR":
            self._current_calc.last_status = "READY"
        ok, err = self.runner.compile(self._current_calc)
        if not ok:
            self.status_lbl.setText(f"\u26A0 Compile failed: {err}")
            self.status_lbl.setStyleSheet(
                "font-size: 8pt; font-family: Consolas, monospace; "
                "color: #C0392B; padding: 2px 8px;")
            self.runner._log("error", f"{self._current_calc.name}: {err}")
        else:
            self._dirty = False
            self.dirty_lbl.setText("")
            self.status_lbl.setText("\u2713 Compiled OK")
            self.status_lbl.setStyleSheet(
                "font-size: 8pt; font-family: Consolas, monospace; "
                "color: #2E8B57; padding: 2px 8px;")
            self.runner._log("info", f"{self._current_calc.name}: applied")
        self._refresh_list()
        self.config_changed.emit()

    def _test_current(self):
        if self._current_calc is None:
            return
        # Apply pending edits first
        if self._dirty:
            self._apply_current()
            if self._current_calc.last_status == "ERROR":
                return
        ok, msg = self.runner.test_run(self._current_calc)
        if ok:
            self.status_lbl.setText(f"\u2713 Test {msg}")
            self.status_lbl.setStyleSheet(
                "font-size: 8pt; font-family: Consolas, monospace; "
                "color: #2E8B57; padding: 2px 8px;")
        else:
            self.status_lbl.setText(f"\u26A0 Test failed: {msg}")
            self.status_lbl.setStyleSheet(
                "font-size: 8pt; font-family: Consolas, monospace; "
                "color: #C0392B; padding: 2px 8px;")
        self._refresh_list()

    def _reset_state(self):
        self.runner.reset_state()
        self.runner._log("info", "user state cleared")

    # ------------------------------------------------------------------
    # Master toggles
    # ------------------------------------------------------------------
    def _on_input_toggle(self, checked):
        self.runner.input_enabled = checked
        self.runner._log("info",
                         f"Input calc processing {'enabled' if checked else 'DISABLED'}")

    def _on_output_toggle(self, checked):
        self.runner.output_enabled = checked
        self.runner._log("info",
                         f"Output calc processing {'enabled' if checked else 'DISABLED'}")

    # ------------------------------------------------------------------
    # Variables Browser
    # ------------------------------------------------------------------
    def _refresh_var_browser(self):
        self.var_tree.clear()
        cfg = self.engine.cfg

        mv_root = QTreeWidgetItem(self.var_tree, [f"\u25BC MVs ({len(cfg.mvs)})"])
        for mv in cfg.mvs:
            QTreeWidgetItem(mv_root, [f'mvs["{mv.tag}"]'])
        mv_root.setExpanded(True)

        cv_root = QTreeWidgetItem(self.var_tree, [f"\u25BC CVs ({len(cfg.cvs)})"])
        for cv in cfg.cvs:
            QTreeWidgetItem(cv_root, [f'cvs["{cv.tag}"]'])
        cv_root.setExpanded(True)

        if cfg.dvs:
            dv_root = QTreeWidgetItem(self.var_tree, [f"\u25BC DVs ({len(cfg.dvs)})"])
            for dv in cfg.dvs:
                QTreeWidgetItem(dv_root, [f'dvs["{dv.tag}"]'])
            dv_root.setExpanded(True)

        # Special namespace items
        special = QTreeWidgetItem(self.var_tree, ["\u25BC Runtime"])
        for n in ["user", "t", "cycle", "dt", "engine", "np", "math", "log"]:
            QTreeWidgetItem(special, [n])
        special.setExpanded(False)

        # CV/MV attributes hint
        attrs = QTreeWidgetItem(self.var_tree, ["\u25BC Attributes"])
        QTreeWidgetItem(attrs, [".value"])
        QTreeWidgetItem(attrs, [".setpoint"])
        QTreeWidgetItem(attrs, [".weight"])
        QTreeWidgetItem(attrs, [".concern_lo"])
        QTreeWidgetItem(attrs, [".concern_hi"])
        QTreeWidgetItem(attrs, [".move_suppress"])
        QTreeWidgetItem(attrs, [".cost"])
        QTreeWidgetItem(attrs, [".rate_limit"])
        QTreeWidgetItem(attrs, [".limits.operating_lo"])
        QTreeWidgetItem(attrs, [".limits.operating_hi"])
        attrs.setExpanded(False)

    def _insert_var(self, item, _col):
        if item.childCount() > 0:
            return  # parent node, not a leaf
        text = item.text(0)
        cursor = self.editor.textCursor()
        cursor.insertText(text)
        self.editor.setFocus()

    # ------------------------------------------------------------------
    # Live state polling
    # ------------------------------------------------------------------
    def _refresh_live_state(self):
        items = self.runner.get_live_state()
        # Limit to first 200 to keep the UI snappy
        items = items[:200]
        self.live_table.setRowCount(len(items))
        for r, (name, val, src) in enumerate(items):
            n = QTableWidgetItem(name)
            n.setFlags(n.flags() & ~Qt.ItemIsEditable)
            self.live_table.setItem(r, 0, n)

            v = QTableWidgetItem(val)
            v.setFlags(v.flags() & ~Qt.ItemIsEditable)
            v.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.live_table.setItem(r, 1, v)

            s = QTableWidgetItem(src)
            s.setFlags(s.flags() & ~Qt.ItemIsEditable)
            s.setForeground(QColor("#707070"))
            self.live_table.setItem(r, 2, s)
        self.live_table.resizeColumnsToContents()
        self.live_table.horizontalHeader().setStretchLastSection(True)

        # Refresh activity log
        log = list(self.runner.activity)[-50:]
        self.log_table.setRowCount(len(log))
        for r, (ts, level, msg) in enumerate(log):
            ts_item = QTableWidgetItem(ts)
            ts_item.setFlags(ts_item.flags() & ~Qt.ItemIsEditable)
            ts_item.setForeground(QColor("#707070"))
            self.log_table.setItem(r, 0, ts_item)

            lvl_item = QTableWidgetItem(level.upper())
            lvl_item.setFlags(lvl_item.flags() & ~Qt.ItemIsEditable)
            lvl_color = {
                "info": QColor("#0066CC"),
                "ok": QColor("#2E8B57"),
                "warn": QColor("#FF8C00"),
                "error": QColor("#C0392B"),
            }.get(level, QColor("#000000"))
            lvl_item.setForeground(lvl_color)
            self.log_table.setItem(r, 1, lvl_item)

            msg_item = QTableWidgetItem(msg)
            msg_item.setFlags(msg_item.flags() & ~Qt.ItemIsEditable)
            self.log_table.setItem(r, 2, msg_item)
        self.log_table.resizeColumnsToContents()
        self.log_table.horizontalHeader().setStretchLastSection(True)
        if self.log_table.rowCount():
            self.log_table.scrollToBottom()

        # Refresh list status (the per-calc OK/ERR cells)
        self._refresh_list_status_only()

    def _refresh_list_status_only(self):
        all_calcs = self.runner.all_calcs()
        for r, calc in enumerate(all_calcs):
            if r >= self.list_table.rowCount():
                break
            it = self.list_table.item(r, 3)
            if it is not None:
                it.setText(self._status_text(calc))
                it.setForeground(self._status_color(calc))

    def refresh(self):
        self._refresh_list()
        self._refresh_var_browser()
        self._refresh_live_state()
