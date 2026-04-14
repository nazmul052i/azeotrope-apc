"""Intelligent resampling for step-test data.

Provides multi-rate analysis that quantifies the trade-off between
**noise reduction** (good) and **signal preservation** (also good)
at different sample periods.  An auto-suggest function picks the
"sweet spot" where noise is adequately suppressed without losing
dynamic information.

Typical industrial data arrives from a historian at 1-second intervals
but the process dynamics operate on 30-second to 5-minute time scales.
Downsampling to the right period removes measurement noise without
smearing out the step responses the identification engine needs.

Usage::

    analysis = analyze_resample_rates(df, candidates=[15, 30, 60, 120, 300])
    best = suggest_resample_rate(analysis)
    df_resampled = resample_dataframe(df, period_sec=best.period_sec)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration & results
# ---------------------------------------------------------------------------
@dataclass
class ResampleRateStats:
    """Statistics for one candidate resample rate on one variable."""
    variable: str
    period_sec: int
    n_samples: int
    noise_ratio: float          # diff_std(resampled) / diff_std(raw); <1 = good
    signal_preservation: float  # std(resampled) / std(raw) * 100; ~100 = good
    mean_raw: float
    mean_resampled: float


@dataclass
class ResampleAnalysis:
    """Multi-rate analysis results for a full dataset."""
    candidates: List[int] = field(default_factory=list)
    per_variable: Dict[str, List[ResampleRateStats]] = field(default_factory=dict)
    aggregate: List[Dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["Resample analysis:"]
        lines.append(f"  {'Period':>8s}  {'Noise%':>8s}  {'Signal%':>8s}  {'Samples':>8s}")
        for row in self.aggregate:
            lines.append(
                f"  {row['period_sec']:>8d}  "
                f"{row['noise_ratio']*100:>7.1f}%  "
                f"{row['signal_preservation']:>7.1f}%  "
                f"{row['n_samples']:>8d}")
        return "\n".join(lines)


@dataclass
class ResampleSuggestion:
    """Recommended resample rate from auto-suggest."""
    period_sec: int
    noise_ratio: float
    signal_preservation: float
    n_samples: int
    reason: str


# ---------------------------------------------------------------------------
# Resampling
# ---------------------------------------------------------------------------
def resample_dataframe(
    df: pd.DataFrame,
    period_sec: int,
    aggregator: str = "mean",
) -> pd.DataFrame:
    """Resample a datetime-indexed DataFrame to a uniform period.

    Parameters
    ----------
    df : DataFrame
        Must have a ``DatetimeIndex``.
    period_sec : int
        Target sample period in seconds (1-3600).
    aggregator : str
        How to aggregate bins: ``mean``, ``median``, ``last``, ``first``.

    Returns
    -------
    DataFrame
        Resampled data.  Non-numeric columns are forward-filled.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("resample_dataframe requires a DatetimeIndex")

    rule = f"{int(period_sec)}s"

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

    agg_map = {
        "mean": "mean", "median": "median",
        "last": "last", "first": "first",
    }
    if aggregator not in agg_map:
        raise ValueError(f"unknown aggregator: {aggregator}")

    parts = []
    if numeric_cols:
        num_df = df[numeric_cols].resample(rule).agg(agg_map[aggregator])
        parts.append(num_df)
    if non_numeric_cols:
        non_df = df[non_numeric_cols].resample(rule).first().ffill()
        parts.append(non_df)

    if not parts:
        return df.resample(rule).mean()
    return pd.concat(parts, axis=1)[df.columns]


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------
def _compute_rate_stats(
    raw_series: pd.Series,
    resampled_series: pd.Series,
    col: str,
    period_sec: int,
) -> ResampleRateStats:
    """Compute noise-ratio and signal-preservation for one variable at one rate."""
    raw_diff_std = float(raw_series.diff().dropna().std())
    res_diff_std = float(resampled_series.diff().dropna().std())

    raw_std = float(raw_series.std())
    res_std = float(resampled_series.std())

    noise_ratio = (res_diff_std / raw_diff_std) if raw_diff_std > 1e-15 else 1.0
    signal_pres = (res_std / raw_std * 100.0) if raw_std > 1e-15 else 100.0

    return ResampleRateStats(
        variable=col,
        period_sec=period_sec,
        n_samples=len(resampled_series.dropna()),
        noise_ratio=noise_ratio,
        signal_preservation=signal_pres,
        mean_raw=float(raw_series.mean()),
        mean_resampled=float(resampled_series.mean()),
    )


# ---------------------------------------------------------------------------
# Multi-rate analysis
# ---------------------------------------------------------------------------
def analyze_resample_rates(
    df: pd.DataFrame,
    candidates: Optional[Sequence[int]] = None,
    columns: Optional[List[str]] = None,
) -> ResampleAnalysis:
    """Evaluate multiple resample rates and quantify noise vs signal trade-off.

    Parameters
    ----------
    df : DataFrame
        Raw data with ``DatetimeIndex``.
    candidates : sequence of int, optional
        Candidate periods in seconds.  Default: [5, 10, 15, 30, 60, 120, 300, 600].
    columns : list[str], optional
        Numeric columns to analyze.  Default: all numeric columns.

    Returns
    -------
    ResampleAnalysis
        Per-variable and aggregate statistics for each candidate rate.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("analyze_resample_rates requires a DatetimeIndex")

    if candidates is None:
        candidates = [5, 10, 15, 30, 60, 120, 300, 600]

    cols = columns or df.select_dtypes(include=[np.number]).columns.tolist()

    result = ResampleAnalysis(candidates=list(candidates))

    for col in cols:
        raw = df[col].dropna()
        if len(raw) < 20:
            continue
        result.per_variable[col] = []

        for period in candidates:
            try:
                resampled = resample_dataframe(
                    df[[col]].dropna(), period, "mean")[col]
            except Exception:
                continue
            if len(resampled.dropna()) < 5:
                continue
            stats = _compute_rate_stats(raw, resampled, col, period)
            result.per_variable[col].append(stats)

    # Build aggregate (average across variables per rate)
    for period in candidates:
        noise_vals = []
        signal_vals = []
        n_samples_vals = []
        for col, stats_list in result.per_variable.items():
            for s in stats_list:
                if s.period_sec == period:
                    noise_vals.append(s.noise_ratio)
                    signal_vals.append(s.signal_preservation)
                    n_samples_vals.append(s.n_samples)
        if noise_vals:
            result.aggregate.append({
                "period_sec": period,
                "noise_ratio": float(np.mean(noise_vals)),
                "signal_preservation": float(np.mean(signal_vals)),
                "n_samples": int(np.mean(n_samples_vals)),
            })

    return result


# ---------------------------------------------------------------------------
# Auto-suggest
# ---------------------------------------------------------------------------
def suggest_resample_rate(
    analysis: ResampleAnalysis,
    max_noise_ratio: float = 0.6,
    min_signal_pct: float = 85.0,
    min_samples: int = 20,
) -> Optional[ResampleSuggestion]:
    """Pick the optimal resample rate from an analysis.

    Finds the *smallest* period (least data loss) where:

    - ``noise_ratio < max_noise_ratio``  (enough noise reduction)
    - ``signal_preservation > min_signal_pct``  (don't smear dynamics)
    - ``n_samples >= min_samples``  (enough data points)

    Returns ``None`` if no candidate meets all three criteria.
    """
    for row in sorted(analysis.aggregate, key=lambda r: r["period_sec"]):
        nr = row["noise_ratio"]
        sp = row["signal_preservation"]
        ns = row["n_samples"]
        if nr < max_noise_ratio and sp > min_signal_pct and ns >= min_samples:
            return ResampleSuggestion(
                period_sec=row["period_sec"],
                noise_ratio=nr,
                signal_preservation=sp,
                n_samples=ns,
                reason=(
                    f"Smallest period with noise ratio {nr:.1%} < "
                    f"{max_noise_ratio:.0%} and signal preservation "
                    f"{sp:.1f}% > {min_signal_pct:.0f}%"
                ),
            )
    return None
