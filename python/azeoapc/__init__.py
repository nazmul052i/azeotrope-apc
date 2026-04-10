"""
Azeotrope APC -- Open-Source Advanced Process Control

Three-layer DMC optimization engine with C++ core.
"""

__version__ = "0.1.0"

# C++ bindings will be available after build
try:
    from _azeoapc_core import (
        StepResponseModel,
        DynamicMatrix,
        MPCController,
        ControlOutput,
        SolverStatus,
        ControllerMode,
        Storage,
    )
except ImportError:
    pass  # C++ core not built yet
