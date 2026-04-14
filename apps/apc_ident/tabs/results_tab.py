"""Results tab -- inspect, shape curves, assemble master model, export.

Workflow (DMC3 style):
  1. Run single or multi-trial identification
  2. All trials are overlaid on the step response grid
  3. For each CV-MV cell, pick which trial to use (or keep best)
  4. Apply curve operations (SHIFT, GAIN, FIRSTORDER, etc.) per cell
  5. Build Master Model -> this becomes the export candidate
  6. Export as .apcmodel bundle
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from azeoapc.identification import (
    BUNDLE_EXT, ModelBundle, bundle_from_ident, save_model_bundle,
)
from azeoapc.identification.curve_operations import (
    CurveOp, CurveOpRecord, apply_op,
)
from azeoapc.identification.model_assembly import (
    ModelAssembler, AssembledModel,
)

from ..session import IdentSession
from ..theme import SILVER, TRACE_COLORS
from ..widgets import StepResponseGrid


def _result_to_step_array(result) -> Optional[np.ndarray]:
    """Extract (ny, n_coeff, nu) cumulative step array from any result type."""
    if hasattr(result, 'step') and isinstance(result.step, list):
        # FIR IdentResult: step is list of (ny, nu) matrices
        n = result.n_coeff
        ny, nu = result.step[0].shape
        arr = np.zeros((ny, n, nu))
        acc = np.zeros((ny, nu))
        for k in range(n):
            acc = acc + result.step[k]
            arr[:, k, :] = acc
        return arr
    elif hasattr(result, 'to_step'):
        # SubspaceResult
        step_list = result.to_step(120)
        ny, nu = step_list[0].shape
        n = len(step_list)
        arr = np.zeros((ny, n, nu))
        for k in range(n):
            arr[:, k, :] = step_list[k]
        return arr
    return None


class ResultsTab(QWidget):
    config_changed = Signal()
    bundle_exported = Signal(str)

    def __init__(self, session: IdentSession, parent=None):
        super().__init__(parent)
        self.session = session
        self._assembler: Optional[ModelAssembler] = None
        self._master: Optional[AssembledModel] = None
        # Per-cell curve operations history: (cv, mv) -> list of (op, kwargs)
        self._cell_ops: Dict[Tuple[int, int], List[Tuple[CurveOp, dict]]] = {}
        self._build()
        self._refresh_from_session()

    # ==================================================================
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_grid_panel())

        # Right side: scrollable panel
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; }}")
        scroll.setWidget(self._build_side_panel())
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([900, 400])
        root.addWidget(splitter)

    def _build_grid_panel(self):
        box = QGroupBox("STEP RESPONSE MATRIX")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(6, 16, 6, 6)
        self.grid = StepResponseGrid()
        lay.addWidget(self.grid)
        return box

    def _build_side_panel(self):
        side = QWidget()
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # ── Gain matrix ──
        gain_box = QGroupBox("GAIN MATRIX")
        gl = QVBoxLayout(gain_box)
        gl.setContentsMargins(6, 16, 6, 6)
        self.gain_table = QTableWidget()
        self.gain_table.verticalHeader().setVisible(True)
        self.gain_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.gain_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.gain_table.setMaximumHeight(160)
        gl.addWidget(self.gain_table)
        lay.addWidget(gain_box)

        # ── Channel fits ──
        fit_box = QGroupBox("CHANNEL FITS")
        fl = QVBoxLayout(fit_box)
        fl.setContentsMargins(6, 16, 6, 6)
        self.fit_table = QTableWidget()
        self.fit_table.setColumnCount(4)
        self.fit_table.setHorizontalHeaderLabels(["CV", "R\u00b2", "RMSE", "LB-p"])
        self.fit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fit_table.verticalHeader().setVisible(False)
        self.fit_table.setMaximumHeight(160)
        fl.addWidget(self.fit_table)
        lay.addWidget(fit_box)

        # ── Model Assembly (trial selection per cell) ──
        asm_box = QGroupBox("MODEL ASSEMBLY")
        al = QVBoxLayout(asm_box)
        al.setContentsMargins(6, 16, 6, 6)
        al.setSpacing(4)

        asm_hint = QLabel(
            "Pick which trial to use for each CV/MV cell.\n"
            "Run multi-trial first to see options.")
        asm_hint.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 8pt;")
        asm_hint.setWordWrap(True)
        al.addWidget(asm_hint)

        self.assembly_table = QTableWidget()
        self.assembly_table.setColumnCount(3)
        self.assembly_table.setHorizontalHeaderLabels(["CV / MV", "Trial", "Gain"])
        self.assembly_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.assembly_table.verticalHeader().setVisible(False)
        al.addWidget(self.assembly_table)

        master_row = QHBoxLayout()
        self.build_master_btn = QPushButton("Build Master Model")
        self.build_master_btn.clicked.connect(self._on_build_master)
        self.build_master_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_blue']};"
            f" color: white; font-weight: 600; padding: 8px;"
            f" border-radius: 3px; }}")
        master_row.addWidget(self.build_master_btn)

        self.master_status = QLabel("")
        self.master_status.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 8pt;")
        master_row.addWidget(self.master_status, 1)
        al.addLayout(master_row)

        lay.addWidget(asm_box)

        # ── Curve Operations ──
        ops_box = QGroupBox("CURVE OPERATIONS")
        ol = QVBoxLayout(ops_box)
        ol.setContentsMargins(6, 16, 6, 6)
        ol.setSpacing(4)

        cell_row = QHBoxLayout()
        cell_row.addWidget(QLabel("CV:"))
        self.ops_cv_combo = QComboBox()
        cell_row.addWidget(self.ops_cv_combo)
        cell_row.addWidget(QLabel("MV:"))
        self.ops_mv_combo = QComboBox()
        cell_row.addWidget(self.ops_mv_combo)
        ol.addLayout(cell_row)

        op_row = QHBoxLayout()
        op_row.addWidget(QLabel("Op:"))
        self.ops_combo = QComboBox()
        self.ops_combo.addItems([
            "SHIFT", "GAIN", "GSCALE", "FIRSTORDER", "SECONDORDER",
            "LEADLAG", "MULTIPLY", "ZERO", "UNITY",
        ])
        self.ops_combo.currentTextChanged.connect(self._on_op_changed)
        op_row.addWidget(self.ops_combo)
        ol.addLayout(op_row)

        param_form = QFormLayout()
        param_form.setSpacing(4)
        self.ops_param1 = QDoubleSpinBox()
        self.ops_param1.setRange(-10000, 10000)
        self.ops_param1.setDecimals(2)
        self.ops_param1_label = QLabel("Shift (samples):")
        param_form.addRow(self.ops_param1_label, self.ops_param1)

        self.ops_param2 = QDoubleSpinBox()
        self.ops_param2.setRange(-10000, 10000)
        self.ops_param2.setDecimals(2)
        self.ops_param2.setVisible(False)
        self.ops_param2_label = QLabel("Param 2:")
        self.ops_param2_label.setVisible(False)
        param_form.addRow(self.ops_param2_label, self.ops_param2)
        ol.addLayout(param_form)

        btn_row = QHBoxLayout()
        self.ops_apply_btn = QPushButton("Apply to Cell")
        self.ops_apply_btn.clicked.connect(self._on_apply_curve_op)
        self.ops_apply_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_blue']};"
            f" color: white; font-weight: 600; padding: 6px;"
            f" border-radius: 3px; }}")
        btn_row.addWidget(self.ops_apply_btn)

        self.ops_undo_btn = QPushButton("Undo")
        self.ops_undo_btn.clicked.connect(self._on_undo_curve_op)
        btn_row.addWidget(self.ops_undo_btn)
        ol.addLayout(btn_row)

        self.ops_status = QLabel("")
        self.ops_status.setStyleSheet(f"color: {SILVER['text_muted']}; font-size: 8pt;")
        self.ops_status.setWordWrap(True)
        ol.addWidget(self.ops_status)

        lay.addWidget(ops_box)

        # ── Export ──
        export_box = QGroupBox("EXPORT")
        el = QVBoxLayout(export_box)
        el.setContentsMargins(6, 16, 6, 6)

        self.export_btn = QPushButton("Export Model Bundle...")
        self.export_btn.setStyleSheet(
            f"QPushButton {{ background: {SILVER['accent_green']};"
            f" color: #1A1A2A; font-weight: 700; padding: 10px;"
            f" border-radius: 4px; }}"
            f"QPushButton:hover {{ background: #5BE8A0; }}"
            f"QPushButton:disabled {{ background: {SILVER['bg_secondary']};"
            f" color: {SILVER['text_muted']}; }}")
        self.export_btn.clicked.connect(self._on_export)
        el.addWidget(self.export_btn)

        self.bundle_label = QLabel("(not exported)")
        self.bundle_label.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 9pt;")
        self.bundle_label.setWordWrap(True)
        el.addWidget(self.bundle_label)

        lay.addWidget(export_box)
        lay.addStretch()
        return side

    # ==================================================================
    # Population
    # ==================================================================
    def _refresh_from_session(self):
        result = self.session.ident_result
        if result is None:
            self.grid.clear_plots()
            self.grid.set_status("No model loaded -- run identification first")
            self.gain_table.setRowCount(0)
            self.gain_table.setColumnCount(0)
            self.fit_table.setRowCount(0)
            self.assembly_table.setRowCount(0)
            self.export_btn.setEnabled(False)
            self._update_bundle_label()
            return

        mv_tags, cv_tags = self._get_tag_lists()
        dt = result.config.dt if hasattr(result, 'config') else 1.0
        self.grid.plot_result(result, mv_tags, cv_tags, dt=dt)
        self._populate_gain_table(result, mv_tags, cv_tags)
        self._populate_fit_table(result, cv_tags)
        self.export_btn.setEnabled(True)
        self._update_bundle_label()

    def _get_tag_lists(self):
        mv_tags, cv_tags = [], []
        for ta in self.session.project.tag_assignments:
            if ta.role == "MV":
                mv_tags.append(ta.controller_tag or ta.column)
            elif ta.role == "CV":
                cv_tags.append(ta.controller_tag or ta.column)
        return mv_tags, cv_tags

    def _populate_gain_table(self, result, mv_tags, cv_tags):
        gain = result.gain_matrix()
        ny, nu = gain.shape
        self.gain_table.setRowCount(ny)
        self.gain_table.setColumnCount(nu)
        self.gain_table.setHorizontalHeaderLabels(mv_tags or [f"MV{j}" for j in range(nu)])
        self.gain_table.setVerticalHeaderLabels(cv_tags or [f"CV{i}" for i in range(ny)])
        for i in range(ny):
            for j in range(nu):
                item = QTableWidgetItem(f"{gain[i,j]:+.4g}")
                item.setTextAlignment(Qt.AlignCenter)
                if gain[i, j] > 0:
                    item.setForeground(QColor(SILVER["accent_green"]))
                elif gain[i, j] < 0:
                    item.setForeground(QColor(SILVER["accent_orange"]))
                self.gain_table.setItem(i, j, item)

    def _populate_fit_table(self, result, cv_tags):
        if not hasattr(result, 'fits'):
            self.fit_table.setRowCount(0)
            return
        seen = {}
        for f in result.fits:
            seen.setdefault(f.cv_index, f)
        rows = sorted(seen.values(), key=lambda f: f.cv_index)
        self.fit_table.setRowCount(len(rows))
        for r, f in enumerate(rows):
            cv_name = cv_tags[f.cv_index] if f.cv_index < len(cv_tags) else f"CV{f.cv_index}"
            cells = [cv_name, f"{f.r_squared:+.4f}", f"{f.rmse:.4g}", f"{f.ljung_box_pvalue:.3f}"]
            for c, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignCenter)
                if c == 1:
                    if f.r_squared > 0.9:
                        item.setForeground(QColor(SILVER["accent_green"]))
                    elif f.r_squared > 0.7:
                        item.setForeground(QColor(SILVER["accent_orange"]))
                    else:
                        item.setForeground(QColor(SILVER["accent_red"]))
                if c == 3:
                    if f.ljung_box_pvalue > 0.05:
                        item.setForeground(QColor(SILVER["accent_green"]))
                    else:
                        item.setForeground(QColor(SILVER["accent_orange"]))
                self.fit_table.setItem(r, c, item)

    # ==================================================================
    # Model Assembly -- trial selection per cell
    # ==================================================================
    def _populate_assembly_table(self):
        """Build the assembly table with one row per CV-MV cell and a
        dropdown to pick which trial to use."""
        comparison = self.session.trial_comparison
        mv_tags, cv_tags = self._get_tag_lists()
        ny = len(cv_tags)
        nu = len(mv_tags)

        if comparison is None or len(comparison.trials) < 2:
            # No multi-trial -- show simple info
            self.assembly_table.setRowCount(0)
            self.master_status.setText(
                "Run multi-trial to pick curves per cell")
            return

        trial_names = [t.name for t in comparison.trials]
        best_name = comparison.best_trial or trial_names[0]

        self.assembly_table.setRowCount(ny * nu)
        self._assembly_combos: List[QComboBox] = []

        for i in range(ny):
            for j in range(nu):
                row = i * nu + j
                cv_name = cv_tags[i] if i < len(cv_tags) else f"CV{i}"
                mv_name = mv_tags[j] if j < len(mv_tags) else f"MV{j}"

                # Cell label
                label_item = QTableWidgetItem(f"{cv_name} / {mv_name}")
                label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
                self.assembly_table.setItem(row, 0, label_item)

                # Trial picker dropdown
                combo = QComboBox()
                combo.addItems(trial_names)
                combo.setCurrentText(best_name)
                combo.setProperty("cv_idx", i)
                combo.setProperty("mv_idx", j)
                self.assembly_table.setCellWidget(row, 1, combo)
                self._assembly_combos.append(combo)

                # Gain (updated when Build Master is clicked)
                gain_item = QTableWidgetItem("--")
                gain_item.setTextAlignment(Qt.AlignCenter)
                gain_item.setFlags(gain_item.flags() & ~Qt.ItemIsEditable)
                self.assembly_table.setItem(row, 2, gain_item)

        self.master_status.setText(
            f"{ny * nu} cells, {len(trial_names)} trials available")

    def _on_build_master(self):
        """Build the master model from per-cell trial selections + curve ops."""
        comparison = self.session.trial_comparison
        result = self.session.ident_result
        if result is None:
            QMessageBox.information(self, "Build Master",
                                     "Run identification first.")
            return

        mv_tags, cv_tags = self._get_tag_lists()
        ny = len(cv_tags)
        nu = len(mv_tags)
        dt = result.config.dt if hasattr(result, 'config') else 1.0
        n_coeff = result.n_coeff if hasattr(result, 'n_coeff') else 120

        assembler = ModelAssembler(
            cv_names=cv_tags, mv_names=mv_tags,
            n_coeff=n_coeff, dt=dt)

        # Register all trial candidates (or just the single result)
        if comparison and len(comparison.trials) >= 2:
            for trial in comparison.trials:
                tr = trial.ident_result
                if tr is None:
                    continue
                step_arr = _result_to_step_array(tr)
                if step_arr is not None:
                    assembler.add_candidate(
                        trial.name, step_arr,
                        fit_r2=trial.fit_r2, source="fir")
        else:
            # Single run
            step_arr = _result_to_step_array(result)
            if step_arr is not None:
                assembler.add_candidate(
                    "current", step_arr, source="fir")

        # Apply per-cell trial selections from the assembly table
        if hasattr(self, '_assembly_combos'):
            for combo in self._assembly_combos:
                cv_idx = combo.property("cv_idx")
                mv_idx = combo.property("mv_idx")
                trial_name = combo.currentText()
                if trial_name in assembler.candidates:
                    assembler.select(cv_idx, mv_idx, trial_name)

        # If no explicit selection, auto-select best
        if not any(assembler.selections[(i, j)].candidate_name
                   for i in range(ny) for j in range(nu)):
            assembler.auto_select()

        # Apply stored curve operations per cell
        for (cv_idx, mv_idx), ops_list in self._cell_ops.items():
            for op, kwargs in ops_list:
                assembler.apply_curve_op(cv_idx, mv_idx, op, **kwargs)

        # Build
        self._master = assembler.build()
        self._assembler = assembler

        # Overlay master on grid
        self.grid.overlay_assembled_model(
            self._master.step_response, cv_tags, mv_tags, dt)

        # Update gain column in assembly table
        for i in range(ny):
            for j in range(nu):
                row = i * nu + j
                if row < self.assembly_table.rowCount():
                    gain = self._master.gain_matrix[i, j]
                    item = self.assembly_table.item(row, 2)
                    if item:
                        item.setText(f"{gain:+.4g}")
                        color = SILVER["accent_green"] if gain >= 0 else SILVER["accent_orange"]
                        item.setForeground(QColor(color))

        self.master_status.setText(
            f"Master model built: {ny}x{nu}, "
            f"cond={np.linalg.cond(self._master.gain_matrix):.1f}")
        self.config_changed.emit()

    # ==================================================================
    # Curve Operations
    # ==================================================================
    def _on_op_changed(self, op_name: str):
        labels = {
            "SHIFT": ("Shift (samples):", None),
            "GAIN": ("Gain multiplier:", None),
            "GSCALE": ("Target SS gain:", None),
            "FIRSTORDER": ("Tau (seconds):", None),
            "SECONDORDER": ("Tau1 (seconds):", "Tau2 (seconds):"),
            "LEADLAG": ("Tau_lead (s):", "Tau_lag (s):"),
            "MULTIPLY": ("Scalar:", None),
            "ZERO": (None, None),
            "UNITY": (None, None),
        }
        l1, l2 = labels.get(op_name, ("Value:", None))
        self.ops_param1.setVisible(l1 is not None)
        self.ops_param1_label.setVisible(l1 is not None)
        if l1:
            self.ops_param1_label.setText(l1)
        self.ops_param2.setVisible(l2 is not None)
        self.ops_param2_label.setVisible(l2 is not None)
        if l2:
            self.ops_param2_label.setText(l2)

    def _on_apply_curve_op(self):
        """Apply curve operation to selected cell and show overlay."""
        result = self.session.ident_result
        if result is None:
            return

        cv_idx = self.ops_cv_combo.currentIndex()
        mv_idx = self.ops_mv_combo.currentIndex()
        op_name = self.ops_combo.currentText()
        if cv_idx < 0 or mv_idx < 0:
            self.ops_status.setText("Select a CV and MV")
            return

        # Get base curve for this cell
        step_arr = _result_to_step_array(result)
        if step_arr is None:
            self.ops_status.setText("Cannot extract step response")
            return

        curve = step_arr[cv_idx, :, mv_idx].copy()
        dt = result.config.dt if hasattr(result, 'config') else 1.0
        p1 = self.ops_param1.value()
        p2 = self.ops_param2.value()

        op_map = {
            "SHIFT": (CurveOp.SHIFT, {"shift": int(p1)}),
            "GAIN": (CurveOp.GAIN, {"gain": p1}),
            "GSCALE": (CurveOp.GSCALE, {"target_gain": p1}),
            "FIRSTORDER": (CurveOp.FIRSTORDER, {"tau": p1, "dt": dt}),
            "SECONDORDER": (CurveOp.SECONDORDER, {"tau1": p1, "tau2": p2, "dt": dt}),
            "LEADLAG": (CurveOp.LEADLAG, {"tau_lead": p1, "tau_lag": p2, "dt": dt}),
            "MULTIPLY": (CurveOp.MULTIPLY, {"scalar": p1}),
            "ZERO": (CurveOp.ZERO, {}),
            "UNITY": (CurveOp.UNITY, {}),
        }
        if op_name not in op_map:
            return

        op, kwargs = op_map[op_name]

        # Apply all accumulated ops for this cell + the new one
        key = (cv_idx, mv_idx)
        if key not in self._cell_ops:
            self._cell_ops[key] = []
        self._cell_ops[key].append((op, kwargs))

        # Replay all ops on the base curve
        for op_i, kw_i in self._cell_ops[key]:
            curve = apply_op(op_i, curve, **kw_i)

        # Overlay just this cell
        ny, n, nu = step_arr.shape
        overlay = np.zeros((ny, n, nu))
        overlay[cv_idx, :, mv_idx] = curve

        mv_tags, cv_tags = self._get_tag_lists()
        self.grid.overlay_model(
            overlay, mv_tags, cv_tags, dt,
            label=f"{op_name}({cv_tags[cv_idx]}/{mv_tags[mv_idx]})",
            color_idx_offset=8,
        )

        n_ops = len(self._cell_ops[key])
        self.ops_status.setText(
            f"{cv_tags[cv_idx]}/{mv_tags[mv_idx]}: {n_ops} op(s), "
            f"K={curve[-1]:+.4g}")

    def _on_undo_curve_op(self):
        """Remove the last curve operation from the selected cell."""
        cv_idx = self.ops_cv_combo.currentIndex()
        mv_idx = self.ops_mv_combo.currentIndex()
        key = (cv_idx, mv_idx)
        if key in self._cell_ops and self._cell_ops[key]:
            removed = self._cell_ops[key].pop()
            self.ops_status.setText(f"Undone: {removed[0].value}")
        else:
            self.ops_status.setText("Nothing to undo")

    def _update_ops_combos(self):
        self.ops_cv_combo.clear()
        self.ops_mv_combo.clear()
        mv_tags, cv_tags = self._get_tag_lists()
        self.ops_cv_combo.addItems(cv_tags or ["(no CVs)"])
        self.ops_mv_combo.addItems(mv_tags or ["(no MVs)"])

    # ==================================================================
    # Multi-trial overlay
    # ==================================================================
    def _overlay_trials(self):
        comparison = self.session.trial_comparison
        if comparison is None or len(comparison.trials) < 2:
            return

        best_name = comparison.best_trial
        mv_tags, cv_tags = self._get_tag_lists()
        best_result = self.session.ident_result
        if best_result is None:
            return

        dt = best_result.config.dt if hasattr(best_result, 'config') else 1.0

        for idx, trial in enumerate(comparison.trials):
            if trial.name == best_name:
                continue
            tr = trial.ident_result
            if tr is None:
                continue
            step_arr = _result_to_step_array(tr)
            if step_arr is None:
                continue

            self.grid.overlay_model(
                step_arr, mv_tags, cv_tags, dt,
                label=trial.name,
                color_idx_offset=idx + 2,
            )

    # ==================================================================
    # Export bundle
    # ==================================================================
    def _on_export(self):
        result = self.session.ident_result
        if result is None:
            return
        mv_tags, cv_tags = self._get_tag_lists()

        suggested_dir = (
            os.path.dirname(self.session.project.source_path)
            if self.session.project.source_path else os.getcwd())
        suggested_name = (
            (self.session.project.metadata.name or "untitled")
            .lower().replace(" ", "_") + BUNDLE_EXT)
        suggested = os.path.join(suggested_dir, suggested_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Model Bundle", suggested,
            f"APC Model Bundle (*{BUNDLE_EXT});;All Files (*)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += BUNDLE_EXT

        u0 = y0 = None
        if self.session.cond_result is not None:
            try:
                u0 = self.session.cond_result.u_train.mean(axis=0)
                y0 = self.session.cond_result.y_train.mean(axis=0)
            except Exception:
                pass

        try:
            bundle = bundle_from_ident(
                result,
                name=self.session.project.metadata.name or "Untitled",
                mv_tags=mv_tags, cv_tags=cv_tags,
                u0=u0, y0=y0,
                source_csv=os.path.basename(self.session.df_path or ""),
                source_project=os.path.basename(
                    self.session.project.source_path or ""),
            )
            save_model_bundle(bundle, path)
        except Exception as e:
            QMessageBox.critical(self, "Export Bundle",
                                 f"Failed:\n{type(e).__name__}: {e}")
            return

        self.session.bundle = bundle
        self.session.project.last_bundle_path = (
            os.path.relpath(path, os.path.dirname(self.session.project.source_path))
            if self.session.project.source_path else path)
        self._update_bundle_label()
        self.bundle_exported.emit(path)
        self.config_changed.emit()
        QMessageBox.information(self, "Export", f"Bundle exported:\n{path}")

    def _update_bundle_label(self):
        p = self.session.project.last_bundle_path
        if p:
            self.bundle_label.setText(f"Last export: {p}")
            self.bundle_label.setStyleSheet(
                f"color: {SILVER['accent_green']}; font-size: 9pt;")
        else:
            self.bundle_label.setText("(not exported)")
            self.bundle_label.setStyleSheet(
                f"color: {SILVER['text_muted']}; font-size: 9pt;")

    # ==================================================================
    # Public hooks
    # ==================================================================
    def on_ident_completed(self, result):
        self._cell_ops.clear()
        self._master = None
        self._refresh_from_session()
        self._overlay_trials()
        self._populate_assembly_table()
        self._update_ops_combos()

    def on_project_loaded(self):
        self._cell_ops.clear()
        self._master = None
        self._refresh_from_session()
        self._update_ops_combos()
