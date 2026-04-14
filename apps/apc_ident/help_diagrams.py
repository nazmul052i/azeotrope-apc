"""SVG diagram generator for built-in help.

Generates clean block diagrams, flowcharts, and signal flow diagrams
that match the ISA-101 Silver theme. Diagrams are returned as inline
SVG strings that can be embedded directly in HTML.

No external dependencies -- pure Python string generation.
"""
from __future__ import annotations


# ISA-101 Silver colors for diagrams
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
    """Rounded rectangle with centered text."""
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
    """Arrow with optional label."""
    mid_x = (x1 + x2) // 2
    mid_y = (y1 + y2) // 2
    lines = [
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" stroke-width="1.5" marker-end="url(#arrowhead)"/>',
    ]
    if label:
        lines.append(
            f'<text x="{mid_x}" y="{mid_y-6}" text-anchor="middle" '
            f'fill="{_TEXT_LIGHT}" font-size="9" '
            f'font-family="Segoe UI">{label}</text>')
    return "\n".join(lines)


def _arrow_down(x, y1, y2, label=""):
    return _arrow(x, y1, x, y2, label)


def _arrow_right(x1, x2, y, label=""):
    return _arrow(x1, y, x2, y, label)


def _svg_wrap(content: str, width: int, height: int) -> str:
    """Wrap SVG content with markers and viewBox."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"
     width="{width}" height="{height}" style="background: {_BG}; border-radius: 8px; border: 1px solid {_CHROME};">
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="{_TEXT_LIGHT}"/>
    </marker>
  </defs>
  {content}
</svg>'''


# =====================================================================
# Diagram: Three-Layer MPC Architecture
# =====================================================================
def diagram_three_layer() -> str:
    """Three-layer MPC optimization architecture."""
    elements = []

    # Title
    elements.append(
        f'<text x="350" y="25" text-anchor="middle" fill="{_TEXT}" '
        f'font-size="14" font-weight="bold" font-family="Segoe UI">'
        f'Three-Layer MPC Architecture</text>')

    # Layer 3
    elements.append(_box(200, 40, 300, 50, "Layer 3: Nonlinear Optimizer",
                         color=_PURPLE, sublabel="CasADi / IPOPT"))
    # Arrow down
    elements.append(_arrow_down(350, 90, 115, "re-linearize"))

    # Layer 2
    elements.append(_box(200, 120, 300, 50, "Layer 2: Steady-State Target",
                         color=_TEAL, sublabel="HiGHS LP/QP"))
    elements.append(_arrow_down(350, 170, 195, "y_ss, u_ss"))

    # Layer 1
    elements.append(_box(200, 200, 300, 50, "Layer 1: Dynamic Controller",
                         color=_ACCENT, sublabel="OSQP QP"))
    elements.append(_arrow_down(350, 250, 275, "Δu"))

    # Plant
    elements.append(_box(220, 280, 260, 45, "Plant (via OPC UA)",
                         color=_GREEN, sublabel=""))

    # Feedback arrow
    elements.append(
        f'<path d="M 480 302 L 530 302 L 530 60 L 500 60" '
        f'stroke="{_ORANGE}" stroke-width="1.5" fill="none" '
        f'marker-end="url(#arrowhead)"/>')
    elements.append(
        f'<text x="540" y="180" fill="{_ORANGE}" font-size="9" '
        f'font-family="Segoe UI" transform="rotate(90,540,180)">y measured</text>')

    # Timing labels
    elements.append(
        f'<text x="150" y="68" text-anchor="end" fill="{_TEXT_LIGHT}" '
        f'font-size="8" font-family="Segoe UI">minutes/hours</text>')
    elements.append(
        f'<text x="150" y="148" text-anchor="end" fill="{_TEXT_LIGHT}" '
        f'font-size="8" font-family="Segoe UI">every sample</text>')
    elements.append(
        f'<text x="150" y="228" text-anchor="end" fill="{_TEXT_LIGHT}" '
        f'font-size="8" font-family="Segoe UI">every sample</text>')

    return _svg_wrap("\n".join(elements), 600, 340)


# =====================================================================
# Diagram: Identification Workflow
# =====================================================================
def diagram_ident_workflow() -> str:
    """Step-by-step identification workflow."""
    elements = []

    elements.append(
        f'<text x="400" y="25" text-anchor="middle" fill="{_TEXT}" '
        f'font-size="14" font-weight="bold" font-family="Segoe UI">'
        f'Model Identification Workflow</text>')

    steps = [
        ("Step Test\nDesign", _TEXT_LIGHT),
        ("Data\nCollection", _ORANGE),
        ("Data\nConditioning", _TEAL),
        ("Model\nIdentification", _ACCENT),
        ("Model\nValidation", _GREEN),
        ("Model\nExport", _PURPLE),
    ]

    y = 45
    for i, (label, color) in enumerate(steps):
        x = 30 + i * 130
        lines = label.split("\n")
        elements.append(_box(x, y, 110, 50, lines[0], color=color,
                             sublabel=lines[1] if len(lines) > 1 else ""))
        if i < len(steps) - 1:
            elements.append(_arrow_right(x + 110, x + 130, y + 25))

    # Sub-steps for identification
    elements.append(
        f'<text x="400" y="120" text-anchor="middle" fill="{_TEXT_LIGHT}" '
        f'font-size="10" font-family="Segoe UI">Identification Methods:</text>')

    methods = [
        ("FIR\n(DLS/COR/Ridge)", _ACCENT),
        ("Subspace\n(N4SID/MOESP/CVA)", _TEAL),
        ("Constrained\n(SLSQP)", _ORANGE),
        ("Closed-Loop\n(IV/Regularized)", _RED),
    ]

    for i, (label, color) in enumerate(methods):
        x = 60 + i * 180
        lines = label.split("\n")
        elements.append(_box(x, 135, 155, 40, lines[0], color=color,
                             sublabel=lines[1] if len(lines) > 1 else "",
                             font_size=10))

    return _svg_wrap("\n".join(elements), 800, 190)


# =====================================================================
# Diagram: FIR Model
# =====================================================================
def diagram_fir_model() -> str:
    """FIR model structure: input → delays → sum → output."""
    elements = []

    elements.append(
        f'<text x="350" y="22" text-anchor="middle" fill="{_TEXT}" '
        f'font-size="13" font-weight="bold" font-family="Segoe UI">'
        f'FIR Model: y(k) = Σ g(i) · u(k-i)</text>')

    # Input
    elements.append(_box(20, 50, 80, 35, "u(k)", color=_ACCENT, font_size=10))

    # Delay chain
    delays = ["z⁻¹", "z⁻¹", "z⁻¹", "···", "z⁻¹"]
    for i, d in enumerate(delays):
        x = 130 + i * 80
        elements.append(_box(x, 50, 55, 35, d, color=_CHROME,
                             text_color=_TEXT, font_size=10))
        if i > 0:
            elements.append(_arrow_right(x - 25, x, 67))

    elements.append(_arrow_right(100, 130, 67))

    # Gain coefficients
    gains = ["g(0)", "g(1)", "g(2)", "···", "g(N-1)"]
    for i, g in enumerate(gains):
        x = 135 + i * 80
        elements.append(_arrow_down(x + 27, 85, 105))
        elements.append(_box(x, 108, 55, 28, g, color=_TEAL,
                             font_size=9))
        elements.append(_arrow_down(x + 27, 136, 155))

    # Sum
    elements.append(_box(260, 160, 60, 35, "Σ", color=_ORANGE,
                         font_size=16))

    # Output
    elements.append(_arrow_right(320, 360, 177))
    elements.append(_box(365, 160, 80, 35, "y(k)", color=_GREEN,
                         font_size=10))

    return _svg_wrap("\n".join(elements), 500, 210)


# =====================================================================
# Diagram: Subspace Method
# =====================================================================
def diagram_subspace() -> str:
    """Subspace identification: data → Hankel → SVD → SS model."""
    elements = []

    elements.append(
        f'<text x="380" y="22" text-anchor="middle" fill="{_TEXT}" '
        f'font-size="13" font-weight="bold" font-family="Segoe UI">'
        f'Subspace Identification Pipeline</text>')

    steps = [
        ("I/O Data\nu(k), y(k)", _TEXT_LIGHT),
        ("Block-Hankel\nMatrices", _ACCENT),
        ("Oblique\nProjection", _TEAL),
        ("SVD →\nOrder nx", _ORANGE),
        ("Extract\nA, B, C, D", _GREEN),
    ]

    for i, (label, color) in enumerate(steps):
        x = 20 + i * 150
        lines = label.split("\n")
        elements.append(_box(x, 40, 130, 50, lines[0], color=color,
                             sublabel=lines[1] if len(lines) > 1 else "",
                             font_size=10))
        if i < len(steps) - 1:
            elements.append(_arrow_right(x + 130, x + 150, 65))

    return _svg_wrap("\n".join(elements), 770, 110)


# =====================================================================
# Diagram: Data Conditioning Pipeline
# =====================================================================
def diagram_conditioning() -> str:
    """Data conditioning pipeline stages."""
    elements = []

    elements.append(
        f'<text x="400" y="22" text-anchor="middle" fill="{_TEXT}" '
        f'font-size="13" font-weight="bold" font-family="Segoe UI">'
        f'Data Conditioning Pipeline</text>')

    stages = [
        ("Segments", _TEXT_LIGHT),
        ("Exclusion\nRules", _ORANGE),
        ("Cutoff /\nSpike / Flat", _RED),
        ("Resample", _TEAL),
        ("Filter", _ACCENT),
        ("Fill NaN", _TEXT_LIGHT),
        ("Outlier\nClip", _ORANGE),
        ("Transform", _PURPLE),
        ("Holdout\nSplit", _GREEN),
    ]

    for i, (label, color) in enumerate(stages):
        x = 10 + i * 88
        lines = label.split("\n")
        h = 40 if len(lines) == 1 else 45
        elements.append(_box(x, 40, 78, h, lines[0], color=color,
                             sublabel=lines[1] if len(lines) > 1 else "",
                             font_size=8, rx=4))
        if i < len(stages) - 1:
            elements.append(_arrow_right(x + 78, x + 88, 60))

    return _svg_wrap("\n".join(elements), 810, 100)


# =====================================================================
# Diagram: Quality Scorecard
# =====================================================================
def diagram_scorecard() -> str:
    """Quality scorecard categories."""
    elements = []

    elements.append(
        f'<text x="300" y="22" text-anchor="middle" fill="{_TEXT}" '
        f'font-size="13" font-weight="bold" font-family="Segoe UI">'
        f'Model Quality Scorecard</text>')

    cats = [
        ("DATA\nQUALITY", _ACCENT, "NaN, outliers,\nsample count"),
        ("MV\nEXCITATION", _TEAL, "Move count,\nmove size"),
        ("MODEL\nFIT", _ORANGE, "R², RMSE,\nwhiteness"),
        ("CONTROL-\nLABILITY", _PURPLE, "Cond. number,\nRGA, colinear"),
    ]

    for i, (label, color, desc) in enumerate(cats):
        x = 30 + i * 150
        lines = label.split("\n")
        elements.append(_box(x, 40, 130, 45, lines[0], color=color,
                             sublabel=lines[1] if len(lines) > 1 else "",
                             font_size=10))
        desc_lines = desc.split("\n")
        for j, dl in enumerate(desc_lines):
            elements.append(
                f'<text x="{x+65}" y="{100+j*14}" text-anchor="middle" '
                f'fill="{_TEXT_LIGHT}" font-size="8" '
                f'font-family="Segoe UI">{dl}</text>')

    # Grade legend
    elements.append(
        f'<rect x="30" y="130" width="16" height="12" rx="3" fill="{_GREEN}"/>')
    elements.append(
        f'<text x="52" y="140" fill="{_TEXT}" font-size="9" '
        f'font-family="Segoe UI">GREEN (&lt;10%)</text>')
    elements.append(
        f'<rect x="160" y="130" width="16" height="12" rx="3" fill="{_ORANGE}"/>')
    elements.append(
        f'<text x="182" y="140" fill="{_TEXT}" font-size="9" '
        f'font-family="Segoe UI">YELLOW (10-50%)</text>')
    elements.append(
        f'<rect x="310" y="130" width="16" height="12" rx="3" fill="{_RED}"/>')
    elements.append(
        f'<text x="332" y="140" fill="{_TEXT}" font-size="9" '
        f'font-family="Segoe UI">RED (&gt;50%)</text>')

    return _svg_wrap("\n".join(elements), 640, 155)


# =====================================================================
# Diagram: Curve Operations
# =====================================================================
def diagram_curve_ops() -> str:
    """Curve operations on step response."""
    elements = []

    elements.append(
        f'<text x="300" y="22" text-anchor="middle" fill="{_TEXT}" '
        f'font-size="13" font-weight="bold" font-family="Segoe UI">'
        f'Curve Operations Workflow</text>')

    # Original
    elements.append(_box(20, 40, 120, 40, "Identified\nStep Response",
                         color=_TEXT_LIGHT, font_size=9))
    elements.append(_arrow_right(140, 170, 60))

    # Operations
    ops = ["SHIFT", "GAIN", "FIRST-\nORDER", "LEAD-\nLAG"]
    for i, op in enumerate(ops):
        x = 170 + i * 90
        lines = op.split("\n")
        elements.append(_box(x, 40, 75, 40, lines[0], color=_ACCENT,
                             sublabel=lines[1] if len(lines) > 1 else "",
                             font_size=9, rx=4))
        if i < len(ops) - 1:
            elements.append(_arrow_right(x + 75, x + 90, 60))

    elements.append(_arrow_right(530, 560, 60))
    elements.append(_box(560, 40, 100, 40, "Master\nModel",
                         color=_GREEN, font_size=9))

    return _svg_wrap("\n".join(elements), 680, 95)


# =====================================================================
# All diagrams dict (for help viewer)
# =====================================================================
DIAGRAMS = {
    "three_layer": diagram_three_layer,
    "ident_workflow": diagram_ident_workflow,
    "fir_model": diagram_fir_model,
    "subspace": diagram_subspace,
    "conditioning": diagram_conditioning,
    "scorecard": diagram_scorecard,
    "curve_ops": diagram_curve_ops,
}


def get_diagram(name: str) -> str:
    """Get an SVG diagram by name. Returns empty string if not found."""
    func = DIAGRAMS.get(name)
    if func:
        return func()
    return ""


def all_diagram_names() -> list:
    """Return all available diagram names."""
    return list(DIAGRAMS.keys())
