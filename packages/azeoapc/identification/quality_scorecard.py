"""Model Quality Scorecard -- single-page health check for identified models.

Grades every aspect of the identification on a simple traffic-light scale
(GREEN / YELLOW / RED) with actionable recommendations.

Categories:
1. DATA QUALITY     -- NaN, flatline, outliers, sample count
2. EXCITATION       -- MV move count, move size, frequency content
3. MODEL FIT        -- R², RMSE, residual whiteness, condition number
4. CONTROLLABILITY  -- gain matrix condition, colinearity, RGA diagonal
5. UNCERTAINTY      -- SS gain uncertainty, dynamic uncertainty, SNR

Each category gets a grade and a list of specific findings.
The overall grade is the worst of all categories.

Usage::

    scorecard = build_scorecard(ident_result, cond_result, df, mv_cols, cv_cols)
    print(scorecard.summary())
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class Grade:
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"

    @staticmethod
    def worst(*grades: str) -> str:
        order = [Grade.GREEN, Grade.YELLOW, Grade.RED]
        return max(grades, key=lambda g: order.index(g) if g in order else 0)


@dataclass
class ScorecardCategory:
    """One category in the scorecard."""
    name: str
    grade: str = Grade.GREEN
    findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class ModelScorecard:
    """Complete model quality scorecard."""
    categories: List[ScorecardCategory] = field(default_factory=list)
    overall_grade: str = Grade.GREEN

    def summary(self) -> str:
        grade_icons = {
            Grade.GREEN: "[OK]",
            Grade.YELLOW: "[!!]",
            Grade.RED: "[XX]",
        }
        lines = [
            "Model Quality Scorecard",
            "=" * 50,
            f"Overall: {grade_icons.get(self.overall_grade, '?')} "
            f"{self.overall_grade}",
            "",
        ]
        for cat in self.categories:
            icon = grade_icons.get(cat.grade, "?")
            lines.append(f"{icon} {cat.name}: {cat.grade}")
            for f in cat.findings:
                lines.append(f"     {f}")
            for r in cat.recommendations:
                lines.append(f"  -> {r}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Category builders
# ---------------------------------------------------------------------------
def _grade_data_quality(
    cond_report, n_rows: int, n_cols: int,
) -> ScorecardCategory:
    """Grade data quality from the conditioning report."""
    cat = ScorecardCategory(name="DATA QUALITY")

    if cond_report is None:
        cat.grade = Grade.YELLOW
        cat.findings.append("No conditioning report available")
        return cat

    cat.findings.append(f"{n_rows} rows, {n_cols} columns")

    # NaN
    n_nan = cond_report.n_nan_filled
    pct_nan = 100.0 * n_nan / max(n_rows * n_cols, 1)
    if pct_nan > 10:
        cat.grade = Grade.RED
        cat.findings.append(f"{pct_nan:.1f}% NaN values filled")
        cat.recommendations.append("Check historian data quality")
    elif pct_nan > 2:
        cat.grade = Grade.YELLOW
        cat.findings.append(f"{pct_nan:.1f}% NaN values filled")

    # Outliers
    n_out = cond_report.n_outliers_clipped
    if n_out > n_rows * 0.05:
        cat.grade = Grade.worst(cat.grade, Grade.YELLOW)
        cat.findings.append(f"{n_out} outliers clipped ({100*n_out/n_rows:.1f}%)")

    # Sample count
    if n_rows < 100:
        cat.grade = Grade.RED
        cat.findings.append(f"Only {n_rows} samples -- very short test")
        cat.recommendations.append("Extend the step test to at least 200 samples")
    elif n_rows < 300:
        cat.grade = Grade.worst(cat.grade, Grade.YELLOW)
        cat.findings.append(f"{n_rows} samples -- short test window")

    if cat.grade == Grade.GREEN:
        cat.findings.append("Data quality is good")

    return cat


def _grade_excitation(
    u_train: np.ndarray, mv_names: List[str],
) -> ScorecardCategory:
    """Grade MV excitation."""
    cat = ScorecardCategory(name="MV EXCITATION")
    nu = u_train.shape[1]

    for j in range(nu):
        col = u_train[:, j]
        std = np.std(col)
        diff = np.diff(col)
        diff_std = np.std(diff)
        n_moves = int(np.sum(np.abs(diff) > 0.1 * std)) if std > 1e-15 else 0
        name = mv_names[j] if j < len(mv_names) else f"MV{j}"

        if n_moves < 3:
            cat.grade = Grade.worst(cat.grade, Grade.RED)
            cat.findings.append(f"{name}: only {n_moves} moves -- insufficient")
            cat.recommendations.append(f"Add more step moves to {name}")
        elif n_moves < 6:
            cat.grade = Grade.worst(cat.grade, Grade.YELLOW)
            cat.findings.append(f"{name}: {n_moves} moves -- marginal")
        else:
            cat.findings.append(f"{name}: {n_moves} moves -- adequate")

    return cat


def _grade_model_fit(
    result, cv_names: List[str],
) -> ScorecardCategory:
    """Grade model fit quality."""
    cat = ScorecardCategory(name="MODEL FIT")

    if result is None:
        cat.grade = Grade.RED
        cat.findings.append("No identification result")
        return cat

    # Per-CV R²
    if hasattr(result, 'fits'):
        seen = {}
        for f in result.fits:
            seen.setdefault(f.cv_index, f)
        for idx in sorted(seen.keys()):
            f = seen[idx]
            name = cv_names[idx] if idx < len(cv_names) else f"CV{idx}"
            r2 = f.r_squared
            if r2 < 0.5:
                cat.grade = Grade.worst(cat.grade, Grade.RED)
                cat.findings.append(f"{name}: R²={r2:.3f} -- poor fit")
                cat.recommendations.append(
                    f"Check data quality for {name}, try different n_coeff")
            elif r2 < 0.8:
                cat.grade = Grade.worst(cat.grade, Grade.YELLOW)
                cat.findings.append(f"{name}: R²={r2:.3f} -- fair fit")
            else:
                cat.findings.append(f"{name}: R²={r2:.3f} -- good fit")

            # Residual whiteness
            if hasattr(f, 'ljung_box_pvalue') and f.ljung_box_pvalue < 0.05:
                cat.grade = Grade.worst(cat.grade, Grade.YELLOW)
                cat.findings.append(
                    f"{name}: residuals not white (LB p={f.ljung_box_pvalue:.3f})")
    elif hasattr(result, 'fit_r2'):
        for idx, r2 in enumerate(result.fit_r2):
            name = cv_names[idx] if idx < len(cv_names) else f"CV{idx}"
            if r2 < 0.5:
                cat.grade = Grade.worst(cat.grade, Grade.RED)
                cat.findings.append(f"{name}: R²={r2:.3f} -- poor fit")
            elif r2 < 0.8:
                cat.grade = Grade.worst(cat.grade, Grade.YELLOW)
                cat.findings.append(f"{name}: R²={r2:.3f} -- fair")
            else:
                cat.findings.append(f"{name}: R²={r2:.3f} -- good")

    # Condition number
    cond = getattr(result, 'condition_number', 0)
    if cond > 1e6:
        cat.grade = Grade.worst(cat.grade, Grade.RED)
        cat.findings.append(f"Condition number = {cond:.0e} -- severely ill-conditioned")
        cat.recommendations.append("Use Ridge method or check for redundant inputs")
    elif cond > 1e3:
        cat.grade = Grade.worst(cat.grade, Grade.YELLOW)
        cat.findings.append(f"Condition number = {cond:.0f} -- moderately conditioned")

    return cat


def _grade_controllability(
    result, mv_names: List[str], cv_names: List[str],
) -> ScorecardCategory:
    """Grade model controllability from gain matrix."""
    cat = ScorecardCategory(name="CONTROLLABILITY")

    gain = result.gain_matrix() if callable(getattr(result, 'gain_matrix', None)) else None
    if gain is None and hasattr(result, 'gain_matrix'):
        gain = result.gain_matrix
    if gain is None:
        cat.grade = Grade.YELLOW
        cat.findings.append("Cannot extract gain matrix")
        return cat

    gain = np.atleast_2d(gain)
    ny, nu = gain.shape

    # Condition number
    try:
        cond = float(np.linalg.cond(gain))
    except Exception:
        cond = np.inf

    if cond > 100:
        cat.grade = Grade.RED
        cat.findings.append(f"Gain matrix condition number = {cond:.1f} -- poor")
        cat.recommendations.append("Check for colinear MVs or near-zero gains")
    elif cond > 20:
        cat.grade = Grade.YELLOW
        cat.findings.append(f"Gain matrix condition number = {cond:.1f} -- fair")
    else:
        cat.findings.append(f"Gain matrix condition number = {cond:.1f} -- good")

    # Zero gains
    for i in range(ny):
        for j in range(nu):
            if abs(gain[i, j]) < 1e-10:
                cv = cv_names[i] if i < len(cv_names) else f"CV{i}"
                mv = mv_names[j] if j < len(mv_names) else f"MV{j}"
                cat.findings.append(f"Zero gain: {cv}/{mv}")

    # RGA (square only)
    if ny == nu:
        try:
            rga = gain * np.linalg.inv(gain).T
            diag = np.diag(rga)
            for i in range(ny):
                cv = cv_names[i] if i < len(cv_names) else f"CV{i}"
                if diag[i] < 0:
                    cat.grade = Grade.worst(cat.grade, Grade.RED)
                    cat.findings.append(f"RGA({cv}) = {diag[i]:.2f} -- negative, bad pairing")
                elif diag[i] < 0.5 or diag[i] > 5.0:
                    cat.grade = Grade.worst(cat.grade, Grade.YELLOW)
                    cat.findings.append(f"RGA({cv}) = {diag[i]:.2f} -- significant interaction")
        except Exception:
            pass

    return cat


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def build_scorecard(
    ident_result=None,
    cond_result=None,
    df=None,
    mv_cols: Optional[List[str]] = None,
    cv_cols: Optional[List[str]] = None,
) -> ModelScorecard:
    """Build a complete model quality scorecard.

    Parameters
    ----------
    ident_result : IdentResult or SubspaceResult
        The identification result.
    cond_result : ConditioningResult
        The conditioning result (for data quality stats).
    df : DataFrame, optional
        Raw data (for additional quality checks).
    mv_cols, cv_cols : list[str]
        Tag names.
    """
    mv_names = mv_cols or []
    cv_names = cv_cols or []
    scorecard = ModelScorecard()

    # Data quality
    n_rows = cond_result.u_train.shape[0] if cond_result else (len(df) if df is not None else 0)
    n_cols = len(mv_names) + len(cv_names)
    cond_report = cond_result.report if cond_result else None
    scorecard.categories.append(_grade_data_quality(cond_report, n_rows, n_cols))

    # Excitation
    if cond_result is not None:
        scorecard.categories.append(
            _grade_excitation(cond_result.u_train, mv_names))

    # Model fit
    scorecard.categories.append(
        _grade_model_fit(ident_result, cv_names))

    # Controllability
    if ident_result is not None:
        scorecard.categories.append(
            _grade_controllability(ident_result, mv_names, cv_names))

    # Overall grade
    scorecard.overall_grade = Grade.GREEN
    for cat in scorecard.categories:
        scorecard.overall_grade = Grade.worst(scorecard.overall_grade, cat.grade)

    return scorecard
