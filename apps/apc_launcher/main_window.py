"""APC Launcher main window.

A 2x3 grid of cards, one per app. Each card has:
  * Icon + title + one-line description
  * Status dot (idle / running / error)
  * Launch button (and Stop button + Open in Browser for services)

Subprocesses are tracked in ``self._procs`` so we can clean them up
on close. Desktop GUI apps (architect, ident) are spawned and
forgotten -- the user manages those windows themselves. Headless
services (runtime, historian, manager) stay tracked so the launcher
can offer Stop and reflect their running state.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

from azeoapc.theme import SILVER as _SILVER


# ── Palette (backwards-compat key map onto canonical Silver) ───────────────
# Older launcher code uses short names like ``PALETTE["bg_primary"]``,
# ``PALETTE["text_dim"]``, ``PALETTE["bg_card"]``. We route them through
# the canonical palette so a colour change in packages/azeoapc/theme
# propagates here automatically.
PALETTE = {
    "bg_primary":   _SILVER["bg_primary"],
    "bg_card":      _SILVER["bg_secondary"],
    "bg_card_hov":  _SILVER["bg_panel"],
    "bg_input":     _SILVER["bg_input"],
    "bg_header":    _SILVER["bg_header"],
    "border":       _SILVER["border"],
    "text":         _SILVER["text_primary"],
    "text_dim":     _SILVER["text_secondary"],
    "text_muted":   _SILVER["text_muted"],
    "accent_blue":  _SILVER["accent_blue"],
    "accent_green": _SILVER["accent_green"],
    "accent_orange":_SILVER["accent_orange"],
    "accent_red":   _SILVER["accent_red"],
    "accent_cyan":  _SILVER["accent_cyan"],
    "accent_purple":_SILVER["accent_purple"],
}


# ── App descriptors ───────────────────────────────────────────────────────
@dataclass
class AppSpec:
    """Static description of one app the launcher can run."""
    key: str
    title: str
    icon: str
    color: str
    description: str
    launcher_script: str          # path relative to repo root
    is_service: bool = False      # services get Stop + Browser buttons
    service_url: str = ""         # template URL once running
    needs_config: bool = False    # show a config-path field
    default_config: str = ""      # default value for the config field


def _build_apps(repo_root: str) -> List[AppSpec]:
    """Apps in workflow order: identify the model, configure the
    controller, run it, store the data, watch it from the operator
    console."""
    examples = os.path.join(repo_root, "apps", "apc_architect", "examples",
                             "fired_heater.yaml")
    return [
        # ── 1. Identify a model from step-test data ──
        AppSpec(
            key="ident",
            title="APC Ident",
            icon="\u0192",   # ƒ
            color=PALETTE["accent_purple"],
            description=(
                "Step-test model identification studio. Loads CSV, "
                "auto-conditions data, runs FIR identification, exports "
                "model bundles for the architect."
            ),
            launcher_script="ident.py",
        ),
        # ── 2. Configure the controller around the identified model ──
        AppSpec(
            key="architect",
            title="APC Architect",
            icon="\u2630",   # ☰
            color=PALETTE["accent_blue"],
            description=(
                "Configuration, tuning, calculations, simulation, and "
                "deployment studio. The DMC3 Builder equivalent."
            ),
            launcher_script="architect.py",
        ),
        # ── 3. Run the controller (Aspen Watch Maker style desktop) ──
        AppSpec(
            key="runtime",
            title="APC Runtime",
            icon="\u26A1",   # ⚡
            color=PALETTE["accent_orange"],
            description=(
                "Desktop controller manager (Aspen Watch Maker style). "
                "Lists every loaded controller in a table with Start / "
                "Stop / Pause actions. Auto-starts the historian "
                "alongside so every cycle is forwarded into the store."
            ),
            launcher_script="runtime.py",
            # Runtime is now a desktop app (with REST + historian
            # forwarding still running on a background thread inside
            # the same process), so the launcher treats it like
            # architect / ident: fire-and-forget, no Stop button.
            is_service=False,
            needs_config=True,
            default_config=examples if os.path.exists(examples) else "",
        ),
        # ── 4. Centralised data store ──
        AppSpec(
            key="historian",
            title="APC Historian",
            icon="\u25A4",   # ▤
            color=PALETTE["accent_cyan"],
            description=(
                "Centralised cycle store + REST query service. "
                "Aggregates data from multiple runtimes, computes KPIs, "
                "applies retention policy."
            ),
            launcher_script="historian.py",
            is_service=True,
            service_url="http://127.0.0.1:8770",
        ),
        # ── 5. Operator web console ──
        AppSpec(
            key="manager",
            title="APC Manager",
            icon="\u25C9",   # ◉
            color=PALETTE["accent_green"],
            description=(
                "Operator web console (PCWS equivalent). Live status, "
                "Plotly trends from the historian, push setpoint and "
                "tuning changes."
            ),
            launcher_script="manager.py",
            is_service=True,
            service_url="http://127.0.0.1:8780",
        ),
    ]


# ── Card widget ───────────────────────────────────────────────────────────
class AppCard(QFrame):
    """One tile in the launcher grid."""

    def __init__(self, spec: AppSpec, on_launch: Callable[[AppSpec, "AppCard"], None],
                  on_stop: Callable[[AppSpec, "AppCard"], None],
                  on_browse_config: Callable[["AppCard"], None]):
        super().__init__()
        self.spec = spec
        self._on_launch = on_launch
        self._on_stop = on_stop
        self._on_browse_config = on_browse_config
        self._running = False
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(self._card_qss(False))
        self.setMinimumSize(330, 250)
        self._build()

    def _card_qss(self, hover: bool) -> str:
        bg = PALETTE["bg_card_hov"] if hover else PALETTE["bg_card"]
        return (
            f"AppCard {{ background: {bg}; "
            f"border: 1px solid {PALETTE['border']}; "
            f"border-left: 4px solid {self.spec.color}; "
            f"border-radius: 4px; }}"
        )

    # ------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        # Top row: icon + title + status dot
        head = QHBoxLayout()
        head.setSpacing(10)
        icon = QLabel(self.spec.icon)
        icon.setStyleSheet(
            f"color: {self.spec.color}; font-size: 22pt; "
            f"font-weight: bold;")
        head.addWidget(icon)

        title = QLabel(self.spec.title)
        title.setStyleSheet(
            f"color: {PALETTE['text']}; font-size: 13pt; "
            f"font-weight: 700; letter-spacing: 0.5px;")
        head.addWidget(title)
        head.addStretch()

        self.status_dot = QLabel("\u25CF")
        self.status_dot.setStyleSheet(
            f"color: {PALETTE['text_muted']}; font-size: 14pt;")
        head.addWidget(self.status_dot)
        self.status_text = QLabel("IDLE")
        self.status_text.setStyleSheet(
            f"color: {PALETTE['text_muted']}; font-size: 8pt; "
            f"font-weight: 700; letter-spacing: 1px;")
        head.addWidget(self.status_text)

        root.addLayout(head)

        # Description
        desc = QLabel(self.spec.description)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {PALETTE['text_dim']}; font-size: 9pt; "
            f"line-height: 1.4;")
        root.addWidget(desc)

        # Optional config field (runtime needs a YAML)
        if self.spec.needs_config:
            cfg_row = QHBoxLayout()
            cfg_row.setSpacing(4)
            self.config_edit = QLineEdit(self.spec.default_config)
            self.config_edit.setPlaceholderText("path/to/config.yaml")
            self.config_edit.setStyleSheet(
                f"QLineEdit {{ background: {PALETTE['bg_input']}; "
                f"color: {PALETTE['text']}; "
                f"border: 1px solid {PALETTE['border']}; "
                f"padding: 4px 6px; font-size: 9pt;"
                f" font-family: Consolas; }}")
            cfg_row.addWidget(self.config_edit, 1)

            browse = QPushButton("...")
            browse.setMaximumWidth(30)
            browse.setStyleSheet(self._button_qss(secondary=True))
            browse.clicked.connect(lambda: self._on_browse_config(self))
            cfg_row.addWidget(browse)

            root.addLayout(cfg_row)
        else:
            self.config_edit = None

        # URL line for services
        if self.spec.is_service:
            self.url_label = QLabel(f"URL: {self.spec.service_url}")
            self.url_label.setStyleSheet(
                f"color: {PALETTE['text_muted']}; "
                f"font-size: 9pt; font-family: Consolas;")
            root.addWidget(self.url_label)
        else:
            self.url_label = None

        root.addStretch()

        # Action buttons row
        actions = QHBoxLayout()
        actions.setSpacing(6)

        self.launch_btn = QPushButton("Launch")
        self.launch_btn.setStyleSheet(self._button_qss(color=self.spec.color))
        self.launch_btn.clicked.connect(self._handle_launch)
        actions.addWidget(self.launch_btn)

        if self.spec.is_service:
            self.browser_btn = QPushButton("Open in Browser")
            self.browser_btn.setStyleSheet(self._button_qss(secondary=True))
            self.browser_btn.clicked.connect(self._handle_browser)
            self.browser_btn.setEnabled(False)
            actions.addWidget(self.browser_btn)

            self.stop_btn = QPushButton("Stop")
            self.stop_btn.setStyleSheet(
                self._button_qss(color=PALETTE["accent_red"]))
            self.stop_btn.clicked.connect(self._handle_stop)
            self.stop_btn.setEnabled(False)
            actions.addWidget(self.stop_btn)
        else:
            self.browser_btn = None
            self.stop_btn = None

        actions.addStretch()
        root.addLayout(actions)

    # ------------------------------------------------------------------
    def _button_qss(self, *, color: Optional[str] = None,
                     secondary: bool = False) -> str:
        if secondary:
            bg = PALETTE["bg_header"]
            fg = PALETTE["text"]
            border = PALETTE["border"]
            hover = PALETTE["bg_card_hov"]
        else:
            # Coloured action buttons (Launch / Stop) -- white text on
            # the accent fill, picked from the canonical palette so
            # the launcher matches the rest of the stack.
            bg = color or PALETTE["accent_blue"]
            fg = "#FFFFFF"
            border = bg
            hover = bg
        return (
            f"QPushButton {{ background: {bg}; color: {fg}; "
            f"border: 1px solid {border}; padding: 6px 16px; "
            f"font-size: 9pt; font-weight: 700; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
            f"QPushButton:disabled {{ background: {PALETTE['bg_header']}; "
            f"color: {PALETTE['text_muted']}; }}"
        )

    # ------------------------------------------------------------------
    def _handle_launch(self):
        self._on_launch(self.spec, self)

    def _handle_stop(self):
        self._on_stop(self.spec, self)

    def _handle_browser(self):
        if self.url_label:
            webbrowser.open(self.spec.service_url)

    # ------------------------------------------------------------------
    def set_running(self, running: bool, *, error: bool = False):
        """Update the status dot + button states."""
        self._running = running
        if error:
            self.status_dot.setStyleSheet(
                f"color: {PALETTE['accent_red']}; font-size: 14pt;")
            self.status_text.setText("ERROR")
            self.status_text.setStyleSheet(
                f"color: {PALETTE['accent_red']}; font-size: 8pt; "
                f"font-weight: 700; letter-spacing: 1px;")
        elif running:
            self.status_dot.setStyleSheet(
                f"color: {PALETTE['accent_green']}; font-size: 14pt;")
            self.status_text.setText("RUNNING")
            self.status_text.setStyleSheet(
                f"color: {PALETTE['accent_green']}; font-size: 8pt; "
                f"font-weight: 700; letter-spacing: 1px;")
        else:
            self.status_dot.setStyleSheet(
                f"color: {PALETTE['text_muted']}; font-size: 14pt;")
            self.status_text.setText("IDLE")
            self.status_text.setStyleSheet(
                f"color: {PALETTE['text_muted']}; font-size: 8pt; "
                f"font-weight: 700; letter-spacing: 1px;")

        if self.spec.is_service:
            self.launch_btn.setEnabled(not running)
            if self.browser_btn is not None:
                self.browser_btn.setEnabled(running)
            if self.stop_btn is not None:
                self.stop_btn.setEnabled(running)


# ── Main window ────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    """The launcher window itself."""

    def __init__(self, repo_root: str, parent=None):
        super().__init__(parent)
        self.repo_root = repo_root
        self.setWindowTitle("Azeotrope APC Launcher")
        self.setMinimumSize(1100, 720)

        # name -> (Popen, AppSpec, AppCard)
        self._procs: Dict[str, tuple] = {}

        self._build_ui()
        self._build_help_menu()

        # Periodic poll to detect crashed children
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_children)
        self._poll_timer.start()

    # ==================================================================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(28, 22, 28, 22)
        body_lay.setSpacing(12)

        # Section heading
        heading = QLabel("Choose an app to open")
        heading.setStyleSheet(
            f"color: {PALETTE['text']}; font-size: 14pt; "
            f"font-weight: 600;")
        body_lay.addWidget(heading)

        sub = QLabel(
            "Desktop studios run as standalone windows. Services run "
            "as background processes -- launch them here and the "
            "launcher will track their state."
        )
        sub.setStyleSheet(
            f"color: {PALETTE['text_dim']}; font-size: 10pt;")
        sub.setWordWrap(True)
        body_lay.addWidget(sub)
        body_lay.addSpacing(10)

        # Card grid
        grid = QGridLayout()
        grid.setSpacing(14)
        body_lay.addLayout(grid, 1)

        self.cards: Dict[str, AppCard] = {}
        for i, spec in enumerate(_build_apps(self.repo_root)):
            card = AppCard(
                spec,
                on_launch=self._launch_app,
                on_stop=self._stop_app,
                on_browse_config=self._browse_config,
            )
            self.cards[spec.key] = card
            row, col = divmod(i, 3)
            grid.addWidget(card, row, col)

        body_lay.addStretch()
        root.addWidget(body, 1)

        # Status bar
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background: {PALETTE['bg_card']}; "
            f"color: {PALETTE['text_dim']}; "
            f"border-top: 1px solid {PALETTE['border']}; }}")
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    def _build_help_menu(self):
        from azeoapc.theme.help_menu import build_help_menu
        build_help_menu(self.menuBar(), "launcher", self,
                         include_mpc_theory=True,
                         include_ident_theory=True)

    # ------------------------------------------------------------------
    def _build_header(self):
        header = QFrame()
        header.setFixedHeight(56)
        header.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg_card']}; "
            f"border-bottom: 1px solid {PALETTE['border']}; }}")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(28, 0, 28, 0)
        lay.setSpacing(14)

        icon = QLabel("\u25C6")
        icon.setStyleSheet(
            f"color: {PALETTE['accent_blue']}; font-size: 22pt; "
            f"font-weight: bold;")
        lay.addWidget(icon)

        brand = QLabel("AZEOTROPE APC")
        brand.setStyleSheet(
            f"color: {PALETTE['text']}; font-size: 14pt; "
            f"font-weight: 700; letter-spacing: 2px;")
        lay.addWidget(brand)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: {PALETTE['text_muted']}; font-size: 16pt;")
        lay.addWidget(sep)

        sub = QLabel("Launcher")
        sub.setStyleSheet(
            f"color: {PALETTE['text_dim']}; font-size: 11pt; "
            f"font-weight: 500;")
        lay.addWidget(sub)

        lay.addStretch()

        version = QLabel("v0.1.0")
        version.setStyleSheet(
            f"color: {PALETTE['text_muted']}; font-size: 9pt;")
        lay.addWidget(version)

        return header

    # ==================================================================
    # Process management
    # ==================================================================
    HISTORIAN_URL = "http://127.0.0.1:8770"

    def _launch_app(self, spec: AppSpec, card: AppCard) -> None:
        """Launch ``spec``. The runtime card auto-starts the historian
        first so every cycle is forwarded into the centralised store
        without the operator having to remember to start it."""

        # Validate config path early so we don't auto-start the
        # historian and then fail to start the runtime.
        config_arg: Optional[str] = None
        if spec.needs_config and card.config_edit is not None:
            cfg = card.config_edit.text().strip()
            if cfg:
                if not os.path.exists(cfg):
                    QMessageBox.warning(
                        self, "Config not found",
                        f"The config file does not exist:\n{cfg}")
                    return
                config_arg = cfg

        # Auto-start the historian when the runtime is launched.
        extra_args: List[str] = []
        if spec.key == "runtime":
            if not self._ensure_historian_running():
                # User cancelled or it failed to come up
                return
            extra_args = ["--historian-url", self.HISTORIAN_URL]

        proc = self._spawn_subprocess(spec, config_arg, extra_args)
        if proc is None:
            return

        self._procs[spec.key] = (proc, spec, card)
        if spec.is_service:
            card.set_running(True)
            msg = f"{spec.title} started (PID {proc.pid})"
            self.statusBar().showMessage(msg, 6000)
        else:
            # Desktop app: not tracked as 'running' since the user
            # owns the lifecycle. Brief status flash.
            msg = f"{spec.title} launched (PID {proc.pid})"
            if spec.key == "runtime":
                msg += "  --  historian started + cycles will forward"
            self.statusBar().showMessage(msg, 6000)
            QTimer.singleShot(
                2000, lambda key=spec.key: self._forget_proc(key))

    # ------------------------------------------------------------------
    def _spawn_subprocess(self, spec: AppSpec, config_arg: Optional[str],
                           extra_args: List[str]) -> Optional[subprocess.Popen]:
        """Resolve the launcher script and spawn it. Returns the Popen
        on success, None on failure (with a message box already shown)."""
        script = os.path.join(self.repo_root, spec.launcher_script)
        if not os.path.exists(script):
            QMessageBox.critical(
                self, "Launch failed",
                f"Launcher script not found:\n{script}")
            return None

        args: List[str] = [sys.executable, script]
        if config_arg:
            args.append(config_arg)
        args.extend(extra_args)

        try:
            return subprocess.Popen(args, cwd=self.repo_root)
        except Exception as e:
            QMessageBox.critical(
                self, "Launch failed",
                f"Could not start {spec.title}:\n{type(e).__name__}: {e}")
            return None

    # ------------------------------------------------------------------
    def _ensure_historian_running(self) -> bool:
        """Make sure the historian is up. If we already started it,
        nothing to do. Otherwise spawn it and wait for /healthz."""
        # Already tracked + still alive?
        entry = self._procs.get("historian")
        if entry is not None:
            proc, _, _ = entry
            if proc.poll() is None:
                return True
            # Tracked but dead -- forget the stale entry and respawn
            self._procs.pop("historian", None)

        # Spawn historian
        hist_card = self.cards.get("historian")
        if hist_card is None:
            return False
        self.statusBar().showMessage(
            "Starting historian (auto)...", 4000)
        proc = self._spawn_subprocess(hist_card.spec, None, [])
        if proc is None:
            return False
        self._procs["historian"] = (proc, hist_card.spec, hist_card)
        hist_card.set_running(True)

        # Wait for the REST surface to come up. Use the Qt event loop
        # so the GUI stays responsive while we poll.
        if not self._wait_for_url(self.HISTORIAN_URL + "/healthz",
                                    timeout_sec=10.0):
            QMessageBox.warning(
                self, "Historian slow to start",
                "The historian process started but its REST surface did "
                "not become reachable within 10 seconds. The runtime "
                "will still be launched but cycle forwarding may fail "
                "until the historian is ready.")
        return True

    # ------------------------------------------------------------------
    @staticmethod
    def _wait_for_url(url: str, *, timeout_sec: float = 10.0) -> bool:
        """Block-poll a URL until it returns 2xx or the timeout elapses.

        Spins the Qt event loop so the GUI stays responsive. Returns
        True on success, False on timeout.
        """
        import time
        import urllib.error
        import urllib.request

        from PySide6.QtCore import QEventLoop

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=0.5) as r:
                    if 200 <= r.status < 300:
                        return True
            except (urllib.error.URLError, urllib.error.HTTPError, OSError):
                pass
            # Sleep ~150 ms but keep the GUI responsive
            loop = QEventLoop()
            QTimer.singleShot(150, loop.quit)
            loop.exec()
        return False

    def _forget_proc(self, key: str):
        self._procs.pop(key, None)

    # ------------------------------------------------------------------
    def _stop_app(self, spec: AppSpec, card: AppCard) -> None:
        entry = self._procs.get(spec.key)
        if entry is None:
            card.set_running(False)
            return
        proc, _, _ = entry
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
        except Exception as e:
            self.statusBar().showMessage(
                f"Could not stop {spec.title}: {e}", 5000)
        self._procs.pop(spec.key, None)
        card.set_running(False)
        self.statusBar().showMessage(f"{spec.title} stopped", 4000)

    # ------------------------------------------------------------------
    def _browse_config(self, card: AppCard) -> None:
        if card.config_edit is None:
            return
        start = (card.config_edit.text()
                 or os.path.join(self.repo_root, "apps", "apc_architect",
                                  "examples"))
        if not os.path.isdir(start):
            start = os.path.dirname(start) or self.repo_root
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick controller config", start,
            "Controller (*.yaml *.yml *.apcproj);;All Files (*)")
        if path:
            card.config_edit.setText(path)

    # ------------------------------------------------------------------
    def _poll_children(self) -> None:
        """Detect children that exited on their own and update cards."""
        dead: List[str] = []
        for key, (proc, spec, card) in self._procs.items():
            if proc.poll() is not None:
                dead.append(key)
                if spec.is_service:
                    rc = proc.returncode
                    error = rc != 0 and rc is not None
                    card.set_running(False, error=error)
                    self.statusBar().showMessage(
                        f"{spec.title} exited (rc={rc})", 6000)
        for key in dead:
            self._procs.pop(key, None)

    # ==================================================================
    def closeEvent(self, event):
        services_running = [
            (spec, card) for (proc, spec, card) in self._procs.values()
            if spec.is_service and proc.poll() is None
        ]
        if services_running:
            names = ", ".join(s.title for s, _ in services_running)
            reply = QMessageBox.question(
                self, "Stop services?",
                f"The following services are still running:\n\n  {names}\n\n"
                "Stop them before exiting?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Yes:
                for spec, card in services_running:
                    self._stop_app(spec, card)
        super().closeEvent(event)
