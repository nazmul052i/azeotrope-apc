"""apc_ident theme -- thin shim that re-exports the canonical palette.

The real palette + stylesheet now lives in ``packages/azeoapc/theme``
so every app in the stack shares one visual identity (DeltaV Live
Silver). This module exists only so existing imports
``from apc_ident.theme import SILVER, STYLESHEET, TRACE_COLORS`` keep
working.
"""
from azeoapc.theme import (
    GLOBAL_QSS as STYLESHEET,
    SILVER,
    TRACE_COLORS,
    apply_theme,
    color,
    css_variables_block,
)

__all__ = [
    "SILVER", "STYLESHEET", "TRACE_COLORS",
    "apply_theme", "color", "css_variables_block",
]
