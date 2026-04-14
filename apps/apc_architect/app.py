"""APC Architect -- entry point.

The configuration / tuning / simulation studio. Inspired by AspenTech
DMC3 Builder; replaces the Builder workflow for the Azeotrope APC stack.
"""
import os
import sys

from PySide6.QtWidgets import QApplication

from azeoapc.models.config_loader import load_config
from azeoapc.theme.ident_theme import get_qss

from .main_window import MainWindow
from .whatif_window import _STYLE


def main():
    app = QApplication(sys.argv)
    # ISA-101 Silver theme + whatif button overrides
    app.setStyleSheet(get_qss() + "\n" + _STYLE)
    try:
        from azeoapc.theme import set_window_icon
        set_window_icon(app, "architect")
    except Exception:
        pass
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
