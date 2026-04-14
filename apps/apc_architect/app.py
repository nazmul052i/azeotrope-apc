"""APC Architect -- entry point.

The configuration / tuning / simulation studio. Inspired by AspenTech
DMC3 Builder; replaces the Builder workflow for the Azeotrope APC stack.
"""
import os
import sys

from PySide6.QtWidgets import QApplication

from azeoapc.models.config_loader import load_config
from azeoapc.theme import apply_theme, set_window_icon

from .main_window import MainWindow
from .whatif_window import _STYLE


def main():
    app = QApplication(sys.argv)
    # Install the canonical DeltaV Live Silver chrome FIRST so every
    # widget downstream picks it up. The whatif _STYLE block adds
    # only the named-button overrides on top.
    apply_theme(app)
    set_window_icon(app, "architect")
    app.setStyleSheet(app.styleSheet() + "\n" + _STYLE)
    app.setApplicationName("APC Architect")
    app.setOrganizationName("Azeotrope")

    config = None
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        try:
            config = load_config(sys.argv[1])
        except Exception as e:
            print(f"Error loading config: {e}")

    window = MainWindow(config)
    window.resize(1600, 950)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
