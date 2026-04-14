"""apc_ident theme -- compatibility shim mapping old SILVER dict to ISA-101 theme.

All existing tabs import ``from ..theme import SILVER, TRACE_COLORS``.
This shim maps those keys to the new ISA-101 Silver theme so existing
tab code keeps working without modification.
"""
from azeoapc.theme.ident_theme import THEME, TREND_COLORS as _TC, get_qss

# Map the old SILVER dict keys to ISA-101 Silver theme values
SILVER = {
    "bg_primary":     THEME.BG_WINDOW,
    "bg_secondary":   THEME.BG_PANEL,
    "bg_panel":       THEME.BG_TOOLBAR,
    "bg_input":       THEME.BG_INPUT,
    "bg_header":      THEME.BG_TOOLBAR,
    "border":         THEME.CHROME_BORDER,
    "border_accent":  THEME.CHROME_DARK,
    "text_primary":   THEME.TEXT_PRIMARY,
    "text_secondary": THEME.TEXT_SECONDARY,
    "text_muted":     THEME.TEXT_DISABLED,
    "accent_blue":    THEME.ACCENT,
    "accent_green":   THEME.STATUS_OK,
    "accent_orange":  THEME.STATUS_WARN,
    "accent_red":     THEME.STATUS_ERROR,
    "accent_cyan":    THEME.OUT_TEAL,
    "accent_purple":  "#7D3C98",
    "plot_bg":        THEME.PLOT_BG,      # WHITE for printing
    "plot_grid":      THEME.PLOT_GRID,
    "plot_axis":      THEME.PLOT_AXIS,
}

TRACE_COLORS = _TC
STYLESHEET = get_qss()

__all__ = ["SILVER", "TRACE_COLORS", "STYLESHEET"]
