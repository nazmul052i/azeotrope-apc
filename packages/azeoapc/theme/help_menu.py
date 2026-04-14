"""Shared Help menu builder for all Azeotrope APC desktop apps.

Provides a consistent Help menu structure across every app:

  Help
    User Guide                  (opens docs/UserGuide.md in browser or editor)
    ──────
    MPC Theory                  (submenu of theory topics)
      Constraint Prioritization
      QP Formulation
      Steady-State Target
      Layer 3 NLP
    FIR Identification Theory   (ident-specific topics)
      DLS / COR / Ridge
      Smoothing Pipeline
      ERA Realisation
      Validation Modes
    ──────
    Check for Updates           (opens GitHub releases page)
    Report an Issue             (opens GitHub issues page)
    ──────
    About {App Name}            (version / credits / license dialog)

Call ``build_help_menu(menubar, app_name, version, parent)`` from
each app's ``_build_menu()`` to get the full Help menu with one line.

The menu items that open files use ``webbrowser.open`` so they work
on Windows, macOS, and Linux without extra dependencies.
"""
from __future__ import annotations

import os
import webbrowser
from typing import Optional

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox


_VERSION = "0.1.0"
_ORG = "Azeotrope Process Control"
_LICENSE = "MIT License"
_GITHUB_URL = "https://github.com/your-org/azeotrope-apc"

_REPO_ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


# ---------------------------------------------------------------------------
# App descriptions (shown in the About dialog)
# ---------------------------------------------------------------------------
_APP_INFO = {
    "launcher": {
        "title": "APC Launcher",
        "icon_letter": "A",
        "description": (
            "The front door to the Azeotrope APC stack. "
            "A hub window that lets you launch every app in the "
            "platform from one place, in workflow order."
        ),
    },
    "architect": {
        "title": "APC Architect",
        "icon_letter": "B",
        "description": (
            "Controller configuration, tuning, and simulation studio. "
            "The DMC3 Builder equivalent. Five tabs: Configuration, "
            "Optimization, Calculations, Simulation, Deployment."
        ),
    },
    "ident": {
        "title": "APC Ident",
        "icon_letter": "I",
        "description": (
            "Step-test model identification studio. Loads historian "
            "CSV data, identifies MIMO FIR models using DLS / COR / "
            "Ridge regression, validates against hold-out data, and "
            "exports .apcmodel bundles for APC Architect."
        ),
    },
    "runtime": {
        "title": "APC Runtime",
        "icon_letter": "R",
        "description": (
            "Production controller cycle loop with a desktop manager "
            "(Aspen Watch Maker style). Runs MPC controllers against "
            "a plant via OPC UA, exposes a REST + Prometheus surface, "
            "and forwards every cycle to the centralized historian."
        ),
    },
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
def build_help_menu(
    menubar,
    app_key: str,
    parent,
    *,
    version: str = _VERSION,
    include_mpc_theory: bool = True,
    include_ident_theory: bool = False,
) -> QMenu:
    """Build and return the Help menu for ``app_key``.

    Attaches to ``menubar``. ``parent`` is the QMainWindow for
    dialog parenting.
    """
    info = _APP_INFO.get(app_key, {
        "title": app_key.title(),
        "icon_letter": "?",
        "description": "",
    })

    hm = menubar.addMenu("&Help")

    # User Guide
    ug = QAction("&User Guide", parent)
    ug.triggered.connect(lambda: _open_doc("docs/UserGuide.md"))
    hm.addAction(ug)

    # README
    readme = QAction("&README", parent)
    readme.triggered.connect(lambda: _open_doc("README.md"))
    hm.addAction(readme)

    hm.addSeparator()

    # MPC Theory submenu
    if include_mpc_theory:
        mpc = QMenu("MPC &Theory", parent)
        for label, anchor in [
            ("Model Predictive Control Overview",   "#model-predictive-control-mpc"),
            ("Constraint Prioritization (P1-P5)",   "#constraint-prioritization"),
            ("QP Formulation (Layer 1)",            "#theory"),
            ("Steady-State Target (Layer 2)",       "#theory"),
            ("Layer 3 NLP / RTO",                   "#theory"),
            ("State-Space Model Representation",    "#configuration-format"),
        ]:
            act = QAction(label, parent)
            act.triggered.connect(
                lambda _=False, a=anchor: _open_doc("README.md", a))
            mpc.addAction(act)
        hm.addMenu(mpc)

    # FIR Ident Theory submenu
    if include_ident_theory:
        fir = QMenu("FIR &Identification Theory", parent)
        for label, anchor in [
            ("Direct Least Squares (DLS)",          "#fir-identification"),
            ("Correlation Method (COR)",            "#fir-identification"),
            ("Ridge Regression (L2)",               "#fir-identification"),
            ("Smoothing Pipeline",                  "#fir-identification"),
            ("ERA / Ho-Kalman Realisation",          "#fir-identification"),
            ("Validation: Open-Loop vs One-Step",   "#fir-identification"),
            ("Excitation Diagnostics",              "#fir-identification"),
        ]:
            act = QAction(label, parent)
            act.triggered.connect(
                lambda _=False, a=anchor: _open_doc("README.md", a))
            fir.addAction(act)
        hm.addMenu(fir)

    hm.addSeparator()

    # External links
    updates = QAction("Check for &Updates", parent)
    updates.triggered.connect(
        lambda: webbrowser.open(f"{_GITHUB_URL}/releases"))
    hm.addAction(updates)

    issues = QAction("Report an &Issue", parent)
    issues.triggered.connect(
        lambda: webbrowser.open(f"{_GITHUB_URL}/issues"))
    hm.addAction(issues)

    hm.addSeparator()

    # About
    about = QAction(f"&About {info['title']}", parent)
    about.triggered.connect(lambda: _show_about(parent, info, version))
    hm.addAction(about)

    return hm


# ---------------------------------------------------------------------------
def _open_doc(rel_path: str, anchor: str = "") -> None:
    """Open a documentation file in the default handler (browser or editor).

    If the file exists on disk, opens it as a file:// URL so Markdown
    renderers (VS Code, Typora) pick it up. If not found, falls back
    to the GitHub URL.
    """
    abs_path = os.path.join(_REPO_ROOT, rel_path)
    if os.path.exists(abs_path):
        url = "file:///" + abs_path.replace("\\", "/")
        if anchor:
            url += anchor
        webbrowser.open(url)
    else:
        webbrowser.open(f"{_GITHUB_URL}/blob/master/{rel_path}{anchor}")


def _show_about(parent, info: dict, version: str) -> None:
    """Show a rich About dialog."""
    QMessageBox.about(
        parent,
        f"About {info['title']}",
        f"<h2>{info['title']}</h2>"
        f"<p><b>Version {version}</b></p>"
        f"<p>{info['description']}</p>"
        f"<hr>"
        f"<p><b>Platform:</b> Azeotrope APC v{version}</p>"
        f"<p><b>License:</b> {_LICENSE}</p>"
        f"<p><b>Author:</b> Nazmul Hasan</p>"
        f"<p><b>Organization:</b> {_ORG}</p>"
        f"<hr>"
        f"<p><small>Built with Python, PySide6, NumPy, SciPy, "
        f"FastAPI, and a C++ optimization core (OSQP + HiGHS).</small></p>"
        f"<p><small>AI assistance by Claude (Anthropic).</small></p>",
    )
