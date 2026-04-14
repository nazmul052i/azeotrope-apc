"""Gain matrix analysis: condition number, colinearity, sub-matrix analysis.

Evaluates controllability of the identified model by analyzing the
steady-state gain matrix.  High condition numbers or colinear MV-CV
pairs indicate potential control problems.

Features
--------
- Condition number with multiple scaling options (LP, QP, Typical Moves, None)
- 2x2, 3x3, 4x4 sub-matrix condition number scanning
- Colinearity detection between MV columns
- Problem highlighting with severity grading

Usage::

    result = analyze_gain_matrix(gain, cv_names, mv_names,
                                 typical_moves=[5.0, 3.0])
    print(result.summary())
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class ScalingMethod(str, Enum):
    NONE = "none"
    TYPICAL_MOVES = "typical_moves"
    RANGE = "range"


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class SubMatrixResult:
    """Condition number for one sub-matrix."""
    cv_indices: Tuple[int, ...]
    mv_indices: Tuple[int, ...]
    cv_names: Tuple[str, ...]
    mv_names: Tuple[str, ...]
    condition_number: float
    is_problematic: bool
    size: int


@dataclass
class ColinearityPair:
    """A pair of MVs with high correlation in the gain matrix."""
    mv_a: str
    mv_b: str
    mv_a_idx: int
    mv_b_idx: int
    cosine_similarity: float
    severity: str  # "low", "medium", "high"


@dataclass
class GainMatrixReport:
    """Full gain matrix analysis result."""
    gain_matrix: np.ndarray
    gain_matrix_scaled: np.ndarray
    scaling_method: ScalingMethod
    cv_names: List[str]
    mv_names: List[str]

    # Overall condition
    condition_number: float
    condition_number_scaled: float

    # Singular values
    singular_values: np.ndarray

    # Sub-matrix analysis
    sub_matrix_results: List[SubMatrixResult] = field(default_factory=list)
    problematic_submatrices: List[SubMatrixResult] = field(default_factory=list)

    # Colinearity
    colinear_pairs: List[ColinearityPair] = field(default_factory=list)

    # RGA (Relative Gain Array)
    rga: Optional[np.ndarray] = None

    def summary(self) -> str:
        lines = [
            f"Gain Matrix Analysis",
            f"  Size: {len(self.cv_names)} CVs x {len(self.mv_names)} MVs",
            f"  Scaling: {self.scaling_method.value}",
            f"  Condition number: {self.condition_number:.1f}"
            f"  (scaled: {self.condition_number_scaled:.1f})",
            f"  Singular values: {np.array2string(self.singular_values, precision=3)}",
        ]

        if self.rga is not None and self.rga.shape[0] == self.rga.shape[1]:
            lines.append(f"  RGA diagonal: {np.diag(self.rga).round(3)}")

        if self.colinear_pairs:
            lines.append(f"  Colinear MV pairs ({len(self.colinear_pairs)}):")
            for cp in self.colinear_pairs:
                lines.append(
                    f"    {cp.mv_a} ~ {cp.mv_b}: cos={cp.cosine_similarity:.3f} "
                    f"[{cp.severity}]")

        if self.problematic_submatrices:
            lines.append(
                f"  Problematic sub-matrices ({len(self.problematic_submatrices)}):")
            for sm in self.problematic_submatrices[:10]:
                cvs = ", ".join(sm.cv_names)
                mvs = ", ".join(sm.mv_names)
                lines.append(
                    f"    {sm.size}x{sm.size}: [{cvs}] x [{mvs}] "
                    f"cond={sm.condition_number:.1f}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------
def _scale_gain_matrix(
    G: np.ndarray,
    method: ScalingMethod,
    typical_moves: Optional[np.ndarray] = None,
    cv_ranges: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Scale gain matrix columns/rows."""
    G_scaled = G.copy()
    ny, nu = G.shape

    if method == ScalingMethod.TYPICAL_MOVES and typical_moves is not None:
        for j in range(nu):
            if abs(typical_moves[j]) > 1e-15:
                G_scaled[:, j] *= typical_moves[j]

    elif method == ScalingMethod.RANGE and cv_ranges is not None:
        for i in range(ny):
            if abs(cv_ranges[i]) > 1e-15:
                G_scaled[i, :] /= cv_ranges[i]

    return G_scaled


# ---------------------------------------------------------------------------
# RGA
# ---------------------------------------------------------------------------
def compute_rga(G: np.ndarray) -> Optional[np.ndarray]:
    """Compute the Relative Gain Array (Bristol array).

    RGA = G .* (G^{-1})^T   (element-wise product)

    Only defined for square matrices.
    """
    ny, nu = G.shape
    if ny != nu:
        return None
    try:
        G_inv = np.linalg.inv(G)
        return G * G_inv.T
    except np.linalg.LinAlgError:
        return None


# ---------------------------------------------------------------------------
# Colinearity detection
# ---------------------------------------------------------------------------
def _detect_colinearity(
    G: np.ndarray,
    mv_names: List[str],
    threshold: float = 0.9,
) -> List[ColinearityPair]:
    """Detect colinear MV columns using cosine similarity."""
    ny, nu = G.shape
    pairs = []

    for i in range(nu):
        for j in range(i + 1, nu):
            col_i = G[:, i]
            col_j = G[:, j]
            norm_i = np.linalg.norm(col_i)
            norm_j = np.linalg.norm(col_j)
            if norm_i < 1e-15 or norm_j < 1e-15:
                continue
            cos_sim = abs(float(col_i @ col_j / (norm_i * norm_j)))

            if cos_sim > threshold:
                if cos_sim > 0.98:
                    severity = "high"
                elif cos_sim > 0.95:
                    severity = "medium"
                else:
                    severity = "low"

                pairs.append(ColinearityPair(
                    mv_a=mv_names[i], mv_b=mv_names[j],
                    mv_a_idx=i, mv_b_idx=j,
                    cosine_similarity=cos_sim,
                    severity=severity,
                ))
    return pairs


# ---------------------------------------------------------------------------
# Sub-matrix scanning
# ---------------------------------------------------------------------------
def _scan_submatrices(
    G: np.ndarray,
    cv_names: List[str],
    mv_names: List[str],
    sizes: List[int],
    cond_threshold: float = 100.0,
) -> Tuple[List[SubMatrixResult], List[SubMatrixResult]]:
    """Scan all sub-matrices of given sizes for high condition numbers."""
    ny, nu = G.shape
    all_results = []
    problematic = []

    for size in sizes:
        if size > ny or size > nu:
            continue
        for cv_combo in combinations(range(ny), size):
            for mv_combo in combinations(range(nu), size):
                sub = G[np.ix_(list(cv_combo), list(mv_combo))]
                try:
                    cond = float(np.linalg.cond(sub))
                except Exception:
                    cond = np.inf

                is_prob = cond > cond_threshold
                result = SubMatrixResult(
                    cv_indices=cv_combo,
                    mv_indices=mv_combo,
                    cv_names=tuple(cv_names[i] for i in cv_combo),
                    mv_names=tuple(mv_names[j] for j in mv_combo),
                    condition_number=cond,
                    is_problematic=is_prob,
                    size=size,
                )
                all_results.append(result)
                if is_prob:
                    problematic.append(result)

    # Sort problematic by condition number (worst first)
    problematic.sort(key=lambda r: r.condition_number, reverse=True)
    return all_results, problematic


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def analyze_gain_matrix(
    gain_matrix: np.ndarray,
    cv_names: Optional[List[str]] = None,
    mv_names: Optional[List[str]] = None,
    scaling: ScalingMethod = ScalingMethod.NONE,
    typical_moves: Optional[np.ndarray] = None,
    cv_ranges: Optional[np.ndarray] = None,
    sub_matrix_sizes: Optional[List[int]] = None,
    cond_threshold: float = 100.0,
    colinearity_threshold: float = 0.9,
) -> GainMatrixReport:
    """Run full gain matrix analysis.

    Parameters
    ----------
    gain_matrix : ndarray, shape (ny, nu)
        Steady-state gain matrix.
    scaling : ScalingMethod
        How to scale before analysis.
    typical_moves : ndarray, optional
        Per-MV typical move sizes.
    sub_matrix_sizes : list[int], optional
        Sub-matrix sizes to scan. Default: [2, 3, 4].
    cond_threshold : float
        Condition number above which a sub-matrix is flagged.
    """
    G = np.atleast_2d(gain_matrix)
    ny, nu = G.shape

    if cv_names is None:
        cv_names = [f"CV{i}" for i in range(ny)]
    if mv_names is None:
        mv_names = [f"MV{j}" for j in range(nu)]
    if sub_matrix_sizes is None:
        sub_matrix_sizes = [2, 3, 4]

    # Scale
    G_scaled = _scale_gain_matrix(G, scaling, typical_moves, cv_ranges)

    # Condition numbers
    cond = float(np.linalg.cond(G))
    cond_scaled = float(np.linalg.cond(G_scaled))

    # SVD
    sv = np.linalg.svd(G_scaled, compute_uv=False)

    # RGA
    rga = compute_rga(G_scaled)

    # Colinearity
    colinear = _detect_colinearity(G, mv_names, colinearity_threshold)

    # Sub-matrix scan
    all_sub, problematic = _scan_submatrices(
        G_scaled, cv_names, mv_names, sub_matrix_sizes, cond_threshold)

    return GainMatrixReport(
        gain_matrix=G,
        gain_matrix_scaled=G_scaled,
        scaling_method=scaling,
        cv_names=cv_names,
        mv_names=mv_names,
        condition_number=cond,
        condition_number_scaled=cond_scaled,
        singular_values=sv,
        sub_matrix_results=all_sub,
        problematic_submatrices=problematic,
        colinear_pairs=colinear,
        rga=rga,
    )
