"""SVG diagram generator for APC Architect help.

Architect-specific diagrams: controller structure, tuning, deployment.
Reuses the ISA-101 Silver color constants from the ident diagrams.
"""
from __future__ import annotations

# Colors
_BG = "#F5F6FA"
_BORDER = "#9AA5B4"
_ACCENT = "#2B5EA7"
_GREEN = "#2D8E3C"
_ORANGE = "#D4930D"
_RED = "#C0392B"
_TEXT = "#1A1C24"
_TEXT_LIGHT = "#4A5068"
_TEAL = "#14696A"
_PURPLE = "#7D3C98"
_CHROME = "#C8CDD8"
_WHITE = "#FFFFFF"


def _box(x, y, w, h, label, color=_ACCENT, text_color=_WHITE,
         rx=6, font_size=11, sublabel=""):
    lines = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{color}" stroke="{_BORDER}" stroke-width="1"/>',
        f'<text x="{x+w//2}" y="{y+h//2+4}" text-anchor="middle" '
        f'fill="{text_color}" font-size="{font_size}" font-weight="600" '
        f'font-family="Segoe UI, sans-serif">{label}</text>',
    ]
    if sublabel:
        lines.append(
            f'<text x="{x+w//2}" y="{y+h//2+18}" text-anchor="middle" '
            f'fill="{text_color}" font-size="9" font-family="Segoe UI">'
            f'{sublabel}</text>')
    return "\n".join(lines)


def _arrow(x1, y1, x2, y2, label="", color=_TEXT_LIGHT):
    mid_x, mid_y = (x1+x2)//2, (y1+y2)//2
    lines = [
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" stroke-width="1.5" marker-end="url(#ah)"/>']
    if label:
        lines.append(
            f'<text x="{mid_x}" y="{mid_y-6}" text-anchor="middle" '
            f'fill="{_TEXT_LIGHT}" font-size="9" font-family="Segoe UI">{label}</text>')
    return "\n".join(lines)


def _svg(content, w, h):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"
     width="{w}" height="{h}" style="background:{_BG};border-radius:8px;border:1px solid {_CHROME};">
  <defs><marker id="ah" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
    <polygon points="0 0,10 3.5,0 7" fill="{_TEXT_LIGHT}"/></marker></defs>
  {content}</svg>'''


def diagram_architect_workflow() -> str:
    """Architect 5-step workflow."""
    e = []
    e.append(f'<text x="400" y="22" text-anchor="middle" fill="{_TEXT}" '
             f'font-size="14" font-weight="bold" font-family="Segoe UI">'
             f'APC Architect Workflow</text>')
    steps = [
        ("Import\nModel", _TEXT_LIGHT),
        ("Configure\nVariables", _ACCENT),
        ("Tune\nOptimizer", _TEAL),
        ("Simulate\nWhat-If", _ORANGE),
        ("Deploy\nOPC UA", _GREEN),
    ]
    for i, (label, color) in enumerate(steps):
        x = 30 + i * 155
        lines = label.split("\n")
        e.append(_box(x, 40, 130, 50, lines[0], color=color,
                       sublabel=lines[1] if len(lines) > 1 else ""))
        if i < len(steps) - 1:
            e.append(_arrow(x+130, 65, x+155, 65))
    return _svg("\n".join(e), 810, 110)


def diagram_constraint_priorities() -> str:
    """P1-P5 constraint priority pyramid."""
    e = []
    e.append(f'<text x="300" y="22" text-anchor="middle" fill="{_TEXT}" '
             f'font-size="14" font-weight="bold" font-family="Segoe UI">'
             f'Constraint Priority Levels</text>')
    levels = [
        ("P1", "MV Hard Limits", _RED, "Valve 0-100%, never violated"),
        ("P2", "MV Rate Limits", _ORANGE, "Max move per step"),
        ("P3", "CV Safety Limits", _ORANGE, "Trip / interlock points"),
        ("P4", "CV Operating Limits", _TEAL, "Normal operating range"),
        ("P5", "Setpoint Tracking", _ACCENT, "Minimize deviation"),
    ]
    for i, (p, name, color, desc) in enumerate(levels):
        y = 35 + i * 42
        w = 460 - i * 30
        x = 70 + i * 15
        e.append(_box(x, y, w, 34, f"{p}: {name}", color=color, font_size=10))
        e.append(f'<text x="{x+w+10}" y="{y+22}" fill="{_TEXT_LIGHT}" '
                 f'font-size="8" font-family="Segoe UI">{desc}</text>')
    e.append(f'<text x="300" y="255" text-anchor="middle" fill="{_TEXT_LIGHT}" '
             f'font-size="9" font-family="Segoe UI">'
             f'← Higher priority relaxed LAST | Lower priority relaxed FIRST →</text>')
    return _svg("\n".join(e), 700, 270)


def diagram_qp_formulation() -> str:
    """Layer 1 QP formulation."""
    e = []
    e.append(f'<text x="350" y="22" text-anchor="middle" fill="{_TEXT}" '
             f'font-size="14" font-weight="bold" font-family="Segoe UI">'
             f'Layer 1: Dynamic QP Formulation</text>')

    # Objective
    e.append(_box(30, 40, 660, 35, "minimize:  J = ‖y_pred − y_target‖²Q  +  ‖Δu‖²R",
                  color=_WHITE, text_color=_ACCENT, font_size=11))

    # Prediction
    e.append(_box(30, 85, 660, 30, "prediction:  y_pred = y_free + A_dyn · Δu",
                  color=_WHITE, text_color=_TEAL, font_size=10))

    # Constraints
    constraints = [
        "Δu_min ≤ Δu ≤ Δu_max        (P2: move size limits)",
        "u_min ≤ u + C·Δu ≤ u_max     (P1: absolute MV limits)",
        "y_min ≤ y_pred ≤ y_max         (P3/P4: CV limits, soft)",
    ]
    for i, c in enumerate(constraints):
        y = 125 + i * 25
        e.append(f'<text x="50" y="{y}" fill="{_TEXT}" font-size="9" '
                 f'font-family="Consolas">{c}</text>')

    # Key variables
    e.append(f'<text x="50" y="215" fill="{_TEXT_LIGHT}" font-size="9" '
             f'font-family="Segoe UI">A_dyn = dynamic matrix (Toeplitz from step response)  '
             f'|  Q = CV weight  |  R = move suppression</text>')

    return _svg("\n".join(e), 720, 235)


def diagram_feedback_filters() -> str:
    """Feedback filter types."""
    e = []
    e.append(f'<text x="350" y="22" text-anchor="middle" fill="{_TEXT}" '
             f'font-size="14" font-weight="bold" font-family="Segoe UI">'
             f'Feedback Filter Types</text>')

    filters = [
        ("Full Feedback", _GREEN, "Fastest correction.\nUse for clean, reliable\nmeasurements."),
        ("First Order", _ACCENT, "Smoothed correction.\nUse for noisy signals\nor analyzer data."),
        ("Moving Average", _ORANGE, "Averaged correction.\nUse for intermittent\nor batch-sampled."),
    ]
    for i, (name, color, desc) in enumerate(filters):
        x = 30 + i * 240
        e.append(_box(x, 40, 210, 40, name, color=color))
        lines = desc.split("\n")
        for j, line in enumerate(lines):
            e.append(f'<text x="{x+105}" y="{95+j*14}" text-anchor="middle" '
                     f'fill="{_TEXT_LIGHT}" font-size="9" font-family="Segoe UI">{line}</text>')

    return _svg("\n".join(e), 740, 145)


def diagram_deployment() -> str:
    """OPC UA deployment architecture."""
    e = []
    e.append(f'<text x="350" y="22" text-anchor="middle" fill="{_TEXT}" '
             f'font-size="14" font-weight="bold" font-family="Segoe UI">'
             f'Deployment Architecture</text>')

    e.append(_box(30, 40, 140, 45, "DCS / PLC", color=_TEXT_LIGHT, sublabel="Process I/O"))
    e.append(_arrow(170, 62, 210, 62, "OPC UA"))
    e.append(_box(210, 40, 160, 45, "APC Runtime", color=_ACCENT, sublabel="MPC Engine"))
    e.append(_arrow(370, 62, 410, 62, "IO Tags"))
    e.append(_box(410, 40, 140, 45, "Historian", color=_TEAL, sublabel="Data Storage"))

    # Monitoring
    e.append(_arrow(290, 85, 290, 110))
    e.append(_box(210, 110, 160, 40, "INCA Viewer /\nAPC Monitor", color=_ORANGE, font_size=9))

    return _svg("\n".join(e), 600, 165)


def diagram_simulation_loop() -> str:
    """What-If simulator execution loop."""
    e = []
    e.append(f'<text x="350" y="22" text-anchor="middle" fill="{_TEXT}" '
             f'font-size="14" font-weight="bold" font-family="Segoe UI">'
             f'Simulation Execution Cycle</text>')

    steps = [
        ("Read\nPlant Output", _TEXT_LIGHT),
        ("Input\nCalculations", _PURPLE),
        ("Run MPC\n(L1+L2+L3)", _ACCENT),
        ("Output\nCalculations", _PURPLE),
        ("Apply Moves\nto Plant", _GREEN),
        ("Step Plant\nModel", _TEAL),
    ]
    for i, (label, color) in enumerate(steps):
        x = 15 + i * 118
        lines = label.split("\n")
        e.append(_box(x, 40, 105, 48, lines[0], color=color,
                       sublabel=lines[1] if len(lines) > 1 else "",
                       font_size=9))
        if i < len(steps) - 1:
            e.append(_arrow(x+105, 64, x+118, 64))

    # Loop-back arrow
    e.append(f'<path d="M 720 64 L 740 64 L 740 100 L 15 100 L 15 88" '
             f'stroke="{_ORANGE}" stroke-width="1.5" fill="none" '
             f'stroke-dasharray="4,3" marker-end="url(#ah)"/>')
    e.append(f'<text x="370" y="112" text-anchor="middle" fill="{_ORANGE}" '
             f'font-size="9" font-family="Segoe UI">repeat every sample period</text>')

    return _svg("\n".join(e), 760, 125)


DIAGRAMS = {
    "architect_workflow": diagram_architect_workflow,
    "constraint_priorities": diagram_constraint_priorities,
    "qp_formulation": diagram_qp_formulation,
    "feedback_filters": diagram_feedback_filters,
    "deployment": diagram_deployment,
    "simulation_loop": diagram_simulation_loop,
}


def get_diagram(name: str) -> str:
    func = DIAGRAMS.get(name)
    return func() if func else ""
