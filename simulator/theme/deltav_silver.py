"""Clean industrial simulation theme -- light background, maximum plot area."""

COLORS = {
    "bg":              "#F0F0F0",
    "panel":           "#E0E0E0",
    "panel_border":    "#C0C0C0",
    "surface":         "#FFFFFF",
    "text_primary":    "#000000",
    "text_secondary":  "#444444",
    "accent":          "#0066CC",
    "danger":          "#CC0000",
    "warning":         "#CC8800",
    "success":         "#008800",
    "grid":            "#DDDDDD",
    "trend_pv":        "#000000",
    "trend_sp":        "#008800",
    "trend_hi":        "#CC0000",
    "trend_lo":        "#CC0000",
    "trend_pred":      "#0066FF",
    "trend_dv":        "#0000CC",
    "separator":       "#AAAAAA",
}

QSS = f"""
QMainWindow {{
    background-color: {COLORS['bg']};
}}
QWidget {{
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 9pt;
    color: {COLORS['text_primary']};
}}
QMenuBar {{
    background-color: {COLORS['bg']};
    border-bottom: 1px solid {COLORS['panel_border']};
}}
QMenuBar::item:selected {{
    background-color: #0066CC;
    color: white;
}}
QMenu {{
    background-color: white;
    border: 1px solid {COLORS['panel_border']};
}}
QMenu::item:selected {{
    background-color: #0066CC;
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {COLORS['panel_border']};
    margin: 2px 8px;
}}
QPushButton {{
    background-color: {COLORS['panel']};
    border: 1px solid {COLORS['panel_border']};
    padding: 3px 10px;
    min-height: 20px;
    font-size: 8pt;
}}
QPushButton:hover {{
    background-color: #D0D0D0;
}}
QPushButton:checked {{
    background-color: #008800;
    color: white;
    border-color: #006600;
}}
QPushButton#loopBtn:checked {{
    background-color: #0066CC;
    color: white;
}}
QStatusBar {{
    background-color: {COLORS['panel']};
    border-top: 1px solid {COLORS['panel_border']};
    font-size: 8pt;
}}
QLineEdit {{
    border: 1px solid {COLORS['panel_border']};
    padding: 2px 4px;
    background: white;
}}
"""


def apply_theme(app):
    app.setStyleSheet(QSS)
