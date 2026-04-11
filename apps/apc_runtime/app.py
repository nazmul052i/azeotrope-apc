"""apc-runtime entry point.

This thin wrapper exists so the pyproject.toml script entry can point
at a stable ``apc_runtime.app:main`` symbol while the real argparse
lives in ``cli.py``.
"""
from .cli import main

__all__ = ["main"]
