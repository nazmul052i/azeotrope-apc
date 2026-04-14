"""Cross-correlation analysis for step-test data quality assessment.

Evaluates whether the step-test input signals (MVs) are sufficiently
independent and well-excited for reliable model identification.

Key analyses:

- **Auto-correlation**: How quickly each MV signal decorrelates with
  itself. Slow decay indicates drift or periodic content.
- **Cross-correlation**: Pairwise correlation between MVs at various
  lags. High cross-correlation means the MVs were moved together,
  making it hard to separate their effects.
- **Quality grading**: DMC3-style zones:
  - Ideal: peak |cross-corr| < 30%
  - Acceptable: 30-50%
  - Poor: 50-80%
  - Unacceptable: > 80%

Usage::

    result = analyze_cross_correlation(df, mv_cols=["FIC101", "FIC102"])
    print(result.summary())
    # result.quality_grades  -> dict of MV pair -> grade
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quality grades
# ---------------------------------------------------------------------------
class CorrelationGrade:
    IDEAL = "IDEAL"             # < 30%
    ACCEPTABLE = "ACCEPTABLE"   # 30-50%
    POOR = "POOR"               # 50-80%
    UNACCEPTABLE = "UNACCEPTABLE"  # > 80%


def _grade_correlation(peak_abs: float) -> str:
    if peak_abs < 0.30:
        return CorrelationGrade.IDEAL
    elif peak_abs < 0.50:
        return CorrelationGrade.ACCEPTABLE
    elif peak_abs < 0.80:
        return CorrelationGrade.POOR
    else:
        return CorrelationGrade.UNACCEPTABLE


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class AutoCorrelationResult:
    """Auto-correlation for one MV."""
    name: str
    lags: np.ndarray           # integer lags
    values: np.ndarray         # normalized auto-correlation
    decay_lag: int             # lag where |acf| drops below 1/e
    is_periodic: bool          # True if secondary peak detected


@dataclass
class CrossCorrelationResult:
    """Cross-correlation between two MVs."""
    name_a: str
    name_b: str
    lags: np.ndarray           # integer lags (negative = a leads)
    values: np.ndarray         # normalized cross-correlation
    peak_lag: int              # lag at peak |xcf|
    peak_value: float          # peak |xcf| value
    grade: str                 # quality grade


@dataclass
class CorrelationAnalysis:
    """Complete cross-correlation analysis result."""
    auto_correlations: Dict[str, AutoCorrelationResult] = field(default_factory=dict)
    cross_correlations: Dict[Tuple[str, str], CrossCorrelationResult] = field(
        default_factory=dict)
    quality_grades: Dict[Tuple[str, str], str] = field(default_factory=dict)
    mv_names: List[str] = field(default_factory=list)

    @property
    def worst_grade(self) -> str:
        grades = list(self.quality_grades.values())
        if not grades:
            return CorrelationGrade.IDEAL
        order = [CorrelationGrade.IDEAL, CorrelationGrade.ACCEPTABLE,
                 CorrelationGrade.POOR, CorrelationGrade.UNACCEPTABLE]
        return max(grades, key=lambda g: order.index(g) if g in order else 0)

    def summary(self) -> str:
        lines = [f"Cross-Correlation Analysis ({len(self.mv_names)} MVs)"]

        lines.append("  Auto-correlation:")
        for name, ac in self.auto_correlations.items():
            periodic = " PERIODIC" if ac.is_periodic else ""
            lines.append(f"    {name}: decay at lag {ac.decay_lag}{periodic}")

        lines.append("  Cross-correlation:")
        for (a, b), xc in self.cross_correlations.items():
            lines.append(
                f"    {a} vs {b}: peak={xc.peak_value:.3f} at lag={xc.peak_lag}  "
                f"[{xc.grade}]")

        lines.append(f"  Overall: {self.worst_grade}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------
def _normalized_correlation(
    x: np.ndarray, y: np.ndarray, max_lag: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute normalized cross-correlation for lags [-max_lag, +max_lag].

    Returns (lags, values) where values are in [-1, 1].
    """
    x = x - np.mean(x)
    y = y - np.mean(y)
    sx = np.std(x)
    sy = np.std(y)
    if sx < 1e-15 or sy < 1e-15:
        lags = np.arange(-max_lag, max_lag + 1)
        return lags, np.zeros(len(lags))

    n = len(x)
    lags = np.arange(-max_lag, max_lag + 1)
    values = np.zeros(len(lags))

    for idx, lag in enumerate(lags):
        if lag >= 0:
            seg_x = x[:n - lag]
            seg_y = y[lag:]
        else:
            seg_x = x[-lag:]
            seg_y = y[:n + lag]
        if len(seg_x) > 0:
            values[idx] = np.mean(seg_x * seg_y) / (sx * sy)

    return lags, values


def _detect_periodicity(acf: np.ndarray, threshold: float = 0.3) -> bool:
    """Detect periodic content from auto-correlation.

    Looks for secondary peaks (after the initial decay) that exceed threshold.
    """
    # Find first zero crossing
    n = len(acf)
    first_zero = n
    for i in range(1, n):
        if acf[i] <= 0:
            first_zero = i
            break

    # Look for peaks after the first zero crossing
    for i in range(first_zero + 1, n - 1):
        if acf[i] > threshold and acf[i] > acf[i - 1] and acf[i] > acf[i + 1]:
            return True
    return False


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def analyze_cross_correlation(
    df: pd.DataFrame,
    mv_cols: List[str],
    max_lag: int = 100,
) -> CorrelationAnalysis:
    """Run full cross-correlation analysis on MV columns.

    Parameters
    ----------
    df : DataFrame
        Process data.
    mv_cols : list[str]
        MV column names to analyze.
    max_lag : int
        Maximum lag to compute (samples).

    Returns
    -------
    CorrelationAnalysis
        Auto and cross-correlation results with quality grades.
    """
    result = CorrelationAnalysis(mv_names=list(mv_cols))

    # Auto-correlations
    for col in mv_cols:
        if col not in df.columns:
            continue
        x = df[col].dropna().to_numpy(dtype=np.float64)
        if len(x) < 2 * max_lag:
            continue

        lags, acf = _normalized_correlation(x, x, max_lag)
        # Extract positive lags only for auto-correlation
        pos_mask = lags >= 0
        pos_lags = lags[pos_mask]
        pos_acf = acf[pos_mask]

        # Decay lag: where |acf| drops below 1/e
        decay_lag = len(pos_acf)
        threshold = np.exp(-1.0)
        for i in range(1, len(pos_acf)):
            if abs(pos_acf[i]) < threshold:
                decay_lag = i
                break

        is_periodic = _detect_periodicity(pos_acf)

        result.auto_correlations[col] = AutoCorrelationResult(
            name=col,
            lags=pos_lags,
            values=pos_acf,
            decay_lag=decay_lag,
            is_periodic=is_periodic,
        )

    # Cross-correlations (pairwise)
    for i in range(len(mv_cols)):
        for j in range(i + 1, len(mv_cols)):
            col_a = mv_cols[i]
            col_b = mv_cols[j]
            if col_a not in df.columns or col_b not in df.columns:
                continue

            x = df[col_a].dropna().to_numpy(dtype=np.float64)
            y = df[col_b].dropna().to_numpy(dtype=np.float64)
            n = min(len(x), len(y))
            if n < 2 * max_lag:
                continue

            lags, xcf = _normalized_correlation(x[:n], y[:n], max_lag)

            peak_idx = np.argmax(np.abs(xcf))
            peak_lag = int(lags[peak_idx])
            peak_value = float(np.abs(xcf[peak_idx]))
            grade = _grade_correlation(peak_value)

            xc_result = CrossCorrelationResult(
                name_a=col_a,
                name_b=col_b,
                lags=lags,
                values=xcf,
                peak_lag=peak_lag,
                peak_value=peak_value,
                grade=grade,
            )
            result.cross_correlations[(col_a, col_b)] = xc_result
            result.quality_grades[(col_a, col_b)] = grade

    return result
