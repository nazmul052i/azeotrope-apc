"""APC Launcher entry point.

A small front-door window that lets you pick which of the five apps
to open. Spawns each one as a subprocess via the corresponding
launcher script at the repo root (architect.py / ident.py / runtime.py
/ historian.py / manager.py).
"""
import os
import sys

from PySide6.QtWidgets import QApplication

from azeoapc.theme import apply_theme, set_window_icon

from .main_window import MainWindow


def _find_repo_root() -> str:
    """Walk up from this file looking for the launcher scripts.

    Lets the launcher work both from the dev source tree (where
    architect.py etc. live two levels up) and from an installed
    location (where they live in sys.prefix/Scripts or wherever
    pyproject put them).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        candidate = os.path.dirname(here)
        if os.path.exists(os.path.join(candidate, "architect.py")):
            return candidate
        here = candidate
    # Fall back to current working directory
    return os.getcwd()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("APC Launcher")
    app.setOrganizationName("Azeotrope")
    apply_theme(app)
    set_window_icon(app, "launcher")

    window = MainWindow(repo_root=_find_repo_root())
    window.resize(1180, 760)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
