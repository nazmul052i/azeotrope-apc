"""Ramp and pseudoramp CV handling for integrating processes.

Many industrial process variables are integrators (levels, inventories,
slow temperature drifts).  Their step response does not settle -- it
ramps indefinitely.  Standard FIR identification assumes a settling
process, so integrating CVs need special preprocessing:

- **Ramp**: The CV has a pure integrator.  Preprocessing: first-difference
  the CV (Δy[k] = y[k] - y[k-1]) to convert the ramp into a step-like
  response.  The identified model is then in "rate" form.

- **Pseudoramp**: The CV is a slow integrator with a very long time constant
  that *looks* like a ramp over the test duration.  Preprocessing: remove
  a linear trend (detrend) from the CV, then identify normally.

After identification the coefficients are adjusted back to represent
the actual integrating behavior.

Usage::

    # Preprocess for ramp CV
    y_diff, y_mean = preprocess_ramp(y_raw)

    # Preprocess for pseudoramp CV
    y_detrended, trend = preprocess_pseudoramp(y_raw)

    # After identification, convert coefficients back
    step_integrating = ramp_to_step(fir_rate, n_coeff)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class CVType(str, Enum):
    """CV type classification."""
    NONE = "none"           # Normal settling CV
    RAMP = "ramp"           # Pure integrator (Δy preprocessing)
    PSEUDORAMP = "pseudoramp"  # Slow integrator (detrend preprocessing)


@dataclass
class RampPreprocessResult:
    """Result of ramp/pseudoramp preprocessing."""
    y_processed: np.ndarray       # preprocessed CV data
    cv_type: CVType
    y_mean: float = 0.0          # subtracted mean (ramp)
    trend_slope: float = 0.0     # removed trend slope (pseudoramp)
    trend_intercept: float = 0.0


def detect_cv_type(
    y: np.ndarray,
    threshold_ramp: float = 0.8,
    threshold_pseudo: float = 0.5,
) -> CVType:
    """Auto-detect whether a CV is integrating.

    Heuristic: compare the variance of the first-differenced signal
    to the variance of the detrended signal.  If differencing reduces
    variance much more than detrending, it's likely a ramp.

    Parameters
    ----------
    y : ndarray (N,)
        CV time series.
    threshold_ramp : float
        If var(Δy)/var(y) < threshold_ramp AND the signal has a strong
        linear trend, classify as RAMP.
    threshold_pseudo : float
        If the linear trend R² > threshold_pseudo, classify as PSEUDORAMP.
    """
    if len(y) < 20:
        return CVType.NONE

    y_clean = y[~np.isnan(y)]
    if len(y_clean) < 20:
        return CVType.NONE

    var_y = np.var(y_clean)
    if var_y < 1e-15:
        return CVType.NONE

    # First difference variance
    dy = np.diff(y_clean)
    var_dy = np.var(dy)
    ratio = var_dy / var_y

    # Linear trend fit
    x = np.arange(len(y_clean), dtype=float)
    coeffs = np.polyfit(x, y_clean, 1)
    trend = np.polyval(coeffs, x)
    ss_res = np.sum((y_clean - trend) ** 2)
    ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
    r2_trend = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0

    # Pure ramp: differencing dramatically reduces variance AND strong trend
    if ratio < 0.1 and r2_trend > threshold_ramp:
        return CVType.RAMP

    # Pseudoramp: moderate trend
    if r2_trend > threshold_pseudo and ratio < 0.3:
        return CVType.PSEUDORAMP

    return CVType.NONE


def preprocess_ramp(y: np.ndarray) -> RampPreprocessResult:
    """Preprocess a ramp (integrating) CV by first-differencing.

    Δy[k] = y[k] - y[k-1]

    The identified FIR will represent the *rate* response.
    """
    y_mean = float(np.nanmean(y))
    dy = np.diff(y, prepend=y[0])
    return RampPreprocessResult(
        y_processed=dy,
        cv_type=CVType.RAMP,
        y_mean=y_mean,
    )


def preprocess_pseudoramp(y: np.ndarray) -> RampPreprocessResult:
    """Preprocess a pseudoramp CV by removing a linear trend.

    y_detrended = y - (slope * t + intercept)
    """
    x = np.arange(len(y), dtype=float)
    # Handle NaN
    valid = ~np.isnan(y)
    if valid.sum() < 2:
        return RampPreprocessResult(y_processed=y.copy(), cv_type=CVType.PSEUDORAMP)

    coeffs = np.polyfit(x[valid], y[valid], 1)
    slope, intercept = float(coeffs[0]), float(coeffs[1])
    trend = slope * x + intercept
    y_detrended = y - trend

    return RampPreprocessResult(
        y_processed=y_detrended,
        cv_type=CVType.PSEUDORAMP,
        trend_slope=slope,
        trend_intercept=intercept,
    )


def preprocess_cv(
    y: np.ndarray,
    cv_type: Optional[CVType] = None,
) -> RampPreprocessResult:
    """Preprocess a CV based on its type (auto-detect if not specified)."""
    if cv_type is None:
        cv_type = detect_cv_type(y)

    if cv_type == CVType.RAMP:
        return preprocess_ramp(y)
    elif cv_type == CVType.PSEUDORAMP:
        return preprocess_pseudoramp(y)
    else:
        return RampPreprocessResult(
            y_processed=y.copy(),
            cv_type=CVType.NONE,
        )


def ramp_to_step(fir_rate: np.ndarray, n_coeff: int) -> np.ndarray:
    """Convert rate-form FIR coefficients back to integrating step response.

    For a ramp CV, the identified FIR represents the rate response.
    The actual step response is the cumulative sum of the rate response.
    """
    step = np.cumsum(fir_rate[:n_coeff])
    return step


def typical_move_scale(
    step_response: np.ndarray,
    typical_moves: np.ndarray,
) -> np.ndarray:
    """Scale step response matrix by typical move sizes.

    Parameters
    ----------
    step_response : ndarray, shape (ny, n_coeff, nu)
        Raw step response (per unit input).
    typical_moves : ndarray, shape (nu,)
        Typical move size for each MV.

    Returns
    -------
    ndarray, shape (ny, n_coeff, nu)
        Scaled step response (response to typical move).
    """
    sr = step_response.copy()
    for j in range(sr.shape[2]):
        sr[:, :, j] *= typical_moves[j]
    return sr
