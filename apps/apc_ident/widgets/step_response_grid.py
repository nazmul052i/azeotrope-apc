"""Step-response matrix grid widget.

Lifted from the original ``step_ident_app.py`` prototype with the
following changes:

  * Layout: rows = CV (output), columns = MV (input). The original's
    docstring claimed the opposite but the actual indexing matched
    this convention; we just made the docs match.
  * Imports point at the new shared library (`azeoapc.identification`)
    and the apc_ident theme module instead of the in-file palette.
  * Header label is updated via ``set_status`` so the parent tab can
    show "no model loaded" / per-trial labels without re-implementing
    the rendering loop.

The widget is purely a renderer -- it does not own any state. The
parent tab calls ``plot_result(ident_result, mv_names, cv_names, dt)``
each time a new identification finishes.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from azeoapc.identification import IdentResult

from ..theme import SILVER, TRACE_COLORS


class StepResponseGrid(QWidget):
    """A scrollable grid of pyqtgraph plots, one cell per (CV, MV) pair.

    Each cell shows:
      * Cumulative step response S(k) as a solid trace
      * 95% confidence band (shaded fill between cumulative CI)
      * Zero reference line
      * Steady-state gain K annotated near the final coefficient

    Layout: row = CV (output), column = MV (input). The corner cell
    (row 0, col 0) is intentionally blank; the top row carries MV tag
    headers and the leftmost column carries CV tag headers.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._header = QLabel("STEP RESPONSE MATRIX")
        self._header.setAlignment(Qt.AlignCenter)
        self._header.setStyleSheet(
            f"color: {SILVER['text_secondary']}; font-size: 9pt;"
            f" font-weight: 600; letter-spacing: 1px; padding: 6px;"
        )
        root.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {SILVER['bg_primary']};"
            f" border: 1px solid {SILVER['border']}; }}")
        root.addWidget(self._scroll, 1)

        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(2)
        self._scroll.setWidget(self._container)

        self._plots: List[pg.PlotWidget] = []

    # ------------------------------------------------------------------
    def set_status(self, text: str):
        """Update the heading text (e.g. 'No model loaded')."""
        self._header.setText(text)

    # ------------------------------------------------------------------
    def clear_plots(self):
        for pw in self._plots:
            pw.setParent(None)
            pw.deleteLater()
        self._plots.clear()
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ------------------------------------------------------------------
    def plot_result(
        self,
        result: IdentResult,
        mv_names: List[str],
        cv_names: List[str],
        dt: float,
    ):
        """Render a fresh grid for the given identification result."""
        self.clear_plots()
        ny = result.ny
        nu = result.nu
        n = result.n_coeff

        step = result.step
        ci_lo_step = self._cumsum_list(result.confidence_lo)
        ci_hi_step = self._cumsum_list(result.confidence_hi)

        t = np.arange(n) * dt

        # Top row: MV (column) headers
        for j in range(nu):
            name = mv_names[j] if j < len(mv_names) else f"MV{j}"
            lbl = QLabel(f"  {name}")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {SILVER['accent_blue']}; font-weight: 700;"
                f" font-size: 10pt; padding: 4px;")
            self._grid.addWidget(lbl, 0, j + 1)

        # Left column: CV (row) headers
        for i in range(ny):
            name = cv_names[i] if i < len(cv_names) else f"CV{i}"
            lbl = QLabel(f"{name}  ")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet(
                f"color: {SILVER['accent_green']}; font-weight: 700;"
                f" font-size: 10pt; padding: 4px;")
            self._grid.addWidget(lbl, i + 1, 0)

        # Plot cells
        for i in range(ny):       # CV row
            for j in range(nu):   # MV column
                pw = pg.PlotWidget()
                pw.setBackground(SILVER["plot_bg"])
                pw.setMinimumSize(220, 160)
                pw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

                ax_color = SILVER["plot_axis"]
                for axis_name in ("left", "bottom"):
                    ax = pw.getAxis(axis_name)
                    ax.setPen(pg.mkPen(ax_color, width=1))
                    ax.setTextPen(pg.mkPen(ax_color))
                    ax.setStyle(tickFont=QFont("Segoe UI", 8))
                pw.showGrid(x=True, y=True, alpha=0.15)

                s = np.array([step[k][i, j] for k in range(n)])
                lo = np.array([ci_lo_step[k][i, j] for k in range(n)])
                hi = np.array([ci_hi_step[k][i, j] for k in range(n)])

                color_idx = (i * nu + j) % len(TRACE_COLORS)
                trace_color = QColor(TRACE_COLORS[color_idx])

                fill_color = QColor(trace_color)
                fill_color.setAlpha(30)
                pw.addItem(pg.FillBetweenItem(
                    pg.PlotDataItem(t, lo, pen=pg.mkPen(None)),
                    pg.PlotDataItem(t, hi, pen=pg.mkPen(None)),
                    brush=fill_color,
                ))

                pw.plot(
                    t, s,
                    pen=pg.mkPen(trace_color, width=2),
                    antialias=True,
                )

                pw.addItem(pg.InfiniteLine(
                    pos=0, angle=0,
                    pen=pg.mkPen(SILVER["text_muted"], width=1,
                                  style=Qt.DashLine),
                ))

                gain = float(s[-1]) if len(s) > 0 else 0.0
                gain_text = pg.TextItem(
                    f"K={gain:+.4g}",
                    color=SILVER["text_secondary"],
                    anchor=(1, 0),
                )
                gain_text.setFont(QFont("Segoe UI", 9))
                gain_text.setPos(t[-1], gain)
                pw.addItem(gain_text)

                self._grid.addWidget(pw, i + 1, j + 1)
                self._plots.append(pw)

        self._header.setText(
            f"STEP RESPONSE MATRIX  -  {nu} MV \u00d7 {ny} CV  |  "
            f"N={n}  dt={dt:g}s  ({n * dt:.0f}s horizon)"
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _cumsum_list(fir_list: List[np.ndarray]) -> List[np.ndarray]:
        result = []
        acc = np.zeros_like(fir_list[0])
        for g in fir_list:
            acc = acc + g
            result.append(acc.copy())
        return result
