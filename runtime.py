#!/usr/bin/env python
"""APC Runtime launcher.

Run from the repo root:

    python runtime.py path/to/controller.apcproj
    python runtime.py *.apcproj --no-rest
    python runtime.py fired_heater.yaml --rest-port 8765 --wall-period 0.5

Wires the dev source layout (packages/ + apps/) onto sys.path so the
runtime can be launched without ``pip install -e .``. After install,
the entry point in pyproject.toml gives the same launch via the
``apc-runtime`` command.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for sub in ("packages", "apps"):
    p = os.path.join(_ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from apc_runtime.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
