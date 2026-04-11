#!/usr/bin/env python
"""APC Manager launcher.

Run from the repo root:

    python manager.py
    python manager.py --runtime-url http://localhost:8765 \
                      --historian-url http://localhost:8770

After ``pip install -e .`` use the ``apc-manager`` console script.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for sub in ("packages", "apps"):
    p = os.path.join(_ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from apc_manager.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
