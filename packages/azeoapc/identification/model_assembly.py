"""Model assembly: pick the best step-response curve for each MV-CV pair
from multiple identification runs and assemble into a final model.

In DMC3 the engineer runs several identification cases (different TTSS,
smoothing, methods) and then "assembles" a final model by choosing, for
each cell in the (CV x MV) matrix, which trial produced the best curve.
Curve operations can be applied after selection.

Usage::

    assembler = ModelAssembler(cv_names=["TI201","FI201"],
                               mv_names=["FIC101","FIC102"])

    # Register candidate models from different identification runs
    assembler.add_candidate("FIR_trial1", step_matrix_1, fits_1)
    assembler.add_candidate("FIR_trial2", step_matrix_2, fits_2)
    assembler.add_candidate("subspace",   step_matrix_3, fits_3)

    # Auto-select best by R² per channel
    assembler.auto_select()

    # Or manually pick: use trial2's curve for (CV0, MV1)
    assembler.select(cv=0, mv=1, candidate="FIR_trial2")

    # Apply curve operations to specific cells
    assembler.apply_curve_op(cv=0, mv=0, CurveOp.SHIFT, shift=3)

    # Build final assembled model
    final = assembler.build()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .curve_operations import CurveOp, CurveOpRecord, apply_op, apply_ops_chain

logger = logging.getLogger(__name__)


@dataclass
class CandidateModel:
    """One candidate identification result."""
    name: str
    step_response: np.ndarray   # (ny, n_coeff, nu) or (n_coeff,) per channel
    n_coeff: int
    dt: float = 1.0
    fit_r2: Optional[np.ndarray] = None   # (ny,) per-CV R²
    fit_rmse: Optional[np.ndarray] = None
    source: str = ""  # "fir", "subspace", etc.


@dataclass
class CellSelection:
    """Selection and operations for one (CV, MV) cell."""
    cv_idx: int
    mv_idx: int
    candidate_name: str = ""
    ops: List[CurveOpRecord] = field(default_factory=list)
    locked: bool = False  # prevent auto-select from overriding


@dataclass
class AssembledModel:
    """The final assembled model matrix."""
    step_response: np.ndarray     # (ny, n_coeff, nu)
    gain_matrix: np.ndarray       # (ny, nu)
    cv_names: List[str]
    mv_names: List[str]
    n_coeff: int
    dt: float
    selections: Dict[Tuple[int, int], CellSelection] = field(default_factory=dict)
    typical_moves: Optional[np.ndarray] = None  # (nu,)

    def summary(self) -> str:
        lines = [
            f"Assembled Model: {len(self.cv_names)} CVs x {len(self.mv_names)} MVs",
            f"  n_coeff={self.n_coeff}, dt={self.dt}",
            f"  Gain matrix:",
        ]
        for i, cv in enumerate(self.cv_names):
            row = "    " + "  ".join(
                f"{self.gain_matrix[i, j]:+8.4f}" for j in range(len(self.mv_names)))
            lines.append(f"  {cv}: {row}")
        return "\n".join(lines)


class ModelAssembler:
    """Assembles a final model matrix from multiple candidate identifications."""

    def __init__(
        self,
        cv_names: List[str],
        mv_names: List[str],
        n_coeff: int = 60,
        dt: float = 1.0,
    ):
        self.cv_names = list(cv_names)
        self.mv_names = list(mv_names)
        self.ny = len(cv_names)
        self.nu = len(mv_names)
        self.n_coeff = n_coeff
        self.dt = dt

        self.candidates: Dict[str, CandidateModel] = {}
        self.selections: Dict[Tuple[int, int], CellSelection] = {}

        # Initialize selections with empty
        for i in range(self.ny):
            for j in range(self.nu):
                self.selections[(i, j)] = CellSelection(cv_idx=i, mv_idx=j)

    def add_candidate(
        self,
        name: str,
        step_response: np.ndarray,
        fit_r2: Optional[np.ndarray] = None,
        fit_rmse: Optional[np.ndarray] = None,
        dt: Optional[float] = None,
        source: str = "",
    ):
        """Register a candidate model from an identification run.

        Parameters
        ----------
        name : str
            Unique identifier for this candidate.
        step_response : ndarray, shape (ny, n_coeff, nu)
            Cumulative step response matrix.
        fit_r2 : ndarray, optional
            Per-CV R² values.
        """
        n_coeff = step_response.shape[1] if step_response.ndim == 3 else len(step_response)
        self.candidates[name] = CandidateModel(
            name=name,
            step_response=step_response,
            n_coeff=n_coeff,
            dt=dt or self.dt,
            fit_r2=fit_r2,
            fit_rmse=fit_rmse,
            source=source,
        )

    def select(self, cv: int, mv: int, candidate: str):
        """Manually select which candidate to use for a specific cell."""
        if candidate not in self.candidates:
            raise ValueError(f"Unknown candidate: {candidate}")
        cell = self.selections[(cv, mv)]
        cell.candidate_name = candidate

    def lock(self, cv: int, mv: int):
        """Lock a cell so auto_select won't override it."""
        self.selections[(cv, mv)].locked = True

    def unlock(self, cv: int, mv: int):
        """Unlock a cell."""
        self.selections[(cv, mv)].locked = False

    def apply_curve_op(self, cv: int, mv: int, op: CurveOp, **params):
        """Add a curve operation to a specific cell."""
        record = CurveOpRecord(op=op, params=params)
        self.selections[(cv, mv)].ops.append(record)

    def clear_ops(self, cv: int, mv: int):
        """Clear all curve operations from a cell."""
        self.selections[(cv, mv)].ops.clear()

    def auto_select(self, metric: str = "r2"):
        """Auto-select the best candidate for each unlocked cell.

        Uses per-CV R² (higher is better) or RMSE (lower is better).
        """
        if not self.candidates:
            return

        for i in range(self.ny):
            cell_any = self.selections[(i, 0)]
            if cell_any.locked:
                continue

            best_name = ""
            best_score = -np.inf if metric == "r2" else np.inf

            for name, cand in self.candidates.items():
                if metric == "r2" and cand.fit_r2 is not None:
                    score = cand.fit_r2[i] if i < len(cand.fit_r2) else 0.0
                    if score > best_score:
                        best_score = score
                        best_name = name
                elif metric == "rmse" and cand.fit_rmse is not None:
                    score = cand.fit_rmse[i] if i < len(cand.fit_rmse) else np.inf
                    if score < best_score:
                        best_score = score
                        best_name = name

            if not best_name and self.candidates:
                best_name = next(iter(self.candidates))

            # Apply best to all MVs for this CV (unless individually locked)
            for j in range(self.nu):
                cell = self.selections[(i, j)]
                if not cell.locked:
                    cell.candidate_name = best_name

    def get_cell_curve(self, cv: int, mv: int) -> np.ndarray:
        """Get the final curve for a cell (after selection + operations)."""
        cell = self.selections[(cv, mv)]
        if not cell.candidate_name or cell.candidate_name not in self.candidates:
            return np.zeros(self.n_coeff)

        cand = self.candidates[cell.candidate_name]
        sr = cand.step_response
        if sr.ndim == 3:
            curve = sr[cv, :, mv].copy()
        else:
            curve = sr.copy()

        # Resize to target n_coeff
        if len(curve) != self.n_coeff:
            new_curve = np.zeros(self.n_coeff)
            n = min(len(curve), self.n_coeff)
            new_curve[:n] = curve[:n]
            if n < self.n_coeff:
                new_curve[n:] = curve[-1]
            curve = new_curve

        # Apply curve operations
        if cell.ops:
            curve = apply_ops_chain(curve, cell.ops, dt=self.dt)

        return curve

    def build(self, typical_moves: Optional[np.ndarray] = None) -> AssembledModel:
        """Build the final assembled model."""
        step = np.zeros((self.ny, self.n_coeff, self.nu))
        gain = np.zeros((self.ny, self.nu))

        for i in range(self.ny):
            for j in range(self.nu):
                curve = self.get_cell_curve(i, j)
                step[i, :, j] = curve
                gain[i, j] = curve[-1]

        return AssembledModel(
            step_response=step,
            gain_matrix=gain,
            cv_names=self.cv_names,
            mv_names=self.mv_names,
            n_coeff=self.n_coeff,
            dt=self.dt,
            selections=dict(self.selections),
            typical_moves=typical_moves,
        )
