"""Steady-state detection for step-test data using the Aspen IQ dual
exponential filter algorithm.

The core idea: apply two exponential filters with different time constants
(a *heavy* filter that tracks the long-term trend and a *light* filter
that responds faster to transients).  When the difference between the
two is small relative to the process noise (< 3 sigma), the signal is
considered at steady state.

Individual per-variable steady-state indicators are combined into a
weighted total (``SSTOTAL``) using user-assigned importance ranks.
The plant-wide "is steady" flag fires when ``SSTOTAL >= 50%``.

References
----------
- Aspen IQ Steady-State Detection (SSD) algorithm documentation
- Rhinehart, R.R. (2013), *Automated Steady and Transient State
  Identification in Noisy Processes*, ACC.

Usage::

    cfg = auto_configure_ssd(df, columns=["TI101", "FI201"])
    result = compute_ssd(df, cfg)
    print(result.summary())
    # result.is_steady_total  -> bool array, True where plant is at SS
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class SSDVariableConfig:
    """Per-variable tuning for the dual-filter SSD algorithm.

    Parameters
    ----------
    heavy_filter : float
        Alpha for the heavy (slow) exponential filter, range (0, 1].
        Smaller values = smoother baseline.  Typical: 0.01 - 0.1.
    filter_ratio : float
        Ratio of light-filter alpha to heavy-filter alpha.  Must be >= 1.
        The light filter responds ``filter_ratio`` times faster.
    std_dev : float
        Noise standard deviation.  The 3-sigma band defines the
        steady-state threshold: ``|heavy - light| <= 3 * std_dev``.
    rank : float
        Importance weight [0-10] for the weighted SSTOTAL.  0 = excluded.
    """
    heavy_filter: float = 0.05
    filter_ratio: float = 5.0
    std_dev: float = 1.0
    rank: float = 1.0


@dataclass
class SSDConfig:
    """Global SSD configuration with per-variable entries."""
    variables: Dict[str, SSDVariableConfig] = field(default_factory=dict)
    ss_threshold_pct: float = 50.0   # SSTOTAL >= this -> steady


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class SSDVariableResult:
    """SSD output for a single variable."""
    name: str
    heavy_filtered: np.ndarray     # heavy exponential filter output
    light_filtered: np.ndarray     # light exponential filter output
    ss_pct: np.ndarray             # per-sample steady-state % (0 or 100)
    is_steady: np.ndarray          # boolean array


@dataclass
class SSDResult:
    """SSD output for the full dataset."""
    variables: Dict[str, SSDVariableResult] = field(default_factory=dict)
    ss_total: np.ndarray = field(default_factory=lambda: np.array([]))
    is_steady_total: np.ndarray = field(default_factory=lambda: np.array([]))
    n_samples: int = 0

    @property
    def steady_fraction(self) -> float:
        """Fraction of samples where the plant-wide flag is True."""
        if self.n_samples == 0:
            return 0.0
        return float(self.is_steady_total.sum()) / self.n_samples

    def summary(self) -> str:
        lines = [f"SSD: {self.n_samples} samples, "
                 f"{self.steady_fraction:.1%} steady-state"]
        for name, vr in self.variables.items():
            frac = float(vr.is_steady.sum()) / max(len(vr.is_steady), 1)
            lines.append(f"  {name}: {frac:.1%} steady")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core per-variable SSD
# ---------------------------------------------------------------------------
def compute_ssd_per_variable(
    values: np.ndarray,
    config: SSDVariableConfig,
) -> SSDVariableResult:
    """Compute the dual-filter SSD for one variable.

    Implements the Aspen IQ algorithm:
      HVYFILTPV[k] = alpha_h * x[k] + (1 - alpha_h) * HVYFILTPV[k-1]
      LITFILTPV[k] = alpha_l * x[k] + (1 - alpha_l) * LITFILTPV[k-1]
      is_steady[k] = |HVYFILTPV[k] - LITFILTPV[k]| <= 3 * std_dev
    """
    n = len(values)
    alpha_h = float(np.clip(config.heavy_filter, 1e-6, 1.0))
    alpha_l = float(np.clip(alpha_h * config.filter_ratio, alpha_h, 1.0))
    threshold = 3.0 * config.std_dev

    heavy = np.empty(n, dtype=np.float64)
    light = np.empty(n, dtype=np.float64)

    # Initialize both filters at the first value
    heavy[0] = values[0]
    light[0] = values[0]

    for i in range(1, n):
        heavy[i] = alpha_h * values[i] + (1.0 - alpha_h) * heavy[i - 1]
        light[i] = alpha_l * values[i] + (1.0 - alpha_l) * light[i - 1]

    diff = np.abs(heavy - light)
    is_steady = diff <= threshold

    # ss_pct: 0 or 100 per sample (binary for the per-variable indicator)
    ss_pct = np.where(is_steady, 100.0, 0.0)

    return SSDVariableResult(
        name="",
        heavy_filtered=heavy,
        light_filtered=light,
        ss_pct=ss_pct,
        is_steady=is_steady,
    )


# ---------------------------------------------------------------------------
# Weighted total
# ---------------------------------------------------------------------------
def compute_ssd_total(
    variable_results: Dict[str, SSDVariableResult],
    config: SSDConfig,
) -> Tuple[np.ndarray, np.ndarray]:
    """Combine per-variable SSD indicators into a weighted SSTOTAL.

    SSTOTAL[k] = sum(ss_pct_i[k] * rank_i) / sum(rank_i)
    is_steady_total[k] = SSTOTAL[k] >= ss_threshold_pct
    """
    if not variable_results:
        return np.array([]), np.array([], dtype=bool)

    # Determine length from the first variable
    n = len(next(iter(variable_results.values())).ss_pct)
    weighted_sum = np.zeros(n, dtype=np.float64)
    rank_sum = 0.0

    for name, vr in variable_results.items():
        rank = config.variables.get(name, SSDVariableConfig()).rank
        if rank <= 0:
            continue
        weighted_sum += vr.ss_pct * rank
        rank_sum += rank

    if rank_sum <= 0:
        ss_total = np.zeros(n)
    else:
        ss_total = weighted_sum / rank_sum

    is_steady_total = ss_total >= config.ss_threshold_pct
    return ss_total, is_steady_total


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def compute_ssd(
    df: pd.DataFrame,
    config: SSDConfig,
    columns: Optional[List[str]] = None,
) -> SSDResult:
    """Run steady-state detection on a DataFrame.

    Parameters
    ----------
    df : DataFrame
        Process data with numeric columns.
    config : SSDConfig
        Per-variable tuning.
    columns : list[str], optional
        Restrict to these columns.  Default: all columns in ``config.variables``.

    Returns
    -------
    SSDResult
        Per-variable and plant-wide steady-state indicators.
    """
    cols = columns or list(config.variables.keys())
    cols = [c for c in cols if c in df.columns
            and pd.api.types.is_numeric_dtype(df[c])]

    variable_results: Dict[str, SSDVariableResult] = {}
    for col in cols:
        vcfg = config.variables.get(col, SSDVariableConfig())
        values = df[col].to_numpy(dtype=np.float64)
        # Forward-fill NaN for the filter (NaN breaks the recursion)
        mask = np.isnan(values)
        if mask.any():
            s = pd.Series(values).ffill().bfill()
            values = s.to_numpy(dtype=np.float64)

        vr = compute_ssd_per_variable(values, vcfg)
        vr.name = col
        variable_results[col] = vr

    ss_total, is_steady_total = compute_ssd_total(variable_results, config)

    return SSDResult(
        variables=variable_results,
        ss_total=ss_total,
        is_steady_total=is_steady_total,
        n_samples=len(df),
    )


# ---------------------------------------------------------------------------
# Auto-configuration
# ---------------------------------------------------------------------------
def auto_configure_ssd(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    default_rank: float = 1.0,
) -> SSDConfig:
    """Build SSD config from data statistics.

    Heuristics
    ----------
    - ``std_dev`` = first-difference standard deviation (noise estimate).
    - ``heavy_filter`` scaled by ``noise_ratio = diff_std / signal_std``.
      High noise -> smaller alpha (more smoothing).  Clamped to [0.01, 0.3].
    - ``filter_ratio`` fixed at 5.0 (industry standard).

    Parameters
    ----------
    df : DataFrame
        Raw process data.
    columns : list[str], optional
        Columns to configure.  Default: all numeric columns.
    default_rank : float
        Default importance rank for all variables.
    """
    cols = columns or [c for c in df.columns
                       if pd.api.types.is_numeric_dtype(df[c])]

    variables: Dict[str, SSDVariableConfig] = {}
    for col in cols:
        s = df[col].dropna()
        if len(s) < 10:
            continue

        diff_std = float(s.diff().dropna().std())
        signal_std = float(s.std())

        # Noise ratio: how noisy is the signal relative to its total spread?
        if signal_std > 1e-15:
            noise_ratio = diff_std / signal_std
        else:
            noise_ratio = 1.0

        # Heavy filter: more noise -> more smoothing (smaller alpha)
        heavy_alpha = float(np.clip(0.15 * (1.0 - noise_ratio), 0.01, 0.3))

        variables[col] = SSDVariableConfig(
            heavy_filter=heavy_alpha,
            filter_ratio=5.0,
            std_dev=diff_std if diff_std > 1e-15 else 1.0,
            rank=default_rank,
        )

    return SSDConfig(variables=variables)
