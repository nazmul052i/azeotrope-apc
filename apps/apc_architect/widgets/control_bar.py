"""Compact control panel matching mpc-tools-casadi style."""
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QPushButton, QLabel)
from PySide6.QtCore import Signal


class ControlBar(QFrame):
    """Compact top bar: sim name + Run/Pause/Step/Reset + loop mode + status."""

    run_toggled = Signal(bool)
    loop_toggled = Signal(bool)
    step_clicked = Signal()
    reset_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("QFrame { background: #E0E0E0; border-bottom: 1px solid #B0B0B0; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(4)

        # Sim name (left)
        self.sim_label = QLabel("")
        self.sim_label.setStyleSheet("font-weight: bold; font-size: 9pt;")
        lay.addWidget(self.sim_label)

        lay.addSpacing(12)

        # Run / Pause
        self.run_btn = QPushButton("Run")
        self.run_btn.setCheckable(True)
        self.run_btn.setFixedWidth(55)
        self.run_btn.toggled.connect(self._on_run)
        lay.addWidget(self.run_btn)

        # Step
        btn = QPushButton("Step")
        btn.setFixedWidth(45)
        btn.clicked.connect(self.step_clicked)
        lay.addWidget(btn)

        # Reset
        btn = QPushButton("Reset")
        btn.setFixedWidth(50)
        btn.clicked.connect(self.reset_clicked)
        lay.addWidget(btn)

        lay.addSpacing(8)

        # Open / Closed loop
        self.loop_btn = QPushButton("Closed")
        self.loop_btn.setObjectName("loopBtn")
        self.loop_btn.setCheckable(True)
        self.loop_btn.setChecked(True)
        self.loop_btn.setFixedWidth(60)
        self.loop_btn.toggled.connect(self._on_loop)
        lay.addWidget(self.loop_btn)

        lay.addStretch()

        # Status
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 8pt; color: #444; font-family: Consolas, monospace;")
        lay.addWidget(self.status_lbl)

    def set_sim_title(self, t):
        self.sim_label.setText(t)

    def _on_run(self, on):
        self.run_btn.setText("Pause" if on else "Run")
        self.run_toggled.emit(on)

    def _on_loop(self, on):
        self.loop_btn.setText("Closed" if on else "Open")
        self.loop_toggled.emit(on)

    def update_status(self, cycle, l1, l2, tot, ok=True):
        s = f"Cycle: {cycle}   L2: {l2:.1f}ms   L1: {l1:.1f}ms   Total: {tot:.1f}ms"
        if not ok:
            s += "   WARN"
        self.status_lbl.setText(s)
