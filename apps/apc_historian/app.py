"""apc-historian entry point.

Stable ``apc_historian.app:main`` symbol for the pyproject script.
The argparse + main loop live in ``cli.py``.
"""
from .cli import main

__all__ = ["main"]
