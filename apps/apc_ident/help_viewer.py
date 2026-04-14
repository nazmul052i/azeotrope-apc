"""Built-in help viewer for APC Ident.

Opens documentation as HTML in a dockable panel or popup window.
Supports F1 context-sensitive help (shows help for the current tab).
"""
from __future__ import annotations

import os
import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)

# Map tab/step IDs to help topics
_CONTEXT_HELP = {
    "data": "data_tab",
    "tags": "tags_tab",
    "ident": "identification",
    "results": "results_tab",
    "analysis": "analysis_tab",
    "validate": "validation_tab",
}

# Help topics with inline content (used when markdown files aren't available)
_HELP_TOPICS = {
    "welcome": {
        "title": "Welcome to APC Ident",
        "html": """
        <h2>APC Ident -- Model Identification Studio</h2>
        <p>APC Ident is an industrial-grade model identification tool for
        Advanced Process Control (MPC). It identifies dynamic models from
        step-test data for use in DMC-style controllers.</p>

        <h3>Workflow</h3>
        <ol>
        <li><b>Data</b> -- Load CSV/Parquet data, inspect trends, condition data</li>
        <li><b>Tags</b> -- Assign MV/CV/DV roles to columns</li>
        <li><b>Identify</b> -- Configure and run FIR or Subspace identification</li>
        <li><b>Results</b> -- Inspect step responses, apply curve operations, assemble model</li>
        <li><b>Analysis</b> -- Cross-correlation, uncertainty, gain matrix analysis</li>
        <li><b>Validate</b> -- Compare model predictions against test data</li>
        </ol>

        <h3>Quick Start</h3>
        <ol>
        <li>Click <b>Data</b> in the sidebar</li>
        <li>Right-click <b>Data</b> → <b>Load CSV/Parquet</b></li>
        <li>Select your step-test CSV file</li>
        <li>Use the Tag Browser to select which tags to view</li>
        <li>Right-click tags to assign MV/CV roles</li>
        <li>Click <b>Identify</b> → <b>Smart Config</b> for auto-configuration</li>
        <li>Click <b>IDENTIFY</b> to run</li>
        </ol>

        <h3>Keyboard Shortcuts</h3>
        <table border="1" cellpadding="4" style="border-collapse: collapse;">
        <tr><td><b>F1</b></td><td>Help (context-sensitive)</td></tr>
        <tr><td><b>F5</b></td><td>Run Identification</td></tr>
        <tr><td><b>Ctrl+1-6</b></td><td>Navigate to tab</td></tr>
        <tr><td><b>Ctrl+N</b></td><td>New Project</td></tr>
        <tr><td><b>Ctrl+O</b></td><td>Open Project</td></tr>
        <tr><td><b>Ctrl+S</b></td><td>Save Project</td></tr>
        <tr><td><b>Ctrl+Shift+S</b></td><td>Smart Config</td></tr>
        <tr><td><b>Ctrl+Shift+R</b></td><td>Generate Report</td></tr>
        </table>
        """,
    },
    "data_tab": {
        "title": "Data Tab",
        "html": """
        <h2>Data Tab -- Trend Workspace</h2>

        <h3>Loading Data</h3>
        <p>Right-click <b>Data</b> in the sidebar and select <b>Load CSV/Parquet</b>,
        or use the <b>Load</b> button in the toolbar. Multiple files can be loaded
        and merged.</p>
        <p>Supported formats: CSV, Parquet, DMC Vector (.vec/.dep/.ind)</p>

        <h3>Tag Browser</h3>
        <p>The tag browser appears after loading data. It shows all columns with:</p>
        <ul>
        <li><b>[MV]</b> blue = Manipulated Variable</li>
        <li><b>[CV]</b> green = Controlled Variable</li>
        <li><b>[DV]</b> orange = Disturbance Variable</li>
        <li>Unchecked tags are not plotted</li>
        </ul>
        <p>Right-click any tag for: Properties, Set Role, Plot Only, Hide,
        Set Cutoffs, Detect Spikes/Flatline.</p>

        <h3>Trend Interaction</h3>
        <ul>
        <li><b>Pan</b>: Click and drag on the plot</li>
        <li><b>Zoom</b>: Scroll wheel</li>
        <li><b>Right-click</b>: Context menu with conditioning operations</li>
        <li><b>Orange region</b>: Drag to select time windows for segments</li>
        </ul>

        <h3>Conditioning Tools</h3>
        <ul>
        <li><b>Auto Condition</b>: One-click auto-detect cutoffs, flatline, spikes</li>
        <li><b>Before/After</b>: Toggle raw vs conditioned view</li>
        <li><b>SSD</b>: Steady-state detection (green shading)</li>
        <li><b>Resample</b>: Downsample to optimal rate</li>
        </ul>
        """,
    },
    "tags_tab": {
        "title": "Tags Tab",
        "html": """
        <h2>Tags Tab -- Variable Assignment</h2>
        <p>Assign each CSV column a role:</p>
        <ul>
        <li><b>MV</b> (Manipulated Variable) -- controller outputs (valve positions, setpoints)</li>
        <li><b>CV</b> (Controlled Variable) -- process measurements to be controlled</li>
        <li><b>DV</b> (Disturbance Variable) -- measured disturbances (feedforward)</li>
        <li><b>Ignore</b> -- not used in identification</li>
        </ul>

        <h3>Quick Methods</h3>
        <ul>
        <li><b>Auto-Assign</b>: First half of columns = MV, rest = CV</li>
        <li><b>Right-click tag</b> in Tag Browser → Set Role</li>
        <li><b>Tag Properties</b> dialog for detailed configuration</li>
        </ul>
        """,
    },
    "identification": {
        "title": "Identification Tab",
        "html": """
        <h2>Identification -- Configure & Run</h2>

        <h3>Smart Config</h3>
        <p>Click <b>⚡ Smart Config</b> to auto-detect all parameters from data:
        sample period, model length, method, smoothing, integrating CVs.</p>

        <h3>FIR Identification</h3>
        <ul>
        <li><b>Model Length (n_coeff)</b>: Number of FIR coefficients. Typically 1.5× the settling time in samples.</li>
        <li><b>Method</b>: DLS (open-loop), COR (closed-loop tolerant), Ridge (collinear inputs)</li>
        <li><b>Smoothing</b>: Pipeline (recommended), exponential, Savitzky-Golay, asymptotic</li>
        </ul>

        <h3>Subspace Identification</h3>
        <ul>
        <li><b>Algorithm</b>: N4SID (standard), MOESP (robust), CVA (statistical)</li>
        <li><b>Model Order</b>: Auto (recommended) or manual</li>
        <li><b>Future Horizon</b>: Block rows in Hankel matrices. Rule of thumb: 1.5-2× expected order.</li>
        <li><b>Expert Mode</b>: Differencing, double-diff, oversampling for difficult data</li>
        </ul>

        <h3>Multi-Trial</h3>
        <p>Check "Run multiple parameter sets" and enter comma-separated n_coeff values
        (e.g. 40, 60, 80, 120). All trials run and the best is auto-selected.</p>

        <h3>Quality Scorecard</h3>
        <p>After identification, a scorecard appears grading:</p>
        <ul>
        <li><b>DATA QUALITY</b>: NaN, outliers, sample count</li>
        <li><b>MV EXCITATION</b>: Move count and adequacy</li>
        <li><b>MODEL FIT</b>: R², residual whiteness, condition number</li>
        <li><b>CONTROLLABILITY</b>: Gain matrix condition, RGA</li>
        </ul>
        """,
    },
    "results_tab": {
        "title": "Results Tab",
        "html": """
        <h2>Results -- Inspect, Shape, Assemble, Export</h2>

        <h3>Step Response Matrix</h3>
        <p>Shows the step response for every MV→CV pair. Colors indicate gain
        sign and strength: green=positive, red=negative, darker=stronger.</p>

        <h3>Curve Operations</h3>
        <p>Select a CV/MV cell, choose an operation, set parameters, click Apply:</p>
        <ul>
        <li><b>SHIFT</b>: Adjust dead time (+ adds delay)</li>
        <li><b>GAIN</b>: Multiply the entire response</li>
        <li><b>GSCALE</b>: Scale to a target steady-state gain</li>
        <li><b>FIRSTORDER</b>: Apply first-order dynamics (smoothing)</li>
        <li><b>LEADLAG</b>: Lead-lag compensation</li>
        <li><b>ZERO</b>: Set response to zero (no interaction)</li>
        </ul>

        <h3>Model Assembly</h3>
        <p>After multi-trial, pick which trial to use for each CV/MV cell.
        Click <b>Build Master Model</b> to assemble the final model.</p>

        <h3>Export</h3>
        <p>Click <b>Export Model Bundle</b> to save as .apcmodel (HDF5).
        The bundle contains FIR coefficients, state-space matrices,
        gain matrix, and metadata for the architect app.</p>
        """,
    },
    "analysis_tab": {
        "title": "Analysis Tab",
        "html": """
        <h2>Analysis Tools</h2>

        <h3>Cross-Correlation</h3>
        <p>Evaluates step test quality by analyzing MV independence:</p>
        <ul>
        <li><b>IDEAL</b> (< 30%): MVs are independent -- good test</li>
        <li><b>ACCEPTABLE</b> (30-50%): Some correlation -- acceptable</li>
        <li><b>POOR</b> (50-80%): High correlation -- results may be biased</li>
        <li><b>UNACCEPTABLE</b> (> 80%): MVs moved together -- can't separate effects</li>
        </ul>

        <h3>Model Uncertainty</h3>
        <p>Grades each MV→CV channel A/B/C/D based on steady-state and dynamic uncertainty.
        Shows frequency-domain Bode plots with confidence bands.</p>

        <h3>Gain Matrix Analysis</h3>
        <p>Checks controllability of the identified model:</p>
        <ul>
        <li><b>Condition Number</b>: < 20 good, > 100 problematic</li>
        <li><b>RGA</b> (Relative Gain Array): Diagonal ~1.0 = good pairing</li>
        <li><b>Colinearity</b>: Detects MVs with similar effects</li>
        </ul>
        """,
    },
    "validation_tab": {
        "title": "Validation Tab",
        "html": """
        <h2>Validation -- Model Testing</h2>

        <h3>Test Data Sources</h3>
        <ul>
        <li><b>Hold-out tail</b>: Last 20% of data (set by holdout fraction)</li>
        <li><b>Full training set</b>: Re-predict the training data</li>
        <li><b>Load CSV</b>: Independent test dataset</li>
        </ul>

        <h3>Prediction Modes</h3>
        <ul>
        <li><b>Open-loop</b>: Predict entire trajectory from inputs only (harder test)</li>
        <li><b>One-step-ahead</b>: Predict next sample using current measurements (easier test)</li>
        </ul>

        <h3>Metrics</h3>
        <ul>
        <li><b>R²</b>: > 0.9 good, > 0.7 acceptable, < 0.5 poor</li>
        <li><b>RMSE</b>: Root mean squared error in engineering units</li>
        <li><b>NRMSE</b>: Normalized RMSE (RMSE / range)</li>
        <li><b>Bias</b>: Systematic offset (should be near zero)</li>
        </ul>
        """,
    },
    "theory_fir": {
        "title": "FIR Identification Theory",
        "html": """
        <h2>Finite Impulse Response (FIR) Identification</h2>

        <h3>The Model</h3>
        <p>A MIMO FIR model relates inputs u to outputs y through a sequence of
        Markov parameter matrices G(k):</p>
        <pre>y(t) = Σ_{k=0}^{N-1} G(k) · u(t-k) + e(t)</pre>
        <p>where N is the model length (n_coeff), G(k) is an (ny × nu) matrix at lag k,
        and e(t) is the residual.</p>

        <h3>Step Response</h3>
        <p>The cumulative step response S(k) gives the output at time k when a unit
        step is applied at time 0:</p>
        <pre>S(k) = Σ_{i=0}^{k} G(i)</pre>
        <p>The steady-state gain is K = S(N-1) = Σ G(i).</p>

        <h3>Least Squares Solution</h3>
        <p>Stack all samples into a regression: Y = Φ · θ + E</p>
        <p>where Φ is the block-Toeplitz matrix of past inputs.</p>
        <p>The DLS solution is: θ = (Φ'Φ)^{-1} Φ'Y</p>
        <p>Ridge adds regularization: θ = (Φ'Φ + αI)^{-1} Φ'Y</p>

        <h3>Confidence Intervals</h3>
        <p>Under i.i.d. residual assumption:</p>
        <pre>Var(θ) = σ² · (Φ'Φ)^{-1}</pre>
        <p>95% CI: θ ± 1.96 · √diag(Var(θ))</p>
        """,
    },
    "theory_subspace": {
        "title": "Subspace Identification Theory",
        "html": """
        <h2>Subspace State-Space Identification</h2>

        <h3>The Model</h3>
        <pre>x(k+1) = A·x(k) + B·u(k)
y(k)   = C·x(k) + D·u(k)</pre>
        <p>where x is the state vector of dimension nx.</p>

        <h3>Block-Hankel Matrices</h3>
        <p>The data is arranged into past/future block-Hankel matrices with f
        (future horizon) and p (past horizon) block rows.</p>

        <h3>N4SID Algorithm</h3>
        <ol>
        <li>Build past data matrix W_p = [U_p; Y_p]</li>
        <li>Oblique projection: O_i = Y_f /_{U_f} W_p</li>
        <li>SVD of O_i → singular values for order selection</li>
        <li>Observability matrix: Γ = U·√Σ (first nx columns)</li>
        <li>C = first ny rows of Γ</li>
        <li>A from shift structure of Γ</li>
        <li>B, D from least squares on state equation</li>
        </ol>

        <h3>Model Order Selection</h3>
        <p>Automatic: look for a gap in the singular values. The order nx is
        where σ_{n+1}/σ_1 drops below the threshold.</p>
        """,
    },
}


class HelpViewer(QDialog):
    """Built-in help viewer with topic navigation."""

    def __init__(self, parent=None, initial_topic: str = "welcome"):
        super().__init__(parent)
        self.setWindowTitle("APC Ident Help")
        self.setMinimumSize(900, 650)
        self.setStyleSheet(
            "QDialog { background: #EBECF1; color: #1A1C24; }"
            "QLabel { color: #1A1C24; background: transparent; }"
            "QListWidget { background: #F5F6FA; border: 1px solid #9AA5B4; }"
            "QListWidget::item:selected { background: #2B5EA7; color: white; }"
            "QTextBrowser { background: #FFFFFF; color: #1A1C24; "
            "  border: 1px solid #9AA5B4; font-size: 10pt; }"
            "QPushButton { background: #EBECF1; border: 1px solid #9AA5B4; "
            "  padding: 6px 16px; border-radius: 3px; }"
        )
        self._build()
        self.show_topic(initial_topic)

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # Topic list
        left = QVBoxLayout()
        left_label = QLabel("TOPICS")
        left_label.setStyleSheet(
            "font-weight: bold; font-size: 8pt; letter-spacing: 1px; "
            "color: #4A5068;")
        left.addWidget(left_label)

        self.topic_list = QListWidget()
        self.topic_list.setFixedWidth(200)
        for topic_id, topic in _HELP_TOPICS.items():
            item = QListWidgetItem(topic["title"])
            item.setData(Qt.UserRole, topic_id)
            self.topic_list.addItem(item)
        self.topic_list.currentItemChanged.connect(self._on_topic_changed)
        left.addWidget(self.topic_list, 1)

        lay.addLayout(left)

        # Content browser
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet(
            "QTextBrowser { padding: 16px; font-family: 'Segoe UI'; }")
        lay.addWidget(self.browser, 1)

    def _on_topic_changed(self, current, previous):
        if current is None:
            return
        topic_id = current.data(Qt.UserRole)
        self.show_topic(topic_id)

    def show_topic(self, topic_id: str):
        """Display a help topic."""
        # First check if we have a markdown file
        docs_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "docs")

        md_paths = [
            os.path.join(docs_dir, "theory", f"{topic_id}.md"),
            os.path.join(docs_dir, "tutorial", f"{topic_id}.md"),
            os.path.join(docs_dir, f"{topic_id}.md"),
        ]

        for md_path in md_paths:
            if os.path.exists(md_path):
                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        md_text = f.read()
                    # Basic markdown to HTML (headers, bold, code)
                    html = self._md_to_html(md_text)
                    self.browser.setHtml(self._wrap_html(html))
                    return
                except Exception:
                    pass

        # Fall back to inline content
        topic = _HELP_TOPICS.get(topic_id)
        if topic:
            self.browser.setHtml(self._wrap_html(topic["html"]))
        else:
            self.browser.setHtml(self._wrap_html(
                f"<h2>Topic not found: {topic_id}</h2>"
                f"<p>No help available for this topic yet.</p>"))

    def _wrap_html(self, body: str) -> str:
        return f"""
        <html>
        <head>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; font-size: 10pt;
                   color: #1A1C24; margin: 0; padding: 16px;
                   background: #FFFFFF; }}
            h2 {{ color: #2B5EA7; border-bottom: 2px solid #C8CDD8;
                  padding-bottom: 6px; }}
            h3 {{ color: #4A5068; margin-top: 20px; }}
            code, pre {{ background: #F0F2F6; padding: 2px 6px;
                        border-radius: 3px; font-family: Consolas;
                        font-size: 9pt; }}
            pre {{ padding: 10px; border: 1px solid #C8CDD8;
                   overflow-x: auto; }}
            table {{ border-collapse: collapse; margin: 10px 0; }}
            td, th {{ border: 1px solid #C8CDD8; padding: 4px 10px; }}
            th {{ background: #E0E2EB; }}
            li {{ margin: 4px 0; }}
            b {{ color: #2B5EA7; }}
        </style>
        </head>
        <body>{body}</body>
        </html>
        """

    @staticmethod
    def _md_to_html(md: str) -> str:
        """Very basic markdown to HTML converter."""
        import re
        lines = md.split("\n")
        html_lines = []
        in_code = False
        in_list = False

        for line in lines:
            # Code blocks
            if line.strip().startswith("```"):
                if in_code:
                    html_lines.append("</pre>")
                    in_code = False
                else:
                    html_lines.append("<pre>")
                    in_code = True
                continue
            if in_code:
                html_lines.append(line)
                continue

            # Headers
            if line.startswith("#### "):
                html_lines.append(f"<h4>{line[5:]}</h4>")
            elif line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            # Lists
            elif line.strip().startswith("- "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                content = line.strip()[2:]
                content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', content)
                content = re.sub(r'`(.+?)`', r'<code>\1</code>', content)
                html_lines.append(f"<li>{content}</li>")
            elif line.strip().startswith(tuple(f"{i}." for i in range(1, 20))):
                if not in_list:
                    html_lines.append("<ol>")
                    in_list = True
                content = re.sub(r'^\d+\.\s*', '', line.strip())
                content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', content)
                html_lines.append(f"<li>{content}</li>")
            else:
                if in_list:
                    html_lines.append("</ul>" if "</li>" in html_lines[-1] else "</ol>")
                    in_list = False
                # Bold, code, italic
                line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
                line = re.sub(r'`(.+?)`', r'<code>\1</code>', line)
                line = re.sub(r'\$\$(.+?)\$\$', r'<pre>\1</pre>', line)
                if line.strip():
                    html_lines.append(f"<p>{line}</p>")

        if in_list:
            html_lines.append("</ul>")
        return "\n".join(html_lines)


def show_help(parent=None, topic: str = "welcome"):
    """Show the help viewer dialog."""
    dlg = HelpViewer(parent, initial_topic=topic)
    dlg.exec()


def context_help_for_step(step_id: str) -> str:
    """Return the help topic ID for a sidebar step."""
    return _CONTEXT_HELP.get(step_id, "welcome")
