"""Industrial-grade data conditioning for process control identification.

Provides per-variable fault detection (cutoff violations, flatline, spikes)
with configurable bad-data replacement strategies and statistics-based
auto-configuration.  Designed for refinery / chemical-plant historian data
where sensor faults, instrument saturation, and communication dropouts are
routine.

Key capabilities
----------------
- **Cutoff detection** -- upper / lower engineering limits with clamp or
  reject action.
- **Flatline detection** -- accumulator that fires when the absolute change
  stays below a threshold for *N* consecutive samples.
- **Spike detection** -- flags sample-to-sample jumps exceeding a threshold;
  reclassifies a spike as a genuine step if it persists for *N* consecutive
  samples.
- **Bad-data replacement** -- three strategies: linear interpolation between
  last-good and first-good, last-good-value hold, or mean of all good
  samples.  A ``max_consecutive_bad`` guard prevents run-away interpolation.
- **Auto-configuration** -- builds per-variable configs from descriptive
  statistics (mean, std, range, first-difference std).

Usage::

    cfg = auto_configure(df)        # one-shot from data statistics
    df_clean, stats = condition_dataframe(df, cfg)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class CutoffAction(str, Enum):
    """What to do when a value exceeds a cutoff limit."""
    CLAMP = "clamp"     # replace with the limit value
    REJECT = "reject"   # mark as bad (NaN)


class BadDataMethod(str, Enum):
    """Replacement strategy for samples marked as bad."""
    INTERPOLATE = "interpolate"   # linear interp between last-good & first-good
    LAST_GOOD = "last_good"       # hold last known good value
    AVERAGE = "average"           # replace with mean of all good samples


# ---------------------------------------------------------------------------
# Per-variable configuration
# ---------------------------------------------------------------------------
@dataclass
class VariableConditionConfig:
    """Conditioning parameters for a single variable (column)."""
    enabled: bool = True

    # Cutoff limits
    upper_cutoff: Optional[float] = None
    lower_cutoff: Optional[float] = None
    cutoff_action: CutoffAction = CutoffAction.REJECT

    # Flatline detection
    flatline_threshold: float = 0.0       # min absolute change per sample
    flatline_period: int = 10             # consecutive samples to trigger

    # Spike detection
    spike_threshold: float = 0.0          # max abs sample-to-sample change
    spike_reclassify_period: int = 3      # if the "spike" persists this many
                                          # samples it is reclassified as real

    # Bad-data replacement
    bad_data_method: BadDataMethod = BadDataMethod.INTERPOLATE


# ---------------------------------------------------------------------------
# Global conditioning configuration
# ---------------------------------------------------------------------------
@dataclass
class ConditioningEngineConfig:
    """Global knobs plus per-variable overrides.

    ``variables`` maps column-name -> ``VariableConditionConfig``.
    Columns not in this dict are passed through unchanged.
    """
    bad_data_method: BadDataMethod = BadDataMethod.INTERPOLATE
    max_consecutive_bad: int = 50   # safety limit on run-away replacement

    variables: Dict[str, VariableConditionConfig] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-variable statistics (returned alongside the conditioned frame)
# ---------------------------------------------------------------------------
@dataclass
class VariableConditionStats:
    """Diagnostic counters for one variable after conditioning."""
    name: str
    n_cutoff_upper: int = 0
    n_cutoff_lower: int = 0
    n_flatline: int = 0
    n_spike: int = 0
    n_bad_replaced: int = 0
    n_unreplaceable: int = 0     # exceeded max_consecutive_bad
    mean: float = 0.0
    std: float = 0.0
    variance: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0


@dataclass
class ConditioningEngineReport:
    """Aggregate report for a full conditioning run."""
    n_rows: int = 0
    variable_stats: Dict[str, VariableConditionStats] = field(default_factory=dict)

    def total_faults(self) -> int:
        return sum(
            s.n_cutoff_upper + s.n_cutoff_lower + s.n_flatline + s.n_spike
            for s in self.variable_stats.values()
        )

    def summary(self) -> str:
        lines = [f"Data conditioning: {self.n_rows} rows, "
                 f"{len(self.variable_stats)} variables, "
                 f"{self.total_faults()} total faults detected"]
        for name, s in self.variable_stats.items():
            faults = (s.n_cutoff_upper + s.n_cutoff_lower
                      + s.n_flatline + s.n_spike)
            if faults > 0:
                parts = []
                if s.n_cutoff_upper:
                    parts.append(f"hi={s.n_cutoff_upper}")
                if s.n_cutoff_lower:
                    parts.append(f"lo={s.n_cutoff_lower}")
                if s.n_flatline:
                    parts.append(f"flat={s.n_flatline}")
                if s.n_spike:
                    parts.append(f"spike={s.n_spike}")
                lines.append(f"  {name}: {', '.join(parts)}  "
                             f"replaced={s.n_bad_replaced}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Detection functions (operate on numpy arrays for speed)
# ---------------------------------------------------------------------------
def detect_cutoff_violations(
    values: np.ndarray,
    upper: Optional[float],
    lower: Optional[float],
) -> np.ndarray:
    """Return boolean mask where True = violates a cutoff limit."""
    bad = np.zeros(len(values), dtype=bool)
    if upper is not None:
        bad |= values > upper
    if lower is not None:
        bad |= values < lower
    return bad


def detect_flatline(
    values: np.ndarray,
    threshold: float,
    period: int,
) -> np.ndarray:
    """Detect flatline (frozen sensor) using a consecutive-sample accumulator.

    A sample is marked as flatline if the absolute change from the previous
    sample has been below ``threshold`` for at least ``period`` consecutive
    samples.
    """
    n = len(values)
    bad = np.zeros(n, dtype=bool)
    if threshold <= 0 or period <= 0 or n < 2:
        return bad

    run_length = 0
    for i in range(1, n):
        if abs(values[i] - values[i - 1]) < threshold:
            run_length += 1
        else:
            run_length = 0
        if run_length >= period:
            bad[i] = True
    return bad


def detect_spikes(
    values: np.ndarray,
    threshold: float,
    reclassify_period: int,
) -> np.ndarray:
    """Detect spikes (sudden jumps) and reclassify persistent ones as real.

    A spike is a sample whose absolute change from the previous sample
    exceeds ``threshold``.  If the new level persists for
    ``reclassify_period`` consecutive samples the spike is reclassified
    as a genuine step change and the bad flag is cleared.

    A classic spike (up then back down) produces two threshold crossings.
    The second crossing finalizes the first batch as confirmed spikes
    before starting a new batch.
    """
    n = len(values)
    bad = np.zeros(n, dtype=bool)
    if threshold <= 0 or n < 2:
        return bad

    pending_spikes: List[int] = []
    persist_count = 0

    for i in range(1, n):
        delta = abs(values[i] - values[i - 1])
        if delta > threshold:
            # A new threshold crossing -- finalize any pending batch
            # as confirmed spikes (they didn't persist long enough)
            for idx in pending_spikes:
                bad[idx] = True
            # Start a fresh batch with this crossing
            pending_spikes = [i]
            persist_count = 1
        elif pending_spikes:
            # Small change -- count persistence at the new level
            persist_count += 1
            if persist_count >= reclassify_period:
                # Level persisted: reclassify as a real step change
                pending_spikes.clear()
                persist_count = 0

    # Finalize anything still pending at end of signal
    for idx in pending_spikes:
        bad[idx] = True
    return bad


# ---------------------------------------------------------------------------
# Bad-data replacement
# ---------------------------------------------------------------------------
def replace_bad_data(
    values: np.ndarray,
    bad_mask: np.ndarray,
    method: BadDataMethod = BadDataMethod.INTERPOLATE,
    max_consecutive: int = 50,
) -> Tuple[np.ndarray, int, int]:
    """Replace bad samples according to *method*.

    Returns
    -------
    replaced : ndarray
        Copy of *values* with bad samples replaced.
    n_replaced : int
        Number of samples successfully replaced.
    n_unreplaceable : int
        Number of samples in runs longer than *max_consecutive* (left as NaN).
    """
    out = values.copy().astype(np.float64)
    n = len(out)
    n_replaced = 0
    n_unreplaceable = 0

    if not bad_mask.any():
        return out, 0, 0

    # Mark bad as NaN first
    out[bad_mask] = np.nan

    if method == BadDataMethod.AVERAGE:
        good_mean = np.nanmean(out)
        if np.isfinite(good_mean):
            # Check run lengths
            run_start = None
            for i in range(n + 1):
                is_bad = i < n and bad_mask[i]
                if is_bad and run_start is None:
                    run_start = i
                elif not is_bad and run_start is not None:
                    run_len = i - run_start
                    if run_len <= max_consecutive:
                        out[run_start:i] = good_mean
                        n_replaced += run_len
                    else:
                        n_unreplaceable += run_len
                    run_start = None
        return out, n_replaced, n_unreplaceable

    if method == BadDataMethod.LAST_GOOD:
        last_good = np.nan
        run_start = None
        for i in range(n):
            if bad_mask[i]:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None:
                    run_len = i - run_start
                    if run_len <= max_consecutive and np.isfinite(last_good):
                        out[run_start:i] = last_good
                        n_replaced += run_len
                    else:
                        n_unreplaceable += run_len
                    run_start = None
                last_good = out[i]
        # Trailing run
        if run_start is not None:
            run_len = n - run_start
            if run_len <= max_consecutive and np.isfinite(last_good):
                out[run_start:n] = last_good
                n_replaced += run_len
            else:
                n_unreplaceable += run_len
        return out, n_replaced, n_unreplaceable

    # Default: INTERPOLATE
    run_start = None
    for i in range(n + 1):
        is_bad = i < n and bad_mask[i]
        if is_bad and run_start is None:
            run_start = i
        elif not is_bad and run_start is not None:
            run_len = i - run_start
            if run_len > max_consecutive:
                n_unreplaceable += run_len
                run_start = None
                continue
            # Find last good before and first good after
            before_val = out[run_start - 1] if run_start > 0 else np.nan
            after_val = out[i] if i < n else np.nan
            if np.isfinite(before_val) and np.isfinite(after_val):
                interp = np.linspace(before_val, after_val, run_len + 2)[1:-1]
                out[run_start:i] = interp
            elif np.isfinite(before_val):
                out[run_start:i] = before_val
            elif np.isfinite(after_val):
                out[run_start:i] = after_val
            n_replaced += run_len
            run_start = None
    # Trailing run
    if run_start is not None:
        run_len = n - run_start
        if run_len <= max_consecutive:
            before_val = out[run_start - 1] if run_start > 0 else np.nan
            if np.isfinite(before_val):
                out[run_start:n] = before_val
                n_replaced += run_len
            else:
                n_unreplaceable += run_len
        else:
            n_unreplaceable += run_len

    return out, n_replaced, n_unreplaceable


# ---------------------------------------------------------------------------
# Auto-configure from statistics
# ---------------------------------------------------------------------------
def auto_configure(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
) -> ConditioningEngineConfig:
    """Build a ``ConditioningEngineConfig`` from data statistics.

    For each numeric column the heuristics are:

    - Cutoff limits: mean +/- 6 * std
    - Flatline threshold: 0.1 % of the variable's range
    - Flatline period: adaptive 30-360 based on coefficient of variation
    - Spike threshold: 5 * first-difference std
    """
    cols = columns or [c for c in df.columns
                       if pd.api.types.is_numeric_dtype(df[c])]
    variables: Dict[str, VariableConditionConfig] = {}

    for col in cols:
        s = df[col].dropna()
        if len(s) < 10:
            continue
        mean = float(s.mean())
        std = float(s.std())
        rng = float(s.max() - s.min())
        diff_std = float(s.diff().dropna().std())

        # Cutoff: 6-sigma
        upper = mean + 6.0 * std if std > 1e-15 else None
        lower = mean - 6.0 * std if std > 1e-15 else None

        # Flatline threshold: 0.1% of range
        flat_thresh = rng * 0.001 if rng > 1e-15 else 0.0

        # Adaptive flatline period based on coefficient of variation
        if std > 1e-15:
            cv = diff_std / std
            # Low-variance signals need shorter periods to catch flatline
            flat_period = int(np.clip(30 + 330 * (1.0 - cv), 30, 360))
        else:
            flat_period = 30

        # Spike threshold: 5x first-difference std
        spike_thresh = 5.0 * diff_std if diff_std > 1e-15 else 0.0

        variables[col] = VariableConditionConfig(
            upper_cutoff=upper,
            lower_cutoff=lower,
            cutoff_action=CutoffAction.REJECT,
            flatline_threshold=flat_thresh,
            flatline_period=flat_period,
            spike_threshold=spike_thresh,
            spike_reclassify_period=3,
            bad_data_method=BadDataMethod.INTERPOLATE,
        )

    return ConditioningEngineConfig(variables=variables)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def condition_dataframe(
    df: pd.DataFrame,
    config: ConditioningEngineConfig,
    columns: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, ConditioningEngineReport]:
    """Apply the full conditioning pipeline to a DataFrame.

    Parameters
    ----------
    df : DataFrame
        Raw historian data (numeric columns).
    config : ConditioningEngineConfig
        Global + per-variable configuration.
    columns : list[str], optional
        Restrict conditioning to these columns.  Default: all columns
        that have a ``VariableConditionConfig`` entry.

    Returns
    -------
    df_clean : DataFrame
        Conditioned copy of *df*.
    report : ConditioningEngineReport
        Per-variable diagnostic counters and statistics.
    """
    df_out = df.copy()
    report = ConditioningEngineReport(n_rows=len(df))

    cols = columns or list(config.variables.keys())
    cols = [c for c in cols if c in df_out.columns
            and pd.api.types.is_numeric_dtype(df_out[c])]

    for col in cols:
        vcfg = config.variables.get(col, VariableConditionConfig())
        if not vcfg.enabled:
            continue

        values = df_out[col].to_numpy(dtype=np.float64)
        stats = VariableConditionStats(name=col)

        # --- Cutoff violations ---
        cutoff_mask = detect_cutoff_violations(
            values, vcfg.upper_cutoff, vcfg.lower_cutoff)

        if vcfg.cutoff_action == CutoffAction.CLAMP and cutoff_mask.any():
            if vcfg.upper_cutoff is not None:
                hi = values > vcfg.upper_cutoff
                values[hi] = vcfg.upper_cutoff
                stats.n_cutoff_upper = int(hi.sum())
            if vcfg.lower_cutoff is not None:
                lo = values < vcfg.lower_cutoff
                values[lo] = vcfg.lower_cutoff
                stats.n_cutoff_lower = int(lo.sum())
            cutoff_mask[:] = False   # already handled by clamping
        else:
            stats.n_cutoff_upper = int(
                (values > vcfg.upper_cutoff).sum()
                if vcfg.upper_cutoff is not None else 0)
            stats.n_cutoff_lower = int(
                (values < vcfg.lower_cutoff).sum()
                if vcfg.lower_cutoff is not None else 0)

        # --- Flatline detection ---
        flatline_mask = detect_flatline(
            values, vcfg.flatline_threshold, vcfg.flatline_period)
        stats.n_flatline = int(flatline_mask.sum())

        # --- Spike detection ---
        spike_mask = detect_spikes(
            values, vcfg.spike_threshold, vcfg.spike_reclassify_period)
        stats.n_spike = int(spike_mask.sum())

        # --- Combine all bad-data masks ---
        combined_bad = cutoff_mask | flatline_mask | spike_mask

        # --- Replace bad data ---
        method = vcfg.bad_data_method or config.bad_data_method
        replaced, n_rep, n_unrep = replace_bad_data(
            values, combined_bad, method, config.max_consecutive_bad)
        stats.n_bad_replaced = n_rep
        stats.n_unreplaceable = n_unrep

        df_out[col] = replaced

        # --- Post-conditioning statistics ---
        clean = df_out[col].dropna()
        if len(clean) > 0:
            stats.mean = float(clean.mean())
            stats.std = float(clean.std())
            stats.variance = float(clean.var())
            stats.skewness = float(clean.skew())
            stats.kurtosis = float(clean.kurtosis())

        report.variable_stats[col] = stats

    return df_out, report
