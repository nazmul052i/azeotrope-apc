"""Step-test identification: data conditioning, FIR/SS/TF model container,
MIMO FIR identification, smoothing, diagnostics, validation.

The shared library used by:
  apc_ident       -- the studio app (Phase C3+)
  apc_architect   -- to consume identified models via the bundle file format
  scripts / CI    -- batch identification jobs
"""
from .control_model import (
    ControlModel,
    from_tf, from_ss, from_fir, from_step_response,
)
from .fir_ident import (
    FIRIdentifier, IdentConfig, IdentResult, IdentMethod, SmoothMethod,
    ChannelFit, identify_fir,
)
from .data_conditioner import (
    DataConditioner, ConditioningConfig, ConditioningResult,
    ConditioningReport, Segment,
)
from .validation import (
    validate_model, validate_model_dual, compute_excitation,
    ValidationReport, DualValidationReport, ChannelMetric,
    ExcitationDiagnostic,
)
from .model_bundle import (
    ModelBundle, bundle_from_ident, save_model_bundle, load_model_bundle,
    BUNDLE_EXT,
)
from .ident_project import (
    IdentProject, IdentProjectMetadata, TagAssignment,
    save_ident_project, load_ident_project, PROJECT_EXT,
)

__all__ = [
    # control_model
    "ControlModel", "from_tf", "from_ss", "from_fir", "from_step_response",
    # fir_ident
    "FIRIdentifier", "IdentConfig", "IdentResult", "IdentMethod",
    "SmoothMethod", "ChannelFit", "identify_fir",
    # data_conditioner
    "DataConditioner", "ConditioningConfig", "ConditioningResult",
    "ConditioningReport", "Segment",
    # validation
    "validate_model", "validate_model_dual", "compute_excitation",
    "ValidationReport", "DualValidationReport",
    "ChannelMetric", "ExcitationDiagnostic",
    # model_bundle
    "ModelBundle", "bundle_from_ident", "save_model_bundle",
    "load_model_bundle", "BUNDLE_EXT",
    # ident_project
    "IdentProject", "IdentProjectMetadata", "TagAssignment",
    "save_ident_project", "load_ident_project", "PROJECT_EXT",
]
