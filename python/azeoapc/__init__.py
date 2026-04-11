"""
Azeotrope APC -- Open-Source Advanced Process Control

Three-layer MPC optimization engine with C++ core.
"""

__version__ = "0.1.0"

# C++ bindings will be available after build
try:
    from _azeoapc_core import (
        # Enums
        SolverStatus,
        ControllerMode,
        ObserverMethod,
        # Core model classes
        StepResponseModel,
        DynamicMatrix,
        PredictionEngine,
        DisturbanceObserver,
        ConstraintHandler,
        Scaling,
        StateSpaceModel,
        # Layer configs and results
        Layer1Config,
        Layer1Result,
        Layer1DynamicQP,
        Layer2Config,
        Layer2Result,
        Layer2SSTarget,
        Layer3Config,
        Layer3NLP,
        # Controller
        MPCConfig,
        MPCController,
        ControlOutput,
        ControllerStatus,
        DiagnosticsInfo,
        # Functions
        set_log_level,
    )

    _HAS_CORE = True
except ImportError:
    _HAS_CORE = False


def setup_logging(level: str = "info") -> None:
    """Configure C++ core logging level.

    Args:
        level: One of 'trace', 'debug', 'info', 'warn', 'error', 'off'.
    """
    if not _HAS_CORE:
        raise RuntimeError(
            "C++ core not available. Build with AZEOAPC_BUILD_BINDINGS=ON."
        )
    set_log_level(level)
