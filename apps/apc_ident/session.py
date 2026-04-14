"""Runtime session state for the apc_ident studio.

The IdentProject (loaded from .apcident YAML) holds the *persisted*
state -- segments, tag bindings, conditioning + ident config, last
bundle path. The IdentSession holds the *transient* runtime state --
the loaded DataFrame, the most recent ConditioningResult and
IdentResult, the in-memory ModelBundle. This separation lets the GUI
reload data without re-touching the project file, and lets the
project file stay focused on what the engineer actually configured.

The MainWindow owns one IdentSession and passes it to every tab so
they can read/write the shared runtime state without going through
the menu system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from azeoapc.identification import (
    ConditioningResult, IdentProject, IdentResult, ModelBundle,
)
from azeoapc.identification.multi_trial import TrialComparison


@dataclass
class IdentSession:
    """Live, transient state shared across the apc_ident tabs."""

    project: IdentProject = field(default_factory=IdentProject)

    # Loaded raw data (Data tab populates, Tags tab reads columns)
    df: Optional[pd.DataFrame] = None
    df_path: Optional[str] = None

    # Most recent conditioning run (Identification tab populates)
    cond_result: Optional[ConditioningResult] = None

    # Most recent identification (Identification tab populates,
    # Results + Validation read)
    ident_result: Optional[IdentResult] = None

    # Multi-trial comparison (all trials, not just the best)
    trial_comparison: Optional[TrialComparison] = None

    # In-memory bundle (Results tab populates on Export, Validation reads)
    bundle: Optional[ModelBundle] = None

    # ------------------------------------------------------------------
    def has_data(self) -> bool:
        return self.df is not None and len(self.df) > 0

    def has_tag_bindings(self) -> bool:
        return any(t.role in ("MV", "CV", "DV")
                   for t in self.project.tag_assignments)

    def has_ident(self) -> bool:
        return self.ident_result is not None

    def has_bundle(self) -> bool:
        return self.bundle is not None

    def reset(self):
        """Clear all transient state (called on New/Open Project)."""
        self.df = None
        self.df_path = None
        self.cond_result = None
        self.ident_result = None
        self.trial_comparison = None
        self.bundle = None
