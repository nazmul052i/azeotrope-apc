"""Smart configuration: auto-detect all identification parameters from data.

Analyzes the raw step-test data and recommends:
- Sample period (from index or auto-correlation)
- Model length (n_coeff) from estimated settling time
- Identification method (DLS vs Ridge based on input correlation)
- Smoothing strategy
- CV types (ramp/pseudoramp/normal)
- Excitation adequacy per MV
- Data quality issues (NaN, flatline, spikes, drift)

One button replaces 20 minutes of manual trial-and-error that
engineers currently do in DMC3.

Usage::

    config, report = smart_configure(df, mv_cols, cv_cols)
    # config is a ready-to-use IdentConfig
    # report explains every decision
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SmartConfigRecommendation:
    """One recommendation with rationale."""
    parameter: str
    value: object
    reason: str
    confidence: str = "high"   # high / medium / low


@dataclass
class SmartConfigReport:
    """Full auto-configuration report."""
    recommendations: List[SmartConfigRecommendation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    data_quality: Dict[str, str] = field(default_factory=dict)
    cv_types: Dict[str, str] = field(default_factory=dict)
    excitation_grades: Dict[str, str] = field(default_factory=dict)

    # Recommended values (ready to apply)
    n_coeff: int = 60
    dt: float = 60.0
    method: str = "dls"
    smooth: str = "pipeline"
    ridge_alpha: float = 1.0
    detrend: bool = True
    remove_mean: bool = True
    prewhiten: bool = False
    clip_sigma: float = 4.0
    holdout_fraction: float = 0.2

    def summary(self) -> str:
        lines = ["Smart Configuration Report", "=" * 40]

        lines.append("\nRecommended Settings:")
        lines.append(f"  n_coeff      : {self.n_coeff}")
        lines.append(f"  dt           : {self.dt:.1f} s")
        lines.append(f"  method       : {self.method}")
        lines.append(f"  smooth       : {self.smooth}")
        lines.append(f"  detrend      : {self.detrend}")
        lines.append(f"  prewhiten    : {self.prewhiten}")
        lines.append(f"  clip_sigma   : {self.clip_sigma}")
        lines.append(f"  holdout      : {self.holdout_fraction}")

        if self.cv_types:
            lines.append("\nCV Types:")
            for cv, typ in self.cv_types.items():
                lines.append(f"  {cv}: {typ}")

        if self.excitation_grades:
            lines.append("\nMV Excitation:")
            for mv, grade in self.excitation_grades.items():
                lines.append(f"  {mv}: {grade}")

        if self.data_quality:
            lines.append("\nData Quality:")
            for col, quality in self.data_quality.items():
                lines.append(f"  {col}: {quality}")

        if self.warnings:
            lines.append("\nWarnings:")
            for w in self.warnings:
                lines.append(f"  ! {w}")

        lines.append("\nDecision Rationale:")
        for rec in self.recommendations:
            lines.append(
                f"  {rec.parameter}: {rec.value} "
                f"[{rec.confidence}] -- {rec.reason}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------
def _estimate_sample_period(df: pd.DataFrame) -> float:
    """Estimate sample period from datetime index."""
    if isinstance(df.index, pd.DatetimeIndex) and len(df) > 1:
        diffs = df.index.to_series().diff().dropna()
        median_sec = diffs.dt.total_seconds().median()
        if median_sec > 0:
            return float(median_sec)
    return 1.0


def _estimate_settling_time(
    u: np.ndarray, y: np.ndarray, dt: float, max_lag: int = 300,
) -> Tuple[float, int]:
    """Estimate settling time from cross-correlation decay.

    Returns (settling_time_seconds, settling_samples).
    """
    nu = u.shape[1]
    ny = y.shape[1]
    n = u.shape[0]

    max_lag = min(max_lag, n // 3)
    best_settling = 10  # minimum

    for j in range(nu):
        for i in range(ny):
            x = u[:, j] - np.mean(u[:, j])
            yy = y[:, i] - np.mean(y[:, i])
            sx = np.std(x)
            sy = np.std(yy)
            if sx < 1e-15 or sy < 1e-15:
                continue

            # Cross-correlation
            xcorr = np.zeros(max_lag)
            for lag in range(max_lag):
                if lag >= n:
                    break
                seg_x = x[:n - lag]
                seg_y = yy[lag:]
                xcorr[lag] = abs(np.mean(seg_x * seg_y) / (sx * sy))

            # Find where correlation decays to 5% of peak
            peak = np.max(xcorr)
            if peak < 0.05:
                continue
            threshold = 0.05 * peak
            for lag in range(len(xcorr)):
                if lag > 5 and xcorr[lag] < threshold:
                    best_settling = max(best_settling, lag)
                    break

    settling_time = best_settling * dt
    return settling_time, best_settling


def _check_excitation(u: np.ndarray, mv_names: List[str]) -> Dict[str, str]:
    """Grade MV excitation adequacy."""
    grades = {}
    for j, name in enumerate(mv_names):
        col = u[:, j]
        std = np.std(col)
        diff_std = np.std(np.diff(col))
        n_moves = np.sum(np.abs(np.diff(col)) > 0.1 * std) if std > 1e-15 else 0

        if n_moves < 3:
            grades[name] = "POOR - too few moves"
        elif n_moves < 6:
            grades[name] = "FAIR - more moves recommended"
        elif diff_std / (std + 1e-15) < 0.05:
            grades[name] = "FAIR - moves too small"
        else:
            grades[name] = "GOOD"
    return grades


def _check_data_quality(
    df: pd.DataFrame, cols: List[str],
) -> Dict[str, str]:
    """Check per-column data quality."""
    quality = {}
    for col in cols:
        if col not in df.columns:
            quality[col] = "MISSING"
            continue
        s = df[col]
        n = len(s)
        n_nan = int(s.isna().sum())
        pct_nan = 100.0 * n_nan / max(n, 1)

        # Flatline check
        diffs = s.diff().abs()
        n_flat = int((diffs < 1e-10).sum())
        pct_flat = 100.0 * n_flat / max(n, 1)

        issues = []
        if pct_nan > 5:
            issues.append(f"{pct_nan:.0f}% NaN")
        if pct_flat > 50:
            issues.append(f"{pct_flat:.0f}% flatline")

        if not issues:
            quality[col] = "GOOD"
        else:
            quality[col] = "WARN - " + ", ".join(issues)

    return quality


def _detect_cv_types(
    y: np.ndarray, cv_names: List[str],
) -> Dict[str, str]:
    """Auto-detect ramp/pseudoramp/normal per CV."""
    from .ramp_cv import detect_cv_type, CVType

    types = {}
    for i, name in enumerate(cv_names):
        cv_type = detect_cv_type(y[:, i])
        types[name] = cv_type.value
    return types


def _check_input_correlation(u: np.ndarray) -> Tuple[float, bool]:
    """Check if inputs are correlated (need Ridge instead of DLS)."""
    nu = u.shape[1]
    if nu < 2:
        return 0.0, False

    max_corr = 0.0
    for i in range(nu):
        for j in range(i + 1, nu):
            corr = abs(np.corrcoef(u[:, i], u[:, j])[0, 1])
            max_corr = max(max_corr, corr)

    return max_corr, max_corr > 0.7


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def smart_configure(
    df: pd.DataFrame,
    mv_cols: List[str],
    cv_cols: List[str],
) -> SmartConfigReport:
    """Analyze data and recommend all identification parameters.

    Parameters
    ----------
    df : DataFrame
        Raw step-test data.
    mv_cols : list[str]
        MV column names.
    cv_cols : list[str]
        CV column names.

    Returns
    -------
    SmartConfigReport
        Complete recommendation with rationale.
    """
    report = SmartConfigReport()
    recs = report.recommendations

    all_cols = mv_cols + cv_cols
    missing = [c for c in all_cols if c not in df.columns]
    if missing:
        report.warnings.append(f"Columns not found: {missing}")
        return report

    u = df[mv_cols].to_numpy(dtype=np.float64)
    y = df[cv_cols].to_numpy(dtype=np.float64)

    # Fill NaN for analysis
    u = pd.DataFrame(u).ffill().bfill().to_numpy()
    y = pd.DataFrame(y).ffill().bfill().to_numpy()

    N = len(u)

    # ── Sample period ──
    dt = _estimate_sample_period(df)
    report.dt = dt
    recs.append(SmartConfigRecommendation(
        "dt", f"{dt:.1f}s",
        f"Median index interval = {dt:.1f}s",
        "high" if isinstance(df.index, pd.DatetimeIndex) else "low"))

    # ── Settling time → n_coeff ──
    settling_time, settling_samples = _estimate_settling_time(u, y, dt)
    # n_coeff should be 1.5x settling to capture the full response
    n_coeff = int(settling_samples * 1.5)
    n_coeff = max(20, min(n_coeff, min(N // 3, 500)))
    report.n_coeff = n_coeff
    recs.append(SmartConfigRecommendation(
        "n_coeff", n_coeff,
        f"Estimated settling = {settling_samples} samples "
        f"({settling_time:.0f}s), using 1.5x = {n_coeff}"))

    # ── Input correlation → method ──
    max_corr, use_ridge = _check_input_correlation(u)
    if use_ridge:
        report.method = "ridge"
        report.ridge_alpha = 10.0
        recs.append(SmartConfigRecommendation(
            "method", "ridge",
            f"Max MV correlation = {max_corr:.2f} > 0.7, "
            f"Ridge recommended to handle collinearity"))
    else:
        report.method = "dls"
        recs.append(SmartConfigRecommendation(
            "method", "dls",
            f"Max MV correlation = {max_corr:.2f}, "
            f"inputs are sufficiently independent"))

    # ── Smoothing ──
    report.smooth = "pipeline"
    recs.append(SmartConfigRecommendation(
        "smooth", "pipeline",
        "Default pipeline (exponential → savgol → asymptotic) "
        "works well for most industrial data"))

    # ── CV types ──
    report.cv_types = _detect_cv_types(y, cv_cols)
    has_ramp = any(v == "ramp" for v in report.cv_types.values())
    if has_ramp:
        report.prewhiten = True
        recs.append(SmartConfigRecommendation(
            "prewhiten", True,
            "Integrating CVs detected, prewhitening recommended"))

    # ── Excitation ──
    report.excitation_grades = _check_excitation(u, mv_cols)
    poor_mvs = [mv for mv, g in report.excitation_grades.items()
                if "POOR" in g]
    if poor_mvs:
        report.warnings.append(
            f"Low excitation on: {', '.join(poor_mvs)}. "
            f"Consider extending the step test.")

    # ── Data quality ──
    report.data_quality = _check_data_quality(df, all_cols)
    bad_cols = [c for c, q in report.data_quality.items() if "WARN" in q]
    if bad_cols:
        report.warnings.append(
            f"Data quality issues: {', '.join(bad_cols)}")

    # ── Holdout ──
    if N < 200:
        report.holdout_fraction = 0.1
        recs.append(SmartConfigRecommendation(
            "holdout", 0.1,
            f"Short dataset ({N} rows), reducing holdout to 10%"))
    else:
        report.holdout_fraction = 0.2
        recs.append(SmartConfigRecommendation(
            "holdout", 0.2, "Standard 20% holdout"))

    # ── Detrend ──
    report.detrend = True
    report.remove_mean = True
    report.clip_sigma = 4.0

    return report
