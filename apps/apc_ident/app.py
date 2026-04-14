"""APC Ident -- entry point.

Step-test model identification studio. Inspired by AspenTech DMC3
Model ID; replaces the standalone identification workflow for the
Azeotrope APC stack.
"""
import os
import sys

from PySide6.QtWidgets import QApplication

from azeoapc.identification import load_ident_project
from azeoapc.theme.ident_theme import get_qss

from .main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(get_qss())
    try:
        from azeoapc.theme import set_window_icon
        set_window_icon(app, "ident")
    except Exception:
        pass
    app.setApplicationName("APC Ident")
    app.setOrganizationName("Azeotrope")

    project = None
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        try:
            project = load_ident_project(sys.argv[1])
        except Exception as e:
            print(f"Error loading project: {e}")

    window = MainWindow(project)
    window.resize(1500, 900)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
