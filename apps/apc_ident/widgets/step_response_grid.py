"""Step-response matrix grid widget with multi-model overlay support.

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
  * **Multi-model overlay**: call ``overlay_model()`` to add additional
    models on top of the primary plot (e.g. compare FIR vs subspace,
    or different trial parameters). Each overlay uses a distinct color
    and dashed line style. Curve operation indicators show which cells
    have been modified.

The widget is purely a renderer -- it does not own any state. The
parent tab calls ``plot_result(ident_result, mv_names, cv_names, dt)``
each time a new identification finishes.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from azeoapc.identification import IdentResult
from azeoapc.theme.ident_theme import THEME

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
        *,
        typical_moves: Optional[List[float]] = None,
    ):
        """Render a fresh grid for the given identification result.

        DMC3 convention:
          * **Rows**    = MV/DV (inputs).  Left-most column shows the
            MV tag name + typical move size.
          * **Columns** = CV (outputs).  Top header row shows CV tags.

        If ``typical_moves`` is provided (one float per MV), the step
        response and gain annotation are scaled to show the response
        per *typical move* rather than per *unit step*. This is what
        Aspen's matrix view does: "if I move FCV-410 by its typical
        amount, how much does TIT-400 change?"
        """
        self.clear_plots()
        ny = result.ny
        nu = result.nu
        n = result.n_coeff

        step = result.step
        ci_lo_step = self._cumsum_list(result.confidence_lo)
        ci_hi_step = self._cumsum_list(result.confidence_hi)

        t = np.arange(n) * dt

        # Typical moves default to 1.0 (unit step) if not provided
        tm = typical_moves or [1.0] * nu

        # ── Row 0: corner cell + CV column headers ──
        corner = QLabel("MV \\ CV")
        corner.setAlignment(Qt.AlignCenter)
        corner.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 8pt;"
            f" font-weight: 600;")
        self._grid.addWidget(corner, 0, 0)

        # "Typical Move" label column header
        tm_header = QLabel("Typical\nMove")
        tm_header.setAlignment(Qt.AlignCenter)
        tm_header.setStyleSheet(
            f"color: {SILVER['text_muted']}; font-size: 8pt;"
            f" font-weight: 600;")
        self._grid.addWidget(tm_header, 0, 1)

        for j in range(ny):
            name = cv_names[j] if j < len(cv_names) else f"CV{j}"
            lbl = QLabel(f"  {name}")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {SILVER['accent_green']}; font-weight: 700;"
                f" font-size: 10pt; padding: 4px;")
            self._grid.addWidget(lbl, 0, j + 2)

        # ── Left column: MV row headers + typical move ──
        for i in range(nu):
            name = mv_names[i] if i < len(mv_names) else f"MV{i}"
            lbl = QLabel(f"{name}  ")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl.setStyleSheet(
                f"color: {SILVER['accent_blue']}; font-weight: 700;"
                f" font-size: 10pt; padding: 4px;")
            self._grid.addWidget(lbl, i + 1, 0)

            # Typical move cell
            tm_val = tm[i]
            tm_lbl = QLabel(f"{tm_val:g}")
            tm_lbl.setAlignment(Qt.AlignCenter)
            tm_lbl.setStyleSheet(
                f"color: {SILVER['text_secondary']}; font-size: 9pt;"
                f" font-family: Consolas; padding: 4px;")
            self._grid.addWidget(tm_lbl, i + 1, 1)

        # ── Compute max absolute gain for color scaling ──
        all_gains = []
        for i in range(nu):
            for j in range(ny):
                s_tmp = np.zeros(n)
                acc = 0.0
                for k in range(n):
                    acc += step[k][j, i] * tm[i]
                    s_tmp[k] = acc
                all_gains.append(abs(s_tmp[-1]) if n > 0 else 0.0)
        max_gain = max(all_gains) if all_gains else 1.0

        # ── Plot cells: row=MV, col=CV ──
        for i in range(nu):       # MV row
            for j in range(ny):   # CV column
                pw = pg.PlotWidget()
                pw.setBackground(SILVER["plot_bg"])
                pw.setMinimumSize(200, 150)
                pw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

                ax_color = SILVER["plot_axis"]
                for axis_name in ("left", "bottom"):
                    ax = pw.getAxis(axis_name)
                    ax.setPen(pg.mkPen(ax_color, width=1))
                    ax.setTextPen(pg.mkPen(ax_color))
                    ax.setStyle(tickFont=QFont("Segoe UI", 8))
                pw.showGrid(x=True, y=True, alpha=0.15)

                scale = tm[i]
                s  = np.array([step[k][j, i]         * scale for k in range(n)])
                lo = np.array([ci_lo_step[k][j, i]   * scale for k in range(n)])
                hi = np.array([ci_hi_step[k][j, i]   * scale for k in range(n)])

                # Cumulate
                s = np.cumsum(s)
                lo = np.cumsum(lo)
                hi = np.cumsum(hi)

                gain = float(s[-1]) if len(s) > 0 else 0.0

                # Color by gain sign and strength
                trace_color_str = THEME.gain_color(gain, max_gain)
                trace_color = QColor(trace_color_str)

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

                # Gain annotation with color
                gain_text = pg.TextItem(
                    f"K={gain:+.4g}",
                    color=trace_color_str,
                    anchor=(1, 0),
                )
                gain_text.setFont(QFont("Segoe UI", 9, QFont.Bold))
                gain_text.setPos(t[-1], gain)
                pw.addItem(gain_text)

                self._grid.addWidget(pw, i + 1, j + 2)   # +2 for corner + TM cols
                self._plots.append(pw)

        self._header.setText(
            f"STEP RESPONSE MATRIX  -  {nu} MV (rows) \u00d7 {ny} CV (cols)  |  "
            f"N={n}  dt={dt:g}s  ({n * dt:.0f}s horizon)"
        )

    # ------------------------------------------------------------------
    def overlay_model(
        self,
        step_response: np.ndarray,
        mv_names: List[str],
        cv_names: List[str],
        dt: float,
        label: str = "overlay",
        color_idx_offset: int = 4,
        *,
        typical_moves: Optional[List[float]] = None,
    ):
        """Overlay an additional model on the existing grid plots.

        Each overlay uses a dashed line with a color offset from the
        primary trace. Call this after ``plot_result()`` to compare
        models (e.g. FIR vs subspace, different trial parameters).

        Parameters
        ----------
        step_response : ndarray, shape (ny, n_coeff, nu)
            Cumulative step response to overlay.
        label : str
            Legend label for this overlay.
        color_idx_offset : int
            Offset into TRACE_COLORS for visual distinction.
        """
        if step_response.ndim != 3:
            return

        ny, n, nu = step_response.shape
        tm = typical_moves or [1.0] * nu
        t = np.arange(n) * dt

        plot_idx = 0
        for i in range(nu):       # MV row
            for j in range(ny):   # CV column
                if plot_idx >= len(self._plots):
                    break

                pw = self._plots[plot_idx]
                scale = tm[i] if i < len(tm) else 1.0
                s = step_response[j, :, i] * scale

                color_idx = (i * ny + j + color_idx_offset) % len(TRACE_COLORS)
                trace_color = QColor(TRACE_COLORS[color_idx])

                pw.plot(
                    t[:len(s)], s,
                    pen=pg.mkPen(trace_color, width=1.5, style=Qt.DashLine),
                    antialias=True,
                    name=label,
                )

                plot_idx += 1

        # Update header to show overlay
        current = self._header.text()
        if label not in current:
            self._header.setText(f"{current}  +  {label}")

    # ------------------------------------------------------------------
    def overlay_assembled_model(
        self,
        assembled_step: np.ndarray,
        cv_names: List[str],
        mv_names: List[str],
        dt: float,
        *,
        typical_moves: Optional[List[float]] = None,
        ops_indicators: Optional[dict] = None,
    ):
        """Overlay an assembled model with curve operation indicators.

        Parameters
        ----------
        assembled_step : ndarray, shape (ny, n_coeff, nu)
            The assembled step response.
        ops_indicators : dict, optional
            Maps (cv_idx, mv_idx) -> list of operation names. If present,
            cells with operations get a visual indicator (triangle marker).
        """
        self.overlay_model(
            assembled_step, mv_names, cv_names, dt,
            label="assembled", color_idx_offset=6,
            typical_moves=typical_moves,
        )

        # Add curve operation indicators
        if ops_indicators:
            plot_idx = 0
            ny = assembled_step.shape[0]
            nu = assembled_step.shape[2]
            for i in range(nu):
                for j in range(ny):
                    if plot_idx >= len(self._plots):
                        break
                    key = (j, i)
                    if key in ops_indicators and ops_indicators[key]:
                        pw = self._plots[plot_idx]
                        # Add blue triangle indicator in top-right
                        n_ops = len(ops_indicators[key])
                        indicator_color = (SILVER["accent_blue"]
                                          if n_ops == 1
                                          else SILVER["accent_cyan"])
                        text = pg.TextItem(
                            "\u25B2" if n_ops == 1 else "\u25B2\u25B2",
                            color=indicator_color,
                            anchor=(1, 0),
                        )
                        text.setFont(QFont("Segoe UI", 10))
                        vr = pw.viewRange()
                        text.setPos(vr[0][1] * 0.95, vr[1][1] * 0.9)
                        pw.addItem(text)
                    plot_idx += 1

    # ------------------------------------------------------------------
    @staticmethod
    def _cumsum_list(fir_list: List[np.ndarray]) -> List[np.ndarray]:
        result = []
        acc = np.zeros_like(fir_list[0])
        for g in fir_list:
            acc = acc + g
            result.append(acc.copy())
        return result
