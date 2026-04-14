"""Step-test identification: data conditioning, FIR/SS/TF model container,
MIMO FIR identification, subspace identification, smoothing, diagnostics,
validation, curve operations, model assembly, and analysis tools.

The shared library used by:
  apc_ident       -- the studio app
  apc_architect   -- to consume identified models via the bundle file format
  scripts / CI    -- batch identification jobs

Module inventory:
  control_model       -- TF / SS / FIR discrete-time model container
  fir_ident           -- MIMO FIR identification (DLS/COR/Ridge)
  subspace_ident      -- MIMO subspace state-space ID (N4SID/MOESP/CVA)
  data_conditioner    -- unified conditioning pipeline
  data_conditioning   -- cutoff, flatline, spike detection + replacement
  steady_state        -- dual exponential filter SSD (Aspen IQ algorithm)
  resampling          -- multi-rate analysis with noise/signal trade-off
  data_rules          -- tag-based exclusion + period exclusion + forward-fill
  dynamic_filter      -- dead time + 1st/2nd-order input filtering
  transforms          -- output transforms (log, Box-Cox, PWLN, valve)
  curve_operations    -- 18 DMC3-style operations on step-response curves
  model_assembly      -- pick best curves from multiple trials into final model
  calculated_vectors  -- safe expression evaluator for derived variables
  cross_correlation   -- MV auto/cross-correlation analysis
  model_uncertainty   -- frequency/time domain uncertainty, A/B/C/D grading
  gain_matrix_analysis-- condition number, colinearity, sub-matrix scanning
  multi_trial         -- run multiple identification parameter sets
  bad_slices          -- bad interpolated slices (interpolate vs exclude)
  ramp_cv             -- ramp/pseudoramp CV handling for integrators
  validation          -- model validation (open-loop, one-step-ahead)
  model_bundle        -- HDF5 model bundle I/O
  ident_project       -- YAML project I/O
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
    ModelBundle, bundle_from_ident, bundle_from_subspace,
    bundle_from_assembled, save_model_bundle, load_model_bundle,
    BUNDLE_EXT,
)
from .ident_project import (
    IdentProject, IdentProjectMetadata, TagAssignment,
    save_ident_project, load_ident_project, PROJECT_EXT,
)

# --- Subspace identification ---
from .subspace_ident import (
    SubspaceIdentifier, SubspaceConfig, SubspaceResult, SubspaceMethod,
    identify_ss, WoodBerrySimulator,
)

# --- Industrial data conditioning (Tier 1) ---
from .data_conditioning import (
    ConditioningEngineConfig, ConditioningEngineReport,
    VariableConditionConfig, VariableConditionStats,
    CutoffAction, BadDataMethod,
    auto_configure as auto_configure_conditioning,
    condition_dataframe as condition_dataframe_engine,
    detect_cutoff_violations, detect_flatline, detect_spikes,
    replace_bad_data,
)
from .steady_state import (
    SSDConfig, SSDVariableConfig, SSDResult, SSDVariableResult,
    compute_ssd, compute_ssd_per_variable, compute_ssd_total,
    auto_configure_ssd,
)
from .resampling import (
    ResampleAnalysis, ResampleRateStats, ResampleSuggestion,
    resample_dataframe, analyze_resample_rates, suggest_resample_rate,
)

# --- Industrial data conditioning (Tier 2) ---
from .data_rules import (
    ExclusionRule, ExclusionPeriod, ForwardFillRule, RulesReport,
    apply_exclusion_rules, apply_exclusion_periods,
    apply_forward_fills, apply_all_rules,
)
from .dynamic_filter import (
    VariableFilter,
    first_order_filter, second_order_filter, apply_dead_time,
    apply_filter, auto_tune_filter, auto_tune_all,
    filter_dataframe as filter_dataframe_dynamic,
)
from .transforms import (
    OutputTransform, TransformMethod, TransformCandidate,
    auto_select_transform, evaluate_transforms,
)

# --- Curve operations & model assembly ---
from .curve_operations import (
    CurveOp, CurveOpRecord,
    apply_op, apply_ops_chain,
    op_add, op_subtract, op_gain, op_gscale, op_shift, op_multiply,
    op_rate, op_rscale, op_firstorder, op_secondorder, op_leadlag,
    op_rotate, create_zero, create_unity, create_firstorder,
    create_secondorder, convolute,
)
from .model_assembly import (
    ModelAssembler, AssembledModel, CandidateModel, CellSelection,
)

# --- Calculated vectors ---
from .calculated_vectors import (
    CalculatedTag, evaluate_expression, add_calculated_tags,
)

# --- Analysis tools ---
from .cross_correlation import (
    CorrelationAnalysis, AutoCorrelationResult, CrossCorrelationResult,
    CorrelationGrade, analyze_cross_correlation,
)
from .model_uncertainty import (
    UncertaintyReport, ChannelUncertainty, analyze_uncertainty,
)
from .gain_matrix_analysis import (
    GainMatrixReport, SubMatrixResult, ColinearityPair, ScalingMethod,
    analyze_gain_matrix, compute_rga,
)

# --- Multi-trial ---
from .multi_trial import (
    TrialConfig, TrialResult, TrialComparison,
    define_trials, run_trials_fir, select_best_trial,
)

# --- Bad slices ---
from .bad_slices import (
    BadSlice, BadSliceReport, apply_bad_slices,
)

# --- Ramp/pseudoramp CV handling ---
from .ramp_cv import (
    CVType, RampPreprocessResult,
    detect_cv_type, preprocess_ramp, preprocess_pseudoramp,
    preprocess_cv, ramp_to_step, typical_move_scale,
)

# --- Smart config & quality scorecard ---
from .smart_config import (
    SmartConfigReport, SmartConfigRecommendation, smart_configure,
)
from .quality_scorecard import (
    ModelScorecard, ScorecardCategory, Grade, build_scorecard,
)

# --- DMC file import ---
from .dmc_import import (
    read_vec, read_dep_ind, combine_single_tag_files,
    detect_format, import_data,
)

# --- Batch execution ---
from .batch_execution import (
    BatchCase, BatchCaseResult, BatchReport,
    generate_miso_cases, run_batch, auto_generate_batch,
)

# --- Constrained identification ---
from .constrained_ident import (
    GainConstraint, DeadTimeConstraint, GainRatioConstraint,
    constrained_fir_identify,
)

# --- Reporting ---
from .report_generator import generate_html_report, save_report

# --- Process templates ---
from .process_templates import (
    ProcessTemplate, get_template, list_templates,
)

__all__ = [
    # control_model
    "ControlModel", "from_tf", "from_ss", "from_fir", "from_step_response",
    # fir_ident
    "FIRIdentifier", "IdentConfig", "IdentResult", "IdentMethod",
    "SmoothMethod", "ChannelFit", "identify_fir",
    # subspace_ident
    "SubspaceIdentifier", "SubspaceConfig", "SubspaceResult",
    "SubspaceMethod", "identify_ss", "WoodBerrySimulator",
    # data_conditioner
    "DataConditioner", "ConditioningConfig", "ConditioningResult",
    "ConditioningReport", "Segment",
    # validation
    "validate_model", "validate_model_dual", "compute_excitation",
    "ValidationReport", "DualValidationReport",
    "ChannelMetric", "ExcitationDiagnostic",
    # model_bundle
    "ModelBundle", "bundle_from_ident", "bundle_from_subspace",
    "bundle_from_assembled", "save_model_bundle",
    "load_model_bundle", "BUNDLE_EXT",
    # ident_project
    "IdentProject", "IdentProjectMetadata", "TagAssignment",
    "save_ident_project", "load_ident_project", "PROJECT_EXT",
    # data_conditioning
    "ConditioningEngineConfig", "ConditioningEngineReport",
    "VariableConditionConfig", "VariableConditionStats",
    "CutoffAction", "BadDataMethod",
    "auto_configure_conditioning", "condition_dataframe_engine",
    "detect_cutoff_violations", "detect_flatline", "detect_spikes",
    "replace_bad_data",
    # steady_state
    "SSDConfig", "SSDVariableConfig", "SSDResult", "SSDVariableResult",
    "compute_ssd", "compute_ssd_per_variable", "compute_ssd_total",
    "auto_configure_ssd",
    # resampling
    "ResampleAnalysis", "ResampleRateStats", "ResampleSuggestion",
    "resample_dataframe", "analyze_resample_rates", "suggest_resample_rate",
    # data_rules
    "ExclusionRule", "ExclusionPeriod", "ForwardFillRule", "RulesReport",
    "apply_exclusion_rules", "apply_exclusion_periods",
    "apply_forward_fills", "apply_all_rules",
    # dynamic_filter
    "VariableFilter",
    "first_order_filter", "second_order_filter", "apply_dead_time",
    "apply_filter", "auto_tune_filter", "auto_tune_all",
    "filter_dataframe_dynamic",
    # transforms
    "OutputTransform", "TransformMethod", "TransformCandidate",
    "auto_select_transform", "evaluate_transforms",
    # curve_operations
    "CurveOp", "CurveOpRecord", "apply_op", "apply_ops_chain",
    "op_add", "op_subtract", "op_gain", "op_gscale", "op_shift",
    "op_multiply", "op_rate", "op_rscale", "op_firstorder",
    "op_secondorder", "op_leadlag", "op_rotate",
    "create_zero", "create_unity", "create_firstorder",
    "create_secondorder", "convolute",
    # model_assembly
    "ModelAssembler", "AssembledModel", "CandidateModel", "CellSelection",
    # calculated_vectors
    "CalculatedTag", "evaluate_expression", "add_calculated_tags",
    # cross_correlation
    "CorrelationAnalysis", "AutoCorrelationResult", "CrossCorrelationResult",
    "CorrelationGrade", "analyze_cross_correlation",
    # model_uncertainty
    "UncertaintyReport", "ChannelUncertainty", "analyze_uncertainty",
    # gain_matrix_analysis
    "GainMatrixReport", "SubMatrixResult", "ColinearityPair", "ScalingMethod",
    "analyze_gain_matrix", "compute_rga",
    # multi_trial
    "TrialConfig", "TrialResult", "TrialComparison",
    "define_trials", "run_trials_fir", "select_best_trial",
    # bad_slices
    "BadSlice", "BadSliceReport", "apply_bad_slices",
    # ramp_cv
    "CVType", "RampPreprocessResult",
    "detect_cv_type", "preprocess_ramp", "preprocess_pseudoramp",
    "preprocess_cv", "ramp_to_step", "typical_move_scale",
    # dmc_import
    "read_vec", "read_dep_ind", "combine_single_tag_files",
    "detect_format", "import_data",
    # batch_execution
    "BatchCase", "BatchCaseResult", "BatchReport",
    "generate_miso_cases", "run_batch", "auto_generate_batch",
]
