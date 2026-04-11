#!/usr/bin/env python
"""APC Ident launcher.

Run from the repo root:

    python ident.py
    python ident.py path/to/project.apcident

Wires the dev source layout (packages/ + apps/) onto sys.path so the
app and shared library can be imported without ``pip install -e .``.
After install, the entry point in pyproject.toml gives the same launch
via the ``apc-ident`` command.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for sub in ("packages", "apps"):
    p = os.path.join(_ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from apc_ident.app import main  # noqa: E402

if __name__ == "__main__":
    main()
