#!/usr/bin/env python
"""APC Historian launcher.

Run from the repo root:

    python historian.py
    python historian.py --port 8770 --db-path runs/historian/h.db
    python historian.py --retention-days 30

After ``pip install -e .`` use the ``apc-historian`` console script.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for sub in ("packages", "apps"):
    p = os.path.join(_ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from apc_historian.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
