"""Azeotrope APC -- canonical "DeltaV Live Silver" theme.

Single source of truth for the visual identity of the entire stack.
Every Python app in apps/ pulls its palette and stylesheet from here
so a colour change ripples to all five studios and consoles in one
place.

The look is the actual Emerson DeltaV Live operator-workstation
chrome: a LIGHT silver-gray background, dark near-black text,
restrained borders, a deep procedural blue (~#0066CC) for selections
and interactive accents, and ISA-101-style status colours (green for
good / orange for warn / red for alarm). It is intentionally NOT a
dark theme -- DeltaV Live operator screens have always been light.

Public surface:

    SILVER         -- the colour palette dict (DeltaV Live Silver)
    TRACE_COLORS   -- distinct trace colours for plot grids
    GLOBAL_QSS     -- the application-level Qt stylesheet
    apply_theme()  -- convenience: app.setStyleSheet(GLOBAL_QSS)
    css_variables_block() -- emit ":root { --apc-bg: ... }" for HTML/CSS apps

Naming convention:

    bg_*           -- background colours, lighter = primary surface
    text_*         -- text colours, primary > secondary > muted
    border         -- separators / panel edges
    accent_*       -- semantic accents (blue=interactive, green=ok,
                      orange=warn, red=alarm, cyan=info, purple=alt)
    plot_*         -- plot-specific overrides (background, grid, axis)

The palette is intentionally one flat dict so it round-trips through
JSON / CSS / Qt stylesheet templates without an enum dance.
"""
from __future__ import annotations

from typing import Dict, Iterable


# ---------------------------------------------------------------------------
# Palette -- DeltaV Live Silver (light operator workstation chrome)
# ---------------------------------------------------------------------------
SILVER: Dict[str, str] = {
    # Backgrounds (lighter is the primary canvas)
    "bg_primary":     "#ECECEC",   # main app canvas (matches DV Live silver)
    "bg_secondary":   "#F5F5F5",   # panels, table fill
    "bg_panel":       "#E4E4E4",   # nested panel surface
    "bg_input":       "#FFFFFF",   # text fields, combos, plot canvas inset
    "bg_header":      "#D8D8D8",   # menu bar, table headers, button face
    # Borders
    "border":         "#B0B0B0",
    "border_accent":  "#909090",
    # Text (primary -> muted)
    "text_primary":   "#1A1A1A",
    "text_secondary": "#404040",
    "text_muted":     "#707070",
    # Semantic accents -- DeltaV Live uses a deep procedural blue and
    # ISA-101-style status colours (green/orange/red kept restrained)
    "accent_blue":    "#0066CC",   # selection, primary interactive
    "accent_green":   "#2E8B57",   # OK / RUNNING / on-control
    "accent_orange":  "#D9822B",   # WARN / paused
    "accent_red":     "#C0392B",   # ALARM / error
    "accent_cyan":    "#0099B0",   # info / tag highlight
    "accent_purple":  "#7A4FB7",   # alternate accent
    # Plot canvas (light background, soft grid)
    "plot_bg":        "#FFFFFF",
    "plot_grid":      "#D8D8D8",
    "plot_axis":      "#606060",
}


# Distinct trace colours for the step-response grid + per-CV trends.
# Picked to be visually separable on the white plot canvas of a
# DeltaV Live operator screen. Avoid pale yellows that disappear.
TRACE_COLORS = (
    "#0066CC",  # blue
    "#2E8B57",  # green
    "#D9822B",  # orange
    "#C0392B",  # red
    "#7A4FB7",  # purple
    "#0099B0",  # teal
    "#B8860B",  # dark gold
    "#C71585",  # magenta
    "#5F8B00",  # olive
    "#1E5BAA",  # navy
    "#A0522D",  # sienna
    "#4B0082",  # indigo
)


# ---------------------------------------------------------------------------
# Global Qt stylesheet
# ---------------------------------------------------------------------------
GLOBAL_QSS = f"""
QMainWindow, QDialog, QWidget {{
    background-color: {SILVER['bg_primary']};
    color: {SILVER['text_primary']};
    font-family: 'Segoe UI', 'Roboto', 'SF Pro Display', sans-serif;
    font-size: 9pt;
}}

QToolTip {{
    background-color: {SILVER['bg_secondary']};
    color: {SILVER['text_primary']};
    border: 1px solid {SILVER['border']};
}}

/* ── Menu bar + drop-downs ───────────────────────────────────────── */
QMenuBar {{
    background-color: {SILVER['bg_header']};
    color: {SILVER['text_primary']};
    border-bottom: 1px solid {SILVER['border']};
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 12px;
}}
QMenuBar::item:selected {{
    background-color: {SILVER['accent_blue']};
    color: #FFFFFF;
}}
QMenu {{
    background-color: {SILVER['bg_secondary']};
    color: {SILVER['text_primary']};
    border: 1px solid {SILVER['border']};
}}
QMenu::item {{ padding: 5px 22px; }}
QMenu::item:selected {{
    background-color: {SILVER['accent_blue']};
    color: #FFFFFF;
}}
QMenu::separator {{
    background: {SILVER['border']};
    height: 1px;
    margin: 4px 8px;
}}

/* ── Tab widget (used by every studio) ───────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {SILVER['border']};
    background-color: {SILVER['bg_primary']};
}}
QTabBar::tab {{
    background-color: {SILVER['bg_header']};
    color: {SILVER['text_secondary']};
    padding: 8px 22px;
    border: 1px solid {SILVER['border']};
    border-bottom: none;
    font-weight: 600;
    min-width: 110px;
}}
QTabBar::tab:selected {{
    background-color: {SILVER['bg_primary']};
    color: {SILVER['accent_blue']};
    border-bottom: 2px solid {SILVER['accent_blue']};
}}
QTabBar::tab:hover:!selected {{
    background-color: {SILVER['bg_panel']};
    color: {SILVER['text_primary']};
}}

/* ── Group boxes ─────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {SILVER['bg_secondary']};
    border: 1px solid {SILVER['border']};
    border-radius: 3px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
    color: {SILVER['text_secondary']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {SILVER['accent_blue']};
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

/* ── Buttons ─────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {SILVER['bg_header']};
    border: 1px solid {SILVER['border']};
    border-radius: 2px;
    padding: 5px 14px;
    color: {SILVER['text_primary']};
    font-weight: 500;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: {SILVER['bg_panel']};
    border-color: {SILVER['accent_blue']};
}}
QPushButton:pressed {{
    background-color: {SILVER['accent_blue']};
    color: #FFFFFF;
}}
QPushButton:checked {{
    background-color: {SILVER['accent_blue']};
    color: #FFFFFF;
    border-color: {SILVER['accent_blue']};
}}
QPushButton:disabled {{
    background-color: {SILVER['bg_secondary']};
    color: {SILVER['text_muted']};
    border-color: {SILVER['border']};
}}

/* ── Form inputs ─────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {SILVER['bg_input']};
    color: {SILVER['text_primary']};
    border: 1px solid {SILVER['border']};
    border-radius: 2px;
    padding: 4px 6px;
    selection-background-color: {SILVER['accent_blue']};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {SILVER['accent_blue']};
}}
QLineEdit:read-only {{
    background-color: {SILVER['bg_secondary']};
    color: {SILVER['text_secondary']};
}}
QComboBox QAbstractItemView {{
    background-color: {SILVER['bg_input']};
    color: {SILVER['text_primary']};
    border: 1px solid {SILVER['border']};
    selection-background-color: {SILVER['accent_blue']};
    selection-color: #FFFFFF;
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}

QCheckBox {{
    color: {SILVER['text_primary']};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {SILVER['border']};
    border-radius: 2px;
    background-color: {SILVER['bg_input']};
}}
QCheckBox::indicator:checked {{
    background-color: {SILVER['accent_blue']};
    border-color: {SILVER['accent_blue']};
}}

QRadioButton {{
    color: {SILVER['text_primary']};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 13px;
    height: 13px;
    border: 1px solid {SILVER['border']};
    border-radius: 7px;
    background-color: {SILVER['bg_input']};
}}
QRadioButton::indicator:checked {{
    background-color: {SILVER['accent_blue']};
    border-color: {SILVER['accent_blue']};
}}

/* ── Tables ──────────────────────────────────────────────────────── */
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {{
    background-color: {SILVER['bg_input']};
    alternate-background-color: {SILVER['bg_secondary']};
    color: {SILVER['text_primary']};
    gridline-color: {SILVER['border']};
    border: 1px solid {SILVER['border']};
    selection-background-color: {SILVER['accent_blue']};
    selection-color: #FFFFFF;
}}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; }}
QHeaderView::section {{
    background-color: {SILVER['bg_header']};
    color: {SILVER['text_secondary']};
    border: none;
    border-right: 1px solid {SILVER['border']};
    border-bottom: 1px solid {SILVER['border']};
    padding: 5px 8px;
    font-weight: 600;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

/* ── Status bar + scroll bars ────────────────────────────────────── */
QStatusBar {{
    background-color: {SILVER['bg_header']};
    color: {SILVER['text_secondary']};
    border-top: 1px solid {SILVER['border']};
}}
QStatusBar::item {{ border: none; }}

QScrollBar:vertical {{
    background: {SILVER['bg_secondary']};
    width: 12px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {SILVER['border']};
    min-height: 30px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical:hover {{ background: {SILVER['border_accent']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {SILVER['bg_secondary']};
    height: 12px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {SILVER['border']};
    min-width: 30px;
    border-radius: 6px;
}}
QScrollBar::handle:horizontal:hover {{ background: {SILVER['border_accent']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── Splitter handles ────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {SILVER['border']};
}}
QSplitter::handle:hover {{
    background-color: {SILVER['border_accent']};
}}

/* ── Progress bar ────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {SILVER['bg_input']};
    border: 1px solid {SILVER['border']};
    border-radius: 2px;
    text-align: center;
    color: {SILVER['text_primary']};
    height: 18px;
}}
QProgressBar::chunk {{
    background-color: {SILVER['accent_blue']};
    border-radius: 1px;
}}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def apply_theme(qapplication) -> None:
    """Install the global stylesheet on a ``QApplication`` instance.

    Apps just call ``apply_theme(app)`` after constructing their
    ``QApplication`` and every widget downstream picks up the
    DeltaV Live Silver chrome automatically.
    """
    qapplication.setStyleSheet(GLOBAL_QSS)


def color(name: str) -> str:
    """Look up a palette colour by name. Raises KeyError if missing."""
    return SILVER[name]


def css_variables_block(prefix: str = "--apc") -> str:
    """Render the palette as a ``:root { --apc-bg-primary: ... }`` block.

    Used by the apc_manager build to generate ``static/manager.css``
    from the same palette the Qt apps use, so the web console matches
    the desktop chrome without manual sync.
    """
    lines = [":root {"]
    for key, value in SILVER.items():
        css_key = f"{prefix}-{key.replace('_', '-')}"
        lines.append(f"    {css_key}: {value};")
    lines.append("}")
    return "\n".join(lines)


def palette_keys() -> Iterable[str]:
    return SILVER.keys()
