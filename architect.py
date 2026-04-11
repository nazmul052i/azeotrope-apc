#!/usr/bin/env python
"""APC Architect launcher.

Run from the repo root:

    python architect.py
    python architect.py apps/apc_architect/examples/fired_heater.yaml

This script wires the dev source layout (packages/ + apps/) onto sys.path
so the app and shared library can be imported without `pip install -e .`.
After ``pip install -e .`` the entry point in pyproject.toml gives the
same launch via the ``apc-architect`` command.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for sub in ("packages", "apps"):
    p = os.path.join(_ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from apc_architect.app import main  # noqa: E402

if __name__ == "__main__":
    main()
