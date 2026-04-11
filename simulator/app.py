"""Azeotrope APC Simulator -- Entry Point."""
import sys
import os
from PySide6.QtWidgets import QApplication
from .main_window import MainWindow
from .whatif_window import _STYLE
from .models.config_loader import load_config


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(_STYLE)

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
