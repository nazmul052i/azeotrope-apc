#!/usr/bin/env python
"""APC Launcher launcher.

Run from the repo root:

    python launcher.py

Opens a small window that lets you pick which of the five apps to
open: architect, ident, runtime, historian, manager. Wires the dev
source layout (packages/ + apps/) onto sys.path so the launcher and
the apps it spawns all import correctly without ``pip install -e .``.

After install, the entry point in pyproject.toml gives the same
launch via the ``apc-launcher`` command.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for sub in ("packages", "apps"):
    p = os.path.join(_ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from apc_launcher.app import main  # noqa: E402

if __name__ == "__main__":
    main()
