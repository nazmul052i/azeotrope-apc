"""Built-in help viewer for APC Architect.

Same structure as the ident help viewer -- F1 context-sensitive,
topic sidebar, HTML rendering with ISA-101 styling and SVG diagrams.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QTextBrowser, QVBoxLayout,
)


def _diagram(name: str) -> str:
    try:
        from .help_diagrams import get_diagram
        return get_diagram(name)
    except Exception:
        return ""


_CONTEXT_HELP = {
    "config": "configuration",
    "optimize": "optimization",
    "calculate": "calculations",
    "simulate": "simulation",
    "deploy": "deployment",
}

_HELP_TOPICS = {
    "welcome": {
        "title": "Welcome to APC Architect",
        "html": lambda: f"""
        <h2>APC Architect -- Controller Configuration Studio</h2>
        <p>APC Architect is the configuration, tuning, simulation, and
        deployment studio for Azeotrope MPC controllers.</p>

        <h3>Workflow</h3>
        {_diagram("architect_workflow")}

        <ol>
        <li><b>Configure</b> -- Import model, set variable limits, feedback filters, subcontrollers</li>
        <li><b>Optimize</b> -- Tune Layer 1 (QP), Layer 2 (LP), Layer 3 (NLP)</li>
        <li><b>Calculate</b> -- Write Python pre/post-MPC calculation scripts</li>
        <li><b>Simulate</b> -- Interactive closed-loop what-if testing</li>
        <li><b>Deploy</b> -- Connect to plant via OPC UA and run online</li>
        </ol>

        <h3>Keyboard Shortcuts</h3>
        <table border="1" cellpadding="4" style="border-collapse: collapse;">
        <tr><td><b>F1</b></td><td>Help (context-sensitive)</td></tr>
        <tr><td><b>Ctrl+1-5</b></td><td>Navigate to step</td></tr>
        <tr><td><b>Ctrl+N</b></td><td>New Project</td></tr>
        <tr><td><b>Ctrl+O</b></td><td>Open Project</td></tr>
        <tr><td><b>Ctrl+S</b></td><td>Save Project</td></tr>
        <tr><td><b>Ctrl+I</b></td><td>Import Model Bundle</td></tr>
        </table>
        """,
    },
    "configuration": {
        "title": "Configuration",
        "html": lambda: f"""
        <h2>Configuration -- Variables, Filters, Subcontrollers</h2>

        <h3>Sub-Views</h3>
        <ul>
        <li><b>Summary</b> -- Read-only dashboard of controller configuration</li>
        <li><b>Variables</b> -- Edit MV/CV/DV properties: tag, name, units, limits, setpoint, weight</li>
        <li><b>Feedback Filters</b> -- Per-CV filter type for prediction error correction</li>
        <li><b>Subcontrollers</b> -- Group variables into priority sub-problems</li>
        </ul>

        <h3>Feedback Filters</h3>
        {_diagram("feedback_filters")}

        <h3>Importing a Model Bundle</h3>
        <p>Right-click <b>Configure</b> in the sidebar → <b>Import Model Bundle</b>,
        or use <b>File → Import Model Bundle (Ctrl+I)</b>.</p>
        <p>The bundle (.apcmodel from APC Ident) auto-populates:</p>
        <ul>
        <li>MV and CV tag lists with names</li>
        <li>State-space plant model (A, B, C, D matrices)</li>
        <li>Operating point (u0, y0)</li>
        <li>Sample time</li>
        </ul>
        """,
    },
    "optimization": {
        "title": "Optimization / Tuning",
        "html": lambda: f"""
        <h2>Optimization -- Three-Layer Tuning</h2>

        <h3>Layer 1: Dynamic QP</h3>
        {_diagram("qp_formulation")}
        <p>Key tuning parameters per MV:</p>
        <ul>
        <li><b>Move Suppression</b> -- penalizes move size (higher = slower, smoother)</li>
        <li><b>Max Move</b> -- absolute limit on Δu per step</li>
        <li><b>Move Resolution</b> -- minimum meaningful move size</li>
        </ul>
        <p>Key tuning parameters per CV:</p>
        <ul>
        <li><b>Weight</b> -- importance of tracking setpoint (higher = tighter control)</li>
        <li><b>Setpoint</b> -- desired steady-state value</li>
        </ul>

        <h3>Constraint Priorities</h3>
        {_diagram("constraint_priorities")}

        <h3>Layer 2: Steady-State Target (LP/QP)</h3>
        <p>The 6-step wizard guides you through:</p>
        <ol>
        <li>CV ranking by importance</li>
        <li>MV/CV optimization preferences</li>
        <li>MV cost prioritization</li>
        <li>Evaluate targets</li>
        <li>Initialize tuning</li>
        <li>Steady-state calculator</li>
        </ol>

        <h3>Layer 3: Nonlinear Optimizer (NLP/RTO)</h3>
        <p>Optional. Requires a nonlinear plant model and CasADi/IPOPT.</p>
        """,
    },
    "calculations": {
        "title": "Calculations",
        "html": """
        <h2>Calculations -- Python Scripting</h2>

        <p>Write custom Python scripts that execute before (Input) or after
        (Output) each MPC cycle.</p>

        <h3>Available Variables</h3>
        <table border="1" cellpadding="4" style="border-collapse: collapse;">
        <tr><th>Variable</th><th>Type</th><th>Description</th></tr>
        <tr><td><code>cvs</code></td><td>dict</td><td>CV measurements and setpoints</td></tr>
        <tr><td><code>mvs</code></td><td>dict</td><td>MV values and limits</td></tr>
        <tr><td><code>dvs</code></td><td>dict</td><td>DV measurements</td></tr>
        <tr><td><code>user</code></td><td>dict</td><td>Persistent user variables</td></tr>
        <tr><td><code>t</code></td><td>float</td><td>Simulation time (s)</td></tr>
        <tr><td><code>cycle</code></td><td>int</td><td>MPC cycle counter</td></tr>
        <tr><td><code>dt</code></td><td>float</td><td>Sample period (s)</td></tr>
        <tr><td><code>np</code></td><td>module</td><td>NumPy</td></tr>
        </table>

        <h3>Example: Pressure-Compensated Temperature</h3>
        <pre>
# Input calculation: correct temperature for pressure
pct = cvs["TI-201.PV"] + 15.0 * (cvs["PI-201.PV"] - 14.7)
user["PCT"] = pct
cvs["TI-201.PV"] = pct
        </pre>
        """,
    },
    "simulation": {
        "title": "Simulation",
        "html": lambda: f"""
        <h2>Simulation -- Interactive What-If Testing</h2>

        <h3>Execution Cycle</h3>
        {_diagram("simulation_loop")}

        <h3>How to Use</h3>
        <ol>
        <li>Click <b>Step</b> to advance one MPC cycle</li>
        <li>Click <b>Run</b> for continuous execution</li>
        <li>Edit MV/CV table cells to introduce disturbances or setpoint changes</li>
        <li>Watch the trend plots update in real time</li>
        </ol>

        <h3>What to Test</h3>
        <ul>
        <li><b>Setpoint tracking</b> -- change a CV setpoint, verify response speed and overshoot</li>
        <li><b>Disturbance rejection</b> -- add a DV step, verify CVs return to setpoint</li>
        <li><b>Constraint handling</b> -- push an MV to its limit, verify graceful degradation</li>
        <li><b>Infeasibility</b> -- tighten CV limits until infeasible, verify relaxation order</li>
        </ul>

        <h3>Table Filters</h3>
        <ul>
        <li><b>Entry Type</b>: Show All / Inputs / Results</li>
        <li><b>Value Type</b>: Show All / Operating / Tuning</li>
        </ul>
        """,
    },
    "deployment": {
        "title": "Deployment",
        "html": lambda: f"""
        <h2>Deployment -- OPC UA Runtime</h2>

        <h3>Architecture</h3>
        {_diagram("deployment")}

        <h3>Steps</h3>
        <ol>
        <li>Enter the OPC UA server URL</li>
        <li>Click <b>Connect</b> to verify connectivity</li>
        <li>Map IO tags to controller variables</li>
        <li>Set validation limits</li>
        <li>Click <b>Deploy</b> to start the control loop</li>
        <li>Monitor performance in the Activity tab</li>
        <li>Click <b>Stop</b> to safely shut down</li>
        </ol>

        <h3>IO Tag Structure</h3>
        <p>Each variable has tags for:</p>
        <ul>
        <li><b>PV</b> -- process value (measurement)</li>
        <li><b>SP</b> -- setpoint</li>
        <li><b>OP</b> -- output (controller action)</li>
        <li><b>Mode</b> -- auto/manual/cascade</li>
        <li><b>Status</b> -- good/bad/uncertain</li>
        </ul>
        """,
    },
}


class ArchitectHelpViewer(QDialog):
    def __init__(self, parent=None, initial_topic: str = "welcome"):
        super().__init__(parent)
        self.setWindowTitle("APC Architect Help")
        self.setMinimumSize(950, 680)
        self.setStyleSheet(
            "QDialog { background: #EBECF1; color: #1A1C24; }"
            "QListWidget { background: #F5F6FA; border: 1px solid #9AA5B4; }"
            "QListWidget::item:selected { background: #2B5EA7; color: white; }"
            "QTextBrowser { background: #FFFFFF; color: #1A1C24; "
            "  border: 1px solid #9AA5B4; font-size: 10pt; }")
        self._build()
        self.show_topic(initial_topic)

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        left = QVBoxLayout()
        left.addWidget(QLabel("TOPICS"))
        self.topic_list = QListWidget()
        self.topic_list.setFixedWidth(200)
        for tid, t in _HELP_TOPICS.items():
            item = QListWidgetItem(t["title"])
            item.setData(Qt.UserRole, tid)
            self.topic_list.addItem(item)
        self.topic_list.currentItemChanged.connect(self._on_changed)
        left.addWidget(self.topic_list, 1)
        lay.addLayout(left)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        lay.addWidget(self.browser, 1)

    def _on_changed(self, current, prev):
        if current:
            self.show_topic(current.data(Qt.UserRole))

    def show_topic(self, topic_id: str):
        # Check markdown files first
        docs = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(__file__))), "docs")
        for subdir in ("theory", "tutorial"):
            md = os.path.join(docs, subdir, f"{topic_id}.md")
            if os.path.exists(md):
                try:
                    with open(md, "r", encoding="utf-8") as f:
                        from apc_ident.help_viewer import HelpViewer
                        html = HelpViewer._md_to_html(f.read())
                        self.browser.setHtml(self._wrap(html))
                        return
                except Exception:
                    pass

        topic = _HELP_TOPICS.get(topic_id)
        if topic:
            html = topic["html"]
            if callable(html):
                html = html()
            self.browser.setHtml(self._wrap(html))

    def _wrap(self, body):
        return f"""<html><head><style>
        body {{ font-family: 'Segoe UI'; font-size: 10pt; color: #1A1C24;
               margin: 0; padding: 16px; background: #FFFFFF; }}
        h2 {{ color: #2B5EA7; border-bottom: 2px solid #C8CDD8; padding-bottom: 6px; }}
        h3 {{ color: #4A5068; margin-top: 20px; }}
        code, pre {{ background: #F0F2F6; padding: 2px 6px; border-radius: 3px;
                    font-family: Consolas; font-size: 9pt; }}
        pre {{ padding: 10px; border: 1px solid #C8CDD8; }}
        table {{ border-collapse: collapse; margin: 10px 0; }}
        td, th {{ border: 1px solid #C8CDD8; padding: 4px 10px; }}
        th {{ background: #E0E2EB; }}
        li {{ margin: 4px 0; }}
        b {{ color: #2B5EA7; }}
        </style></head><body>{body}</body></html>"""


def show_architect_help(parent=None, topic="welcome"):
    dlg = ArchitectHelpViewer(parent, topic)
    dlg.exec()


def context_help_for_step(step_id: str) -> str:
    return _CONTEXT_HELP.get(step_id, "welcome")
