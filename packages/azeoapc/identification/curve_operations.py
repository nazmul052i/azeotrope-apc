"""DMC3-style curve operations on step-response coefficients.

Provides 18 operations matching the AspenTech DMC3 Model feature set.
All operations work on cumulative step-response arrays of shape
``(n_coeff,)`` and return a new array of the same shape.

Operations on existing curves
-----------------------------
ADD, SUBTRACT, GAIN, GSCALE, SHIFT, MULTIPLY, RATE, RSCALE,
FIRSTORDER, SECONDORDER, LEADLAG, ROTATE

Operations for creating curves
------------------------------
REPLACE, ZERO, UNITY, FIRSTORDER_CREATE, SECONDORDER_CREATE, CONVOLUTE

Usage::

    from azeoapc.identification.curve_operations import CurveOp, apply_op

    # Shift a curve by 3 samples (add dead time)
    shifted = apply_op(CurveOp.SHIFT, step, shift=3)

    # Apply first-order dynamics with tau=30s, dt=1s
    smoothed = apply_op(CurveOp.FIRSTORDER, step, tau=30.0, dt=1.0)

    # Scale the gain by 1.5x
    scaled = apply_op(CurveOp.GAIN, step, gain=1.5)

    # Convolute two curves
    conv = apply_op(CurveOp.CONVOLUTE, step_a, other=step_b)
"""
from __future__ import annotations

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class CurveOp(str, Enum):
    """Available curve operations."""
    # Operations on existing curves
    ADD = "add"
    SUBTRACT = "subtract"
    GAIN = "gain"
    GSCALE = "gscale"
    SHIFT = "shift"
    MULTIPLY = "multiply"
    RATE = "rate"
    RSCALE = "rscale"
    FIRSTORDER = "firstorder"
    SECONDORDER = "secondorder"
    LEADLAG = "leadlag"
    ROTATE = "rotate"
    # Operations for creating curves
    REPLACE = "replace"
    ZERO = "zero"
    UNITY = "unity"
    FIRSTORDER_CREATE = "firstorder_create"
    SECONDORDER_CREATE = "secondorder_create"
    CONVOLUTE = "convolute"


@dataclass
class CurveOpRecord:
    """Record of a single curve operation applied to an MV-CV pair."""
    op: CurveOp
    params: Dict = field(default_factory=dict)
    description: str = ""


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------
def op_add(step: np.ndarray, other: np.ndarray) -> np.ndarray:
    """Add another curve: S_new = S + S_other."""
    n = len(step)
    other_r = np.resize(other, n) if len(other) != n else other
    return step + other_r


def op_subtract(step: np.ndarray, other: np.ndarray) -> np.ndarray:
    """Subtract another curve: S_new = S - S_other."""
    n = len(step)
    other_r = np.resize(other, n) if len(other) != n else other
    return step - other_r


def op_gain(step: np.ndarray, gain: float) -> np.ndarray:
    """Apply gain multiplier: S_new = gain * S."""
    return step * gain


def op_gscale(step: np.ndarray, target_gain: float) -> np.ndarray:
    """Scale curve so steady-state gain equals target_gain."""
    ss_gain = step[-1] if len(step) > 0 else 1.0
    if abs(ss_gain) < 1e-15:
        return step.copy()
    return step * (target_gain / ss_gain)


def op_shift(step: np.ndarray, shift: int) -> np.ndarray:
    """Time-shift (dead time adjustment). Positive = add delay."""
    n = len(step)
    out = np.zeros(n)
    if shift >= 0:
        if shift < n:
            out[shift:] = step[:n - shift]
    else:
        s = abs(shift)
        if s < n:
            out[:n - s] = step[s:]
            out[n - s:] = step[-1]
    return out


def op_multiply(step: np.ndarray, scalar: float) -> np.ndarray:
    """Multiply by scalar (same as gain)."""
    return step * scalar


def op_rate(step: np.ndarray) -> np.ndarray:
    """Rate of change: convert step response to impulse response."""
    fir = np.diff(step, prepend=0.0)
    return fir


def op_rscale(step: np.ndarray, factor: float) -> np.ndarray:
    """Rate scaling: scale the impulse (FIR) coefficients, rebuild step."""
    fir = np.diff(step, prepend=0.0)
    fir_scaled = fir * factor
    return np.cumsum(fir_scaled)


def op_firstorder(step: np.ndarray, tau: float, dt: float) -> np.ndarray:
    """Apply first-order dynamics to existing curve.

    Convolves the step response with a first-order filter impulse response.
    """
    if tau <= 0 or dt <= 0:
        return step.copy()
    alpha = dt / (tau + dt)
    n = len(step)
    fir = np.diff(step, prepend=0.0)
    # Filter the FIR coefficients
    filtered_fir = np.zeros(n)
    filtered_fir[0] = alpha * fir[0]
    for k in range(1, n):
        filtered_fir[k] = alpha * fir[k] + (1.0 - alpha) * filtered_fir[k - 1]
    return np.cumsum(filtered_fir)


def op_secondorder(step: np.ndarray, tau1: float, tau2: float,
                   dt: float) -> np.ndarray:
    """Apply second-order dynamics (cascade of two first-order)."""
    s = op_firstorder(step, tau1, dt)
    return op_firstorder(s, tau2, dt)


def op_leadlag(step: np.ndarray, tau_lead: float, tau_lag: float,
               dt: float) -> np.ndarray:
    """Apply lead-lag compensation.

    G(s) = (tau_lead * s + 1) / (tau_lag * s + 1)
    """
    if dt <= 0:
        return step.copy()
    n = len(step)
    fir = np.diff(step, prepend=0.0)

    # Lead-lag in discrete time:
    # y[k] = a_lag * y[k-1] + b0 * x[k] + b1 * x[k-1]
    if tau_lag > 0:
        a_lag = np.exp(-dt / tau_lag)
    else:
        a_lag = 0.0
    if tau_lead > 0:
        b0 = (tau_lead / dt) * (1.0 - a_lag) + a_lag
        b1 = -(tau_lead / dt) * (1.0 - a_lag)
    else:
        b0 = 1.0 - a_lag
        b1 = 0.0

    out_fir = np.zeros(n)
    for k in range(n):
        out_fir[k] = b0 * fir[k]
        if k > 0:
            out_fir[k] += b1 * fir[k - 1] + a_lag * out_fir[k - 1]
    return np.cumsum(out_fir)


def op_rotate(step: np.ndarray, angle_deg: float) -> np.ndarray:
    """Rotate the step response curve (scale time axis).

    angle > 0: speed up (compress), angle < 0: slow down (stretch).
    """
    n = len(step)
    factor = 1.0 + angle_deg / 90.0
    if factor <= 0:
        return step.copy()
    x_old = np.arange(n, dtype=float)
    x_new = x_old * factor
    return np.interp(x_old, x_new, step, right=step[-1])


# ---------------------------------------------------------------------------
# Curve creation operations
# ---------------------------------------------------------------------------
def create_zero(n: int) -> np.ndarray:
    """Create a zero-gain step response."""
    return np.zeros(n)


def create_unity(n: int) -> np.ndarray:
    """Create a unity-gain step response (immediate response)."""
    return np.ones(n)


def create_firstorder(n: int, gain: float, tau: float, dt: float,
                      dead_time: int = 0) -> np.ndarray:
    """Create a first-order step response from scratch.

    S(k) = gain * (1 - exp(-(k - dead_time) * dt / tau))  for k >= dead_time
    """
    step = np.zeros(n)
    if tau <= 0 or dt <= 0:
        step[dead_time:] = gain
        return step
    for k in range(dead_time, n):
        t = (k - dead_time) * dt
        step[k] = gain * (1.0 - np.exp(-t / tau))
    return step


def create_secondorder(n: int, gain: float, tau1: float, tau2: float,
                       dt: float, dead_time: int = 0) -> np.ndarray:
    """Create a second-order (two cascaded first-order) step response."""
    if abs(tau1 - tau2) < 1e-10:
        # Equal time constants: S(t) = K * (1 - (1 + t/tau) * exp(-t/tau))
        step = np.zeros(n)
        for k in range(dead_time, n):
            t = (k - dead_time) * dt
            step[k] = gain * (1.0 - (1.0 + t / tau1) * np.exp(-t / tau1))
        return step
    # Distinct time constants
    step = np.zeros(n)
    for k in range(dead_time, n):
        t = (k - dead_time) * dt
        s1 = tau1 * np.exp(-t / tau1)
        s2 = tau2 * np.exp(-t / tau2)
        step[k] = gain * (1.0 - (s1 - s2) / (tau1 - tau2))
    return step


def convolute(step_a: np.ndarray, step_b: np.ndarray) -> np.ndarray:
    """Convolute two step responses.

    Convolves the FIR (impulse) coefficients and rebuilds the step response.
    """
    fir_a = np.diff(step_a, prepend=0.0)
    fir_b = np.diff(step_b, prepend=0.0)
    n = len(step_a)
    fir_conv = np.convolve(fir_a, fir_b)[:n]
    return np.cumsum(fir_conv)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
def apply_op(
    op: CurveOp,
    step: np.ndarray,
    other: Optional[np.ndarray] = None,
    **kwargs,
) -> np.ndarray:
    """Apply a curve operation and return the modified step response.

    Parameters
    ----------
    op : CurveOp
        Which operation to apply.
    step : ndarray
        Cumulative step response, shape (n_coeff,).
    other : ndarray, optional
        Second curve (for ADD, SUBTRACT, REPLACE, CONVOLUTE).
    **kwargs
        Operation-specific parameters: gain, shift, tau, tau1, tau2,
        dt, target_gain, scalar, factor, angle_deg, dead_time, n.
    """
    if op == CurveOp.ADD:
        return op_add(step, other)
    elif op == CurveOp.SUBTRACT:
        return op_subtract(step, other)
    elif op == CurveOp.GAIN:
        return op_gain(step, kwargs.get("gain", 1.0))
    elif op == CurveOp.GSCALE:
        return op_gscale(step, kwargs.get("target_gain", 1.0))
    elif op == CurveOp.SHIFT:
        return op_shift(step, int(kwargs.get("shift", 0)))
    elif op == CurveOp.MULTIPLY:
        return op_multiply(step, kwargs.get("scalar", 1.0))
    elif op == CurveOp.RATE:
        return op_rate(step)
    elif op == CurveOp.RSCALE:
        return op_rscale(step, kwargs.get("factor", 1.0))
    elif op == CurveOp.FIRSTORDER:
        return op_firstorder(step, kwargs.get("tau", 1.0), kwargs.get("dt", 1.0))
    elif op == CurveOp.SECONDORDER:
        return op_secondorder(
            step, kwargs.get("tau1", 1.0), kwargs.get("tau2", 1.0),
            kwargs.get("dt", 1.0))
    elif op == CurveOp.LEADLAG:
        return op_leadlag(
            step, kwargs.get("tau_lead", 1.0), kwargs.get("tau_lag", 1.0),
            kwargs.get("dt", 1.0))
    elif op == CurveOp.ROTATE:
        return op_rotate(step, kwargs.get("angle_deg", 0.0))
    elif op == CurveOp.REPLACE:
        return other.copy() if other is not None else step.copy()
    elif op == CurveOp.ZERO:
        return create_zero(len(step))
    elif op == CurveOp.UNITY:
        return create_unity(len(step))
    elif op == CurveOp.FIRSTORDER_CREATE:
        return create_firstorder(
            len(step), kwargs.get("gain", 1.0), kwargs.get("tau", 1.0),
            kwargs.get("dt", 1.0), kwargs.get("dead_time", 0))
    elif op == CurveOp.SECONDORDER_CREATE:
        return create_secondorder(
            len(step), kwargs.get("gain", 1.0), kwargs.get("tau1", 1.0),
            kwargs.get("tau2", 1.0), kwargs.get("dt", 1.0),
            kwargs.get("dead_time", 0))
    elif op == CurveOp.CONVOLUTE:
        return convolute(step, other)
    else:
        raise ValueError(f"Unknown operation: {op}")


def apply_ops_chain(
    step: np.ndarray,
    ops: List[CurveOpRecord],
    **shared_kwargs,
) -> np.ndarray:
    """Apply a chain of operations sequentially."""
    result = step.copy()
    for record in ops:
        params = {**shared_kwargs, **record.params}
        other = params.pop("other", None)
        result = apply_op(record.op, result, other=other, **params)
    return result
