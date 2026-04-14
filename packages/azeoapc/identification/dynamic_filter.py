"""Dynamic input filtering: dead time + cascaded 1st/2nd-order filters
with cross-correlation-based auto-tuning.

In model identification the MV and DV inputs are often much noisier
than the underlying process dynamics.  Applying a matched filter that
mirrors the process dead time and lag improves signal-to-noise for the
identification engine without introducing artificial model artefacts.

The filter chain for each input is:

    raw -> dead-time shift -> 1st-order filter -> optional 2nd-order filter

Parameters can be set manually or auto-tuned from cross-correlation
between each input and a designated output column.

Usage::

    # Manual
    filters = {
        "FIC101_SP": VariableFilter(dead_time_pts=3, tau1=30.0),
        "FIC102_SP": VariableFilter(dead_time_pts=5, tau1=60.0, tau2=20.0),
    }
    df_filtered = filter_dataframe(df, filters, dt=1.0)

    # Auto-tune
    filters = auto_tune_all(df, input_cols=["FIC101_SP", "FIC102_SP"],
                            output_col="TI201", dt=1.0)
    df_filtered = filter_dataframe(df, filters, dt=1.0)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class VariableFilter:
    """Filter parameters for a single input variable.

    Parameters
    ----------
    dead_time_pts : int
        Dead time (transport delay) in sample intervals.
    tau1 : float
        First-order time constant in the same units as ``dt``.
        0 or negative disables the first-order filter.
    tau2 : float
        Second-order time constant (cascaded with tau1).
        0 or negative disables the second stage.
    enabled : bool
        Master on/off switch.
    """
    dead_time_pts: int = 0
    tau1: float = 0.0
    tau2: float = 0.0
    enabled: bool = True


# ---------------------------------------------------------------------------
# Core filter primitives
# ---------------------------------------------------------------------------
def first_order_filter(
    x: np.ndarray,
    tau: float,
    dt: float,
) -> np.ndarray:
    """Apply a first-order exponential (low-pass) filter.

    y[k] = alpha * x[k] + (1 - alpha) * y[k-1]
    alpha = dt / (tau + dt)
    """
    if tau <= 0 or dt <= 0:
        return x.copy()
    alpha = dt / (tau + dt)
    y = np.empty_like(x, dtype=np.float64)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = alpha * x[i] + (1.0 - alpha) * y[i - 1]
    return y


def second_order_filter(
    x: np.ndarray,
    tau1: float,
    tau2: float,
    dt: float,
) -> np.ndarray:
    """Cascade of two first-order filters."""
    y = first_order_filter(x, tau1, dt)
    if tau2 > 0:
        y = first_order_filter(y, tau2, dt)
    return y


def apply_dead_time(
    x: np.ndarray,
    delay_pts: int,
) -> np.ndarray:
    """Shift signal forward by *delay_pts* samples, holding the first value."""
    if delay_pts <= 0:
        return x.copy()
    out = np.empty_like(x)
    out[:delay_pts] = x[0]
    out[delay_pts:] = x[:-delay_pts] if delay_pts < len(x) else x[0]
    return out


# ---------------------------------------------------------------------------
# Full filter chain for one variable
# ---------------------------------------------------------------------------
def apply_filter(
    x: np.ndarray,
    filt: VariableFilter,
    dt: float,
) -> np.ndarray:
    """Apply the full filter chain: dead time -> 1st order -> 2nd order.

    Parameters
    ----------
    x : ndarray
        Raw input signal.
    filt : VariableFilter
        Filter parameters.
    dt : float
        Sample period (seconds or consistent units).
    """
    if not filt.enabled:
        return x.copy()
    y = apply_dead_time(x, filt.dead_time_pts)
    y = first_order_filter(y, filt.tau1, dt)
    if filt.tau2 > 0:
        y = first_order_filter(y, filt.tau2, dt)
    return y


# ---------------------------------------------------------------------------
# Auto-tuning from cross-correlation
# ---------------------------------------------------------------------------
def auto_tune_filter(
    input_signal: np.ndarray,
    output_signal: np.ndarray,
    dt: float,
    max_lag: Optional[int] = None,
) -> VariableFilter:
    """Auto-tune dead time and time constant from cross-correlation.

    Algorithm
    ---------
    1. Compute normalized cross-correlation between input and output.
    2. Dead time = lag at peak |correlation|.
    3. Time constant = lag where |correlation| drops to 1/e (36.8%)
       of its peak value (measured from the dead-time lag onward).

    Parameters
    ----------
    input_signal, output_signal : ndarray
        Equal-length signals.
    dt : float
        Sample period.
    max_lag : int, optional
        Maximum lag to search (samples).  Default: half the signal length.
    """
    n = min(len(input_signal), len(output_signal))
    if n < 10:
        return VariableFilter()

    x = input_signal[:n] - np.mean(input_signal[:n])
    y = output_signal[:n] - np.mean(output_signal[:n])

    sx = np.std(x)
    sy = np.std(y)
    if sx < 1e-15 or sy < 1e-15:
        return VariableFilter()

    if max_lag is None:
        max_lag = n // 2

    # Normalized cross-correlation for positive lags
    xcorr = np.zeros(max_lag)
    for lag in range(max_lag):
        if lag >= n:
            break
        seg_x = x[:n - lag]
        seg_y = y[lag:]
        xcorr[lag] = np.mean(seg_x * seg_y) / (sx * sy)

    abs_xcorr = np.abs(xcorr)
    if abs_xcorr.max() < 1e-6:
        return VariableFilter()

    # Dead time = lag at peak correlation
    dead_time_pts = int(np.argmax(abs_xcorr))

    # Time constant = lag where correlation drops to 1/e of peak
    peak_val = abs_xcorr[dead_time_pts]
    threshold = peak_val * np.exp(-1.0)   # 36.8% of peak

    tau_pts = 0
    for lag in range(dead_time_pts, max_lag):
        if abs_xcorr[lag] < threshold:
            tau_pts = lag - dead_time_pts
            break

    tau1 = float(tau_pts) * dt

    return VariableFilter(
        dead_time_pts=dead_time_pts,
        tau1=tau1,
        tau2=0.0,
        enabled=True,
    )


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------
def filter_dataframe(
    df: pd.DataFrame,
    filters: Dict[str, VariableFilter],
    dt: float,
    columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Apply per-variable filters to a DataFrame.

    Parameters
    ----------
    df : DataFrame
        Input data.
    filters : dict
        Column-name -> VariableFilter mapping.
    dt : float
        Sample period (seconds).
    columns : list[str], optional
        Restrict to these columns.  Default: all keys in *filters*.
    """
    df_out = df.copy()
    cols = columns or list(filters.keys())

    for col in cols:
        if col not in df_out.columns:
            continue
        filt = filters.get(col)
        if filt is None or not filt.enabled:
            continue
        if not pd.api.types.is_numeric_dtype(df_out[col]):
            continue

        values = df_out[col].to_numpy(dtype=np.float64)
        # Forward-fill NaN before filtering (NaN breaks the recursion)
        mask = np.isnan(values)
        if mask.any():
            s = pd.Series(values).ffill().bfill()
            values = s.to_numpy(dtype=np.float64)

        df_out[col] = apply_filter(values, filt, dt)

    return df_out


def auto_tune_all(
    df: pd.DataFrame,
    input_cols: Sequence[str],
    output_col: str,
    dt: float,
    max_lag: Optional[int] = None,
) -> Dict[str, VariableFilter]:
    """Auto-tune filters for all input columns against a single output.

    Parameters
    ----------
    df : DataFrame
        Process data.
    input_cols : sequence of str
        MV / DV columns to filter.
    output_col : str
        CV column to cross-correlate against.
    dt : float
        Sample period (seconds).
    max_lag : int, optional
        Maximum correlation lag (samples).

    Returns
    -------
    dict
        Column-name -> VariableFilter.
    """
    if output_col not in df.columns:
        raise ValueError(f"Output column '{output_col}' not in DataFrame")

    y = df[output_col].dropna().to_numpy(dtype=np.float64)
    result: Dict[str, VariableFilter] = {}

    for col in input_cols:
        if col not in df.columns:
            logger.warning("auto_tune_all: column '%s' not found", col)
            result[col] = VariableFilter()
            continue
        x = df[col].dropna().to_numpy(dtype=np.float64)
        filt = auto_tune_filter(x, y, dt, max_lag)
        result[col] = filt
        logger.info("auto_tune %s: dead_time=%d pts, tau1=%.1f",
                     col, filt.dead_time_pts, filt.tau1)

    return result
