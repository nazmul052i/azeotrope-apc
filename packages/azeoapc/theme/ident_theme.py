"""ISA-101 Silver Theme for APC Ident -- brushed-aluminum industrial look.

Light silver backgrounds with white plot canvases. Follows the ISA-101
information priority hierarchy and uses gain-strength coloring for
step response matrix cells.

Plot backgrounds are WHITE (not dark) so engineers can print directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class IdentTheme:
    """Complete ISA-101 Silver theme for the identification studio."""

    # ── Backgrounds (brushed aluminum progression) ──
    BG_WINDOW: str = "#E0E2EB"       # main window canvas
    BG_PANEL: str = "#EBECF1"        # panels, dialogs
    BG_TOOLBAR: str = "#D0D2DB"      # toolbar, header
    BG_INSET: str = "#DBDBE0"        # recessed areas
    BG_INPUT: str = "#F5F6FA"        # text fields
    BG_SIDEBAR: str = "#2B3544"      # dark sidebar for contrast
    BG_SIDEBAR_HOVER: str = "#3A4A5E"
    BG_SIDEBAR_ACTIVE: str = "#1E4A8A"

    # ── Chrome (metallic accents) ──
    CHROME_LIGHT: str = "#F0F2F6"
    CHROME_MID: str = "#C8CDD8"
    CHROME_DARK: str = "#8A92A8"
    CHROME_BORDER: str = "#9AA5B4"

    # ── Text ──
    TEXT_PRIMARY: str = "#1A1C24"
    TEXT_SECONDARY: str = "#4A5068"
    TEXT_DISABLED: str = "#9AA5B4"
    TEXT_ON_ACCENT: str = "#FFFFFF"
    TEXT_ON_SIDEBAR: str = "#C8D0DC"
    TEXT_ON_SIDEBAR_ACTIVE: str = "#FFFFFF"

    # ── Accent (ISA blue) ──
    ACCENT: str = "#2B5EA7"
    ACCENT_HOVER: str = "#3A72C0"
    ACCENT_PRESSED: str = "#1E4A8A"
    ACCENT_LIGHT: str = "#E3ECF7"   # for selected list items

    # ── ISA-101 process colors ──
    PV_BLUE: str = "#3C6291"
    SP_TAN: str = "#CDC2B6"
    OUT_TEAL: str = "#14696A"

    # ── Status indicators ──
    STATUS_OK: str = "#2D8E3C"
    STATUS_WARN: str = "#D4930D"
    STATUS_ERROR: str = "#C0392B"
    STATUS_INFO: str = "#2B5EA7"

    # ── Plot (WHITE backgrounds for printing) ──
    PLOT_BG: str = "#FFFFFF"
    PLOT_GRID: str = "#E0E0E0"
    PLOT_AXIS: str = "#4A5068"

    # ── Gain-strength coloring (for step response matrix) ──
    GAIN_POS_STRONG: str = "#1B7A3D"    # dark green (large positive)
    GAIN_POS_MEDIUM: str = "#4CAF50"    # medium green
    GAIN_POS_WEAK: str = "#A5D6A7"      # light green (small positive)
    GAIN_NEG_STRONG: str = "#C62828"    # dark red (large negative)
    GAIN_NEG_MEDIUM: str = "#EF5350"    # medium red
    GAIN_NEG_WEAK: str = "#EF9A9A"      # light red (small negative)
    GAIN_ZERO: str = "#E0E0E0"          # near-zero gain (gray)

    # ── Wizard step indicators ──
    STEP_DONE: str = "#2D8E3C"
    STEP_CURRENT: str = "#2B5EA7"
    STEP_PENDING: str = "#9AA5B4"

    def gain_color(self, gain: float, max_gain: float) -> str:
        """Return a color based on gain sign and relative magnitude."""
        if max_gain < 1e-15:
            return self.GAIN_ZERO
        ratio = abs(gain) / max_gain
        if abs(gain) < 1e-10 * max_gain:
            return self.GAIN_ZERO
        if gain > 0:
            if ratio > 0.6:
                return self.GAIN_POS_STRONG
            elif ratio > 0.2:
                return self.GAIN_POS_MEDIUM
            else:
                return self.GAIN_POS_WEAK
        else:
            if ratio > 0.6:
                return self.GAIN_NEG_STRONG
            elif ratio > 0.2:
                return self.GAIN_NEG_MEDIUM
            else:
                return self.GAIN_NEG_WEAK

    def gain_bg_color(self, gain: float, max_gain: float) -> str:
        """Return a subtle background color for table cells based on gain."""
        if max_gain < 1e-15:
            return "#F5F5F5"
        ratio = abs(gain) / max_gain
        if abs(gain) < 1e-10 * max_gain:
            return "#F5F5F5"
        if gain > 0:
            alpha = min(int(40 + 80 * ratio), 120)
            return f"rgba(45, 142, 60, {alpha})"
        else:
            alpha = min(int(40 + 80 * ratio), 120)
            return f"rgba(192, 57, 43, {alpha})"


# Singleton
THEME = IdentTheme()

# ISA-101 trend palette (distinct, printable on white)
TREND_COLORS = (
    "#3C6291",  # PV blue
    "#14696A",  # teal
    "#C0392B",  # red
    "#2D8E3C",  # green
    "#8E44AD",  # purple
    "#D4930D",  # amber
    "#1A5276",  # navy
    "#C44569",  # rose
    "#27AE60",  # emerald
    "#2980B9",  # sky
    "#E67E22",  # orange
    "#7D3C98",  # violet
)

# Workflow steps for the sidebar
WORKFLOW_STEPS = [
    {"id": "data",    "icon": "\u25A4", "label": "Data",           "tip": "Load & condition step-test data"},
    {"id": "tags",    "icon": "\u2630", "label": "Tags",           "tip": "Assign MV / CV / DV roles"},
    {"id": "ident",   "icon": "\u2699", "label": "Identify",       "tip": "Configure & run identification"},
    {"id": "results", "icon": "\u25A0", "label": "Results",        "tip": "Inspect step response, curve ops, assembly"},
    {"id": "analysis","icon": "\u25C8", "label": "Analysis",       "tip": "Cross-correlation, uncertainty, gain matrix"},
    {"id": "validate","icon": "\u2713", "label": "Validate",       "tip": "Compare model against test data"},
]


def get_qss() -> str:
    """Generate the complete Qt stylesheet for APC Ident."""
    t = THEME
    return f"""
    /* ═══════════════════════════════════════════════════════
       APC Ident — ISA-101 Silver Industrial Theme
       ═══════════════════════════════════════════════════════ */

    * {{
        font-family: "Segoe UI", "Tahoma", sans-serif;
        font-size: 9pt;
    }}

    QMainWindow {{
        background-color: {t.BG_WINDOW};
    }}

    QWidget {{
        background-color: {t.BG_PANEL};
        color: {t.TEXT_PRIMARY};
    }}

    /* ── Menu Bar ── */
    QMenuBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {t.CHROME_LIGHT}, stop:1 {t.BG_TOOLBAR});
        color: {t.TEXT_PRIMARY};
        border-bottom: 1px solid {t.CHROME_BORDER};
        padding: 2px 0;
    }}
    QMenuBar::item {{
        padding: 4px 10px;
        background: transparent;
    }}
    QMenuBar::item:selected {{
        background: {t.CHROME_MID};
        border-radius: 3px;
    }}
    QMenu {{
        background: {t.BG_PANEL};
        color: {t.TEXT_PRIMARY};
        border: 1px solid {t.CHROME_BORDER};
    }}
    QMenu::item {{
        padding: 5px 28px 5px 12px;
    }}
    QMenu::item:selected {{
        background: {t.ACCENT};
        color: {t.TEXT_ON_ACCENT};
    }}
    QMenu::separator {{
        height: 1px;
        background: {t.CHROME_MID};
        margin: 4px 8px;
    }}

    /* ── Push Buttons ── */
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {t.CHROME_LIGHT}, stop:1 {t.BG_TOOLBAR});
        border: 1px solid {t.CHROME_BORDER};
        border-radius: 3px;
        padding: 5px 16px;
        color: {t.TEXT_PRIMARY};
        min-height: 20px;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #FFFFFF, stop:1 {t.CHROME_LIGHT});
        border-color: {t.ACCENT};
    }}
    QPushButton:pressed {{
        background: {t.BG_INSET};
    }}
    QPushButton:disabled {{
        color: {t.TEXT_DISABLED};
        background: {t.BG_PANEL};
        border-color: {t.CHROME_MID};
    }}

    /* ── Inputs ── */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {t.BG_INPUT};
        border: 1px solid {t.CHROME_BORDER};
        border-radius: 2px;
        padding: 3px 6px;
        color: {t.TEXT_PRIMARY};
        selection-background-color: {t.ACCENT};
        selection-color: {t.TEXT_ON_ACCENT};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {t.ACCENT};
    }}
    QComboBox::drop-down {{
        border-left: 1px solid {t.CHROME_BORDER};
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background: {t.BG_INPUT};
        border: 1px solid {t.CHROME_BORDER};
        selection-background-color: {t.ACCENT};
        selection-color: {t.TEXT_ON_ACCENT};
    }}

    /* ── Tab Widget (for sub-tabs inside panels) ── */
    QTabWidget::pane {{
        border: 1px solid {t.CHROME_BORDER};
        background: {t.BG_PANEL};
    }}
    QTabBar::tab {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {t.CHROME_LIGHT}, stop:1 {t.BG_TOOLBAR});
        border: 1px solid {t.CHROME_BORDER};
        border-bottom: none;
        padding: 5px 14px;
        margin-right: 1px;
        border-top-left-radius: 3px;
        border-top-right-radius: 3px;
        color: {t.TEXT_SECONDARY};
    }}
    QTabBar::tab:selected {{
        background: {t.BG_PANEL};
        border-bottom: 1px solid {t.BG_PANEL};
        color: {t.TEXT_PRIMARY};
        font-weight: bold;
    }}
    QTabBar::tab:hover:!selected {{
        background: {t.CHROME_LIGHT};
    }}

    /* ── Splitter ── */
    QSplitter::handle {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {t.CHROME_MID}, stop:0.5 {t.CHROME_LIGHT},
            stop:1 {t.CHROME_MID});
    }}
    QSplitter::handle:horizontal {{ width: 4px; }}
    QSplitter::handle:vertical {{ height: 4px; }}

    /* ── Tables ── */
    QTableWidget, QTableView {{
        background: {t.BG_INPUT};
        border: 1px solid {t.CHROME_BORDER};
        alternate-background-color: {t.BG_PANEL};
        selection-background-color: {t.ACCENT};
        selection-color: {t.TEXT_ON_ACCENT};
        gridline-color: {t.CHROME_MID};
    }}
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {t.CHROME_LIGHT}, stop:1 {t.BG_TOOLBAR});
        border: 1px solid {t.CHROME_BORDER};
        padding: 4px;
        color: {t.TEXT_PRIMARY};
        font-weight: 600;
    }}

    /* ── Scroll Bars ── */
    QScrollBar:vertical {{
        background: {t.BG_INSET};
        width: 12px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {t.CHROME_MID};
        border-radius: 4px;
        min-height: 24px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t.CHROME_DARK};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: {t.BG_INSET};
        height: 12px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {t.CHROME_MID};
        border-radius: 4px;
        min-width: 24px;
        margin: 2px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* ── Status Bar ── */
    QStatusBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {t.BG_TOOLBAR}, stop:1 {t.CHROME_MID});
        color: {t.TEXT_SECONDARY};
        border-top: 1px solid {t.CHROME_BORDER};
        font-size: 8pt;
    }}

    /* ── Group Box ── */
    QGroupBox {{
        border: 1px solid {t.CHROME_BORDER};
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 12px;
        background: {t.BG_PANEL};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: {t.TEXT_SECONDARY};
        font-weight: 600;
        letter-spacing: 0.5px;
    }}

    /* ── Text Editors ── */
    QTextBrowser, QTextEdit, QPlainTextEdit {{
        background: {t.BG_INPUT};
        color: {t.TEXT_PRIMARY};
        border: 1px solid {t.CHROME_BORDER};
        font-family: "Consolas", "Courier New", monospace;
    }}

    /* ── Progress Bar ── */
    QProgressBar {{
        background: {t.BG_INSET};
        border: 1px solid {t.CHROME_BORDER};
        border-radius: 3px;
        text-align: center;
        color: {t.TEXT_PRIMARY};
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {t.ACCENT}, stop:1 {t.ACCENT_HOVER});
        border-radius: 2px;
    }}

    /* ── CheckBox / Radio ── */
    QCheckBox, QRadioButton {{
        spacing: 6px;
        color: {t.TEXT_PRIMARY};
    }}

    /* ── Label ── */
    QLabel {{
        color: {t.TEXT_PRIMARY};
        background: transparent;
    }}

    /* ── Tooltips ── */
    QToolTip {{
        background: #E8EBF0;
        color: {t.TEXT_PRIMARY};
        border: 1px solid {t.CHROME_BORDER};
        border-radius: 3px;
        padding: 6px 8px;
    }}

    /* ── Slider ── */
    QSlider::groove:horizontal {{
        background: {t.CHROME_MID};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {t.ACCENT};
        width: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}
    """
