"""Ident project file (.apcident) -- the persistent state of one identification job.

This is what an engineer **opens** in the apc_ident studio. It captures
the data source, the segments they marked as "good", how they bound CSV
columns to controller tags, the conditioning + ident knobs, and a
pointer to the most recent exported model bundle. Reopening reproduces
the entire workspace.

Format: a single YAML file with a ``project:`` header (mirroring the
``.apcproj`` shape from Phase B). Lives next to its CSV / bundle so a
"project folder" is just a directory full of related files:

    cdu_2026_04/
      cdu_step_test.csv
      cdu_furnace.apcident       <- the project file
      cdu_furnace.apcmodel       <- last exported bundle
      runs/
        cdu_furnace_2026-04-09_14-30.apcmodel
        cdu_furnace_2026-04-10_09-15.apcmodel
"""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from .data_conditioner import ConditioningConfig, Segment
from .fir_ident import IdentConfig, IdentMethod, SmoothMethod


SCHEMA_VERSION = 1
PROJECT_EXT = ".apcident"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class IdentProjectMetadata:
    """Header for an .apcident file. Same shape as .apcproj's project header."""
    schema_version: int = SCHEMA_VERSION
    name: str = ""
    author: str = ""
    created: str = ""
    modified: str = ""
    apc_ident_version: str = "0.1.0"
    notes: str = ""


@dataclass
class TagAssignment:
    """Bind a CSV column to a controller variable + role."""
    column: str
    role: str = "Ignore"            # MV | CV | DV | Ignore
    controller_tag: str = ""        # e.g. "TI-201.PV"


@dataclass
class IdentProject:
    """The full state of one identification job."""
    metadata: IdentProjectMetadata = field(default_factory=IdentProjectMetadata)

    # Data source
    data_source_path: str = ""           # relative or absolute CSV / parquet path
    timestamp_col: str = ""

    # Engineer's marked windows
    segments: List[Segment] = field(default_factory=list)

    # Tag bindings (one per CSV column the user touched)
    tag_assignments: List[TagAssignment] = field(default_factory=list)

    # Pipeline configs
    conditioning: ConditioningConfig = field(default_factory=ConditioningConfig)
    ident: IdentConfig = field(default_factory=IdentConfig)

    # Last exported bundle (the canonical handoff to apc_architect)
    last_bundle_path: str = ""

    # --- Extended state (added for commercial completeness) ---
    # Identification engine: "fir" or "subspace"
    ident_engine: str = "fir"

    # Per-CV type overrides: column_name -> "none" | "ramp" | "pseudoramp"
    cv_types: Dict[str, str] = field(default_factory=dict)

    # Calculated vectors: list of {name, expression, unit}
    calculated_vectors: List[Dict[str, str]] = field(default_factory=list)

    # Subspace config (if engine == "subspace")
    subspace_config: Dict[str, Any] = field(default_factory=dict)

    # Bookkeeping (not persisted under "project:")
    source_path: Optional[str] = None    # absolute path the .apcident was loaded from

    # Convenience accessors -------------------------------------------------
    def mv_columns(self) -> List[str]:
        return [t.column for t in self.tag_assignments if t.role == "MV"]

    def cv_columns(self) -> List[str]:
        return [t.column for t in self.tag_assignments if t.role == "CV"]

    def dv_columns(self) -> List[str]:
        return [t.column for t in self.tag_assignments if t.role == "DV"]

    def controller_tag_for(self, column: str) -> str:
        for t in self.tag_assignments:
            if t.column == column:
                return t.controller_tag
        return ""


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
def save_ident_project(p: IdentProject, path: str) -> None:
    """Write an IdentProject to a .apcident YAML file."""
    abs_path = os.path.abspath(path)
    new_dir = os.path.dirname(abs_path) or "."
    os.makedirs(new_dir, exist_ok=True)

    now = datetime.datetime.now().isoformat(timespec="seconds")
    if not p.metadata.created:
        p.metadata.created = now
    p.metadata.modified = now
    p.metadata.schema_version = SCHEMA_VERSION

    raw: Dict[str, Any] = {
        "project": _meta_to_dict(p.metadata),
        "data_source": {
            "path": _rebase_for_save(p.data_source_path, p.source_path, abs_path),
            "timestamp_col": p.timestamp_col,
        },
        "segments": [_segment_to_dict(s) for s in p.segments],
        "tag_assignments": [_tag_to_dict(t) for t in p.tag_assignments],
        "conditioning": _conditioning_to_dict(p.conditioning),
        "identification": _ident_to_dict(p.ident),
        "last_bundle_path": _rebase_for_save(p.last_bundle_path,
                                              p.source_path, abs_path),
        # Extended state
        "ident_engine": p.ident_engine,
        "cv_types": dict(p.cv_types) if p.cv_types else {},
        "calculated_vectors": list(p.calculated_vectors),
        "subspace_config": dict(p.subspace_config) if p.subspace_config else {},
    }

    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(_HEADER_COMMENT)
        yaml.safe_dump(
            raw, f, sort_keys=False, default_flow_style=False, indent=2,
            allow_unicode=True, width=100,
        )

    p.source_path = abs_path


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load_ident_project(path: str) -> IdentProject:
    """Load a .apcident YAML file into an IdentProject."""
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f".apcident not found: {abs_path}")

    with open(abs_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    p = IdentProject()
    p.source_path = abs_path
    p.metadata = _meta_from_dict(raw.get("project", {}) or {})

    ds = raw.get("data_source", {}) or {}
    p.data_source_path = ds.get("path", "")
    p.timestamp_col = ds.get("timestamp_col", "")

    p.segments = [_segment_from_dict(s) for s in raw.get("segments", []) or []]
    p.tag_assignments = [_tag_from_dict(t)
                         for t in raw.get("tag_assignments", []) or []]
    p.conditioning = _conditioning_from_dict(raw.get("conditioning", {}) or {})
    p.ident = _ident_from_dict(raw.get("identification", {}) or {})
    p.last_bundle_path = raw.get("last_bundle_path", "") or ""

    # Extended state (backwards-compatible: missing keys use defaults)
    p.ident_engine = raw.get("ident_engine", "fir") or "fir"
    p.cv_types = dict(raw.get("cv_types", {}) or {})
    p.calculated_vectors = list(raw.get("calculated_vectors", []) or [])
    p.subspace_config = dict(raw.get("subspace_config", {}) or {})

    return p


# ---------------------------------------------------------------------------
# YAML serialisation helpers
# ---------------------------------------------------------------------------
_HEADER_COMMENT = (
    "# Azeotrope APC identification project file (.apcident)\n"
    "# Generated by apc_ident -- safe to edit by hand.\n"
    "# Schema version: 1\n\n"
)


def _meta_to_dict(m: IdentProjectMetadata) -> Dict[str, Any]:
    return {
        "schema_version": int(m.schema_version),
        "name": m.name,
        "author": m.author,
        "created": m.created,
        "modified": m.modified,
        "apc_ident_version": m.apc_ident_version,
        "notes": m.notes,
    }


def _meta_from_dict(d: Dict[str, Any]) -> IdentProjectMetadata:
    return IdentProjectMetadata(
        schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
        name=d.get("name", ""),
        author=d.get("author", ""),
        created=d.get("created", ""),
        modified=d.get("modified", ""),
        apc_ident_version=d.get("apc_ident_version", "0.1.0"),
        notes=d.get("notes", ""),
    )


def _segment_to_dict(s: Segment) -> Dict[str, Any]:
    return {
        "name": s.name,
        "start": _ts_to_str(s.start),
        "end": _ts_to_str(s.end),
        "excluded_ranges": [
            [_ts_to_str(a), _ts_to_str(b)] for a, b in s.excluded_ranges
        ],
    }


def _segment_from_dict(d: Dict[str, Any]) -> Segment:
    return Segment(
        name=d.get("name", ""),
        start=d.get("start"),
        end=d.get("end"),
        excluded_ranges=[
            (pair[0], pair[1]) for pair in d.get("excluded_ranges", []) or []
        ],
    )


def _tag_to_dict(t: TagAssignment) -> Dict[str, Any]:
    return {
        "column": t.column,
        "role": t.role,
        "controller_tag": t.controller_tag,
    }


def _tag_from_dict(d: Dict[str, Any]) -> TagAssignment:
    return TagAssignment(
        column=d.get("column", ""),
        role=d.get("role", "Ignore"),
        controller_tag=d.get("controller_tag", ""),
    )


def _conditioning_to_dict(c: ConditioningConfig) -> Dict[str, Any]:
    return {
        "resample_period_sec": c.resample_period_sec,
        "resample_aggregator": c.resample_aggregator,
        "fillna_method": c.fillna_method,
        "clip_sigma": float(c.clip_sigma),
        "quality_col": c.quality_col,
        "quality_good_value": c.quality_good_value,
        "holdout_fraction": float(c.holdout_fraction),
    }


def _conditioning_from_dict(d: Dict[str, Any]) -> ConditioningConfig:
    return ConditioningConfig(
        resample_period_sec=d.get("resample_period_sec"),
        resample_aggregator=d.get("resample_aggregator", "mean"),
        fillna_method=d.get("fillna_method", "ffill"),
        clip_sigma=float(d.get("clip_sigma", 4.0)),
        quality_col=d.get("quality_col"),
        quality_good_value=d.get("quality_good_value", "GOOD"),
        holdout_fraction=float(d.get("holdout_fraction", 0.0)),
    )


def _ident_to_dict(c: IdentConfig) -> Dict[str, Any]:
    return {
        "n_coeff": int(c.n_coeff),
        "dt_seconds": float(c.dt),
        "method": c.method.value,
        "ridge_alpha": float(c.ridge_alpha),
        "prewhiten": bool(c.prewhiten),
        "detrend": bool(c.detrend),
        "remove_mean": bool(c.remove_mean),
        "confidence_level": float(c.confidence_level),
        "smooth": c.smooth.value,
        "smooth_savgol_window": int(c.smooth_savgol_window),
        "smooth_savgol_order": int(c.smooth_savgol_order),
        "smooth_exp_tau": c.smooth_exp_tau,
        "smooth_exp_start": float(c.smooth_exp_start),
        "smooth_asym_start": float(c.smooth_asym_start),
        "ljung_box_lags": int(c.ljung_box_lags),
    }


def _ident_from_dict(d: Dict[str, Any]) -> IdentConfig:
    return IdentConfig(
        n_coeff=int(d.get("n_coeff", 60)),
        dt=float(d.get("dt_seconds", 1.0)),
        method=IdentMethod(d.get("method", "dls")),
        ridge_alpha=float(d.get("ridge_alpha", 1.0)),
        prewhiten=bool(d.get("prewhiten", False)),
        detrend=bool(d.get("detrend", True)),
        remove_mean=bool(d.get("remove_mean", True)),
        confidence_level=float(d.get("confidence_level", 0.95)),
        smooth=SmoothMethod(d.get("smooth", "pipeline")),
        smooth_savgol_window=int(d.get("smooth_savgol_window", 11)),
        smooth_savgol_order=int(d.get("smooth_savgol_order", 3)),
        smooth_exp_tau=d.get("smooth_exp_tau"),
        smooth_exp_start=float(d.get("smooth_exp_start", 0.6)),
        smooth_asym_start=float(d.get("smooth_asym_start", 0.75)),
        ljung_box_lags=int(d.get("ljung_box_lags", 20)),
    )


def _ts_to_str(v):
    """Render a Segment timestamp for YAML.

    Pandas Timestamps and datetime instances are converted to ISO strings;
    integer offsets stay as ints; None stays None.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        import pandas as pd
        if isinstance(v, pd.Timestamp):
            return v.isoformat()
    except Exception:
        pass
    if isinstance(v, datetime.datetime):
        return v.isoformat()
    return str(v)


def _rebase_for_save(value: str, old_path: Optional[str], new_path: str) -> str:
    """Rewrite a relative path so it remains valid after Save As to a new dir.

    Mirrors the helper in apc_architect's config_loader: resolve against the
    OLD project dir, then make relative to the NEW project dir.
    """
    if not value:
        return value
    if os.path.isabs(value):
        return value
    if not old_path:
        return value
    new_dir = os.path.dirname(os.path.abspath(new_path))
    old_dir = os.path.dirname(os.path.abspath(old_path))
    abs_p = os.path.normpath(os.path.join(old_dir, value))
    if not os.path.exists(abs_p):
        return value
    try:
        return os.path.relpath(abs_p, new_dir).replace("\\", "/")
    except ValueError:
        return abs_p.replace("\\", "/")
