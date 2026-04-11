"""Strip chart trend matching mpc-tools-casadi style.

Tight, compact: y-axis label on left, plot fills width.
History left of red now line, prediction right.
"""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt
from ..theme.deltav_silver import COLORS


class TrendStrip(QWidget):
    """Compact strip chart: history + now + prediction."""

    def __init__(self, tag, name, units,
                 plot_lo, plot_hi,
                 history_len=200, forecast_len=0,
                 show_sp=False, show_limits=False,
                 sp_value=0, hi_limit=1e20, lo_limit=-1e20,
                 line_color=None, parent=None):
        super().__init__(parent)
        self.history_len = history_len
        self.forecast_len = forecast_len
        self._cur = np.nan

        self.data = np.full(history_len, np.nan)
        self.t_hist = np.arange(-history_len, 0, dtype=float)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Plot widget ──
        self.pw = pg.PlotWidget()
        self.pw.setBackground("w")
        self.pw.setYRange(plot_lo, plot_hi, padding=0.02)
        self.pw.setXRange(-history_len, max(forecast_len, 1), padding=0)
        self.pw.showGrid(x=True, y=True, alpha=0.2)
        self.pw.setMouseEnabled(x=False, y=False)
        self.pw.hideButtons()
        self.pw.setMinimumHeight(50)

        # Y-axis: show variable label
        ax_left = self.pw.getAxis("left")
        ax_left.setWidth(55)
        ax_left.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 7))
        ax_left.setLabel(f"{tag}", units=units, **{"font-size": "7pt"})

        # X-axis: hide tick labels
        ax_bot = self.pw.getAxis("bottom")
        ax_bot.setStyle(showValues=False, tickLength=-3)
        ax_bot.setHeight(10)

        # Title at top of plot area
        self.pw.setTitle(f"{name}", size="8pt", color="#333")

        # ── Limit lines (red dashed) ──
        self.hi_line = self.lo_line = None
        if show_limits:
            lp = pg.mkPen(COLORS["trend_hi"], width=1, style=Qt.DashLine)
            if hi_limit < 1e19:
                self.hi_line = self.pw.addLine(y=hi_limit, pen=lp)
            if lo_limit > -1e19:
                self.lo_line = self.pw.addLine(y=lo_limit, pen=lp)

        # ── Setpoint line (green dashed) ──
        self.sp_line = None
        if show_sp:
            self.sp_line = self.pw.addLine(
                y=sp_value, pen=pg.mkPen(COLORS["trend_sp"], width=1.5, style=Qt.DashLine))

        # ── Now line (red vertical) ──
        self.pw.addLine(x=0, pen=pg.mkPen("#CC0000", width=1.5))

        # ── History curve (black solid) ──
        c = line_color or COLORS["trend_pv"]
        self.hist_curve = self.pw.plot(self.t_hist, self.data, pen=pg.mkPen(c, width=1.5))

        # ── Prediction curve (blue solid, right of now) ──
        self.fc_curve = None
        if forecast_len > 0:
            self.fc_t = np.arange(0, forecast_len + 1, dtype=float)
            self.fc_d = np.full(forecast_len + 1, np.nan)
            self.fc_curve = self.pw.plot(
                self.fc_t, self.fc_d,
                pen=pg.mkPen(COLORS["trend_pred"], width=1.5))

        lay.addWidget(self.pw, stretch=1)

    def append_value(self, v):
        self._cur = v
        self.data = np.roll(self.data, -1)
        self.data[-1] = v
        self.hist_curve.setData(self.t_hist, self.data)

    def set_forecast(self, vals):
        if self.fc_curve is None or vals is None or len(vals) == 0:
            return
        n = min(len(vals), self.forecast_len)
        fc = np.full(self.forecast_len + 1, np.nan)
        fc[0] = self._cur  # bridge from history
        fc[1:n + 1] = vals[:n]
        self.fc_curve.setData(self.fc_t, fc)

    def set_setpoint(self, sp):
        if self.sp_line:
            self.sp_line.setValue(sp)

    def set_limits(self, lo, hi):
        if self.lo_line and lo > -1e19:
            self.lo_line.setValue(lo)
        if self.hi_line and hi < 1e19:
            self.hi_line.setValue(hi)

    def clear_data(self):
        self.data[:] = np.nan
        self._cur = np.nan
        self.hist_curve.setData(self.t_hist, self.data)
        if self.fc_curve is not None:
            self.fc_curve.setData(self.fc_t, np.full(len(self.fc_t), np.nan))
