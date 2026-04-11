"""apc_architect theme -- thin shim that re-exports the canonical palette.

The canonical DeltaV Live Silver palette + stylesheet now lives in
``packages/azeoapc/theme``. This module exists only so existing
``from .theme.deltav_silver import COLORS`` and ``QSS`` imports keep
working. The old key names (``bg``, ``panel``, ``trend_pv``, ...)
are mapped onto the canonical palette so trend plots and the
WhatIf simulator chrome stay consistent with the rest of the stack.
"""
from azeoapc.theme import GLOBAL_QSS as _QSS
from azeoapc.theme import SILVER, apply_theme as _apply_theme


# Backward-compatible key map. Existing call sites refer to short
# names like ``COLORS["bg"]`` or ``COLORS["trend_pv"]``; we route them
# onto the canonical palette so a single edit to packages/azeoapc/theme
# updates all of them.
COLORS = {
    # Surfaces
    "bg":              SILVER["bg_primary"],
    "panel":           SILVER["bg_secondary"],
    "panel_border":    SILVER["border"],
    "surface":         SILVER["bg_input"],
    "separator":       SILVER["border_accent"],
    # Text
    "text_primary":    SILVER["text_primary"],
    "text_secondary":  SILVER["text_secondary"],
    # Semantic
    "accent":          SILVER["accent_blue"],
    "danger":          SILVER["accent_red"],
    "warning":         SILVER["accent_orange"],
    "success":         SILVER["accent_green"],
    "grid":            SILVER["plot_grid"],
    # Trend traces
    "trend_pv":        SILVER["text_primary"],     # measured -- bold black
    "trend_sp":        SILVER["accent_green"],     # setpoint
    "trend_hi":        SILVER["accent_red"],       # high alarm
    "trend_lo":        SILVER["accent_red"],       # low alarm
    "trend_pred":      SILVER["accent_blue"],      # MPC prediction
    "trend_dv":        SILVER["accent_purple"],    # disturbance
}


# Re-export the canonical stylesheet so existing imports of ``QSS``
# continue to work. Apps should prefer ``apply_theme`` from the shared
# module going forward.
QSS = _QSS


def apply_theme(app):
    """Install the canonical DeltaV Live Silver stylesheet."""
    _apply_theme(app)
