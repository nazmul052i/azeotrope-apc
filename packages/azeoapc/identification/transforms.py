"""Output transforms for process variable normalization.

Many process variables (concentrations, flow rates, pressures) have
skewed or heavy-tailed distributions that degrade linear FIR
identification.  Applying a monotonic transform can make the variable
approximately Gaussian, improving model fit and reducing bias-update
drift at runtime.

**Important**: In an APC controller the bias update (output correction)
happens in the *transform domain*.  The transform must be invertible so
predictions can be converted back to engineering units for display and
constraint checking.

Supported transforms
--------------------
=================  ====================  ========================
Method             Forward               Inverse
=================  ====================  ========================
``log``            ln(y)                 exp(z)
``log10``          log10(y)              10^z
``sqrt``           sqrt(y)               z^2
``logit``          ln(y/(1-y))           1/(1+exp(-z))
``power``          y^c                   z^(1/c)
``box_cox``        (y^lam - 1)/lam       (z*lam + 1)^(1/lam)
``shift_rate_pow`` b*(y+a)^c             (z/b)^(1/c) - a
=================  ====================  ========================

The ``auto_select_transform`` function evaluates all candidates via
Shapiro-Wilk normality testing and picks the best.

Usage::

    tf = OutputTransform(method="box_cox")
    z = tf.forward(y_raw)               # to transform domain
    y_back = tf.inverse(z)              # back to engineering units

    # Auto-select
    best = auto_select_transform(y_raw)
    z = best.forward(y_raw)
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats as sp_stats

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class TransformMethod(str, Enum):
    NONE = "none"
    LOG = "log"
    LOG10 = "log10"
    SQRT = "sqrt"
    LOGIT = "logit"
    POWER = "power"
    BOX_COX = "box_cox"
    SHIFT_RATE_POWER = "shift_rate_power"
    LINEAR_VALVE = "linear_valve"
    PARABOLIC_VALVE = "parabolic_valve"
    PWLN = "pwln"


# ---------------------------------------------------------------------------
# Transform specification
# ---------------------------------------------------------------------------
@dataclass
class OutputTransform:
    """Specification and state for one output transform.

    Parameters
    ----------
    method : TransformMethod
        Which transform to apply.
    shift : float
        Additive shift ``a`` (used by ``log``/``shift_rate_power``).
        For log: y -> ln(y + shift) to handle values near zero.
    rate : float
        Multiplicative rate ``b`` (shift_rate_power only).
    power : float
        Exponent ``c`` (power / shift_rate_power).
    box_cox_lambda : float
        Lambda for Box-Cox.  Auto-fitted if left at 0.0 and
        ``auto_fit_lambda`` is called.
    breakpoints : list of float
        X-axis breakpoints for PWLN (piece-wise linear).
    slopes : list of float
        Slopes for each PWLN segment (len = len(breakpoints) - 1).
    valve_range : tuple
        (min, max) for valve transforms (default 0-100%).
    """
    method: TransformMethod = TransformMethod.NONE
    shift: float = 0.0
    rate: float = 1.0
    power: float = 1.0
    box_cox_lambda: float = 0.0
    breakpoints: Optional[List[float]] = None
    slopes: Optional[List[float]] = None
    valve_range: Tuple[float, float] = (0.0, 100.0)

    # ---- Forward transforms ------------------------------------------------
    def forward(self, y: np.ndarray) -> np.ndarray:
        """Apply forward transform (engineering units -> transform domain)."""
        y = np.asarray(y, dtype=np.float64)

        if self.method == TransformMethod.NONE:
            return y.copy()

        if self.method == TransformMethod.LOG:
            shifted = y + self.shift
            shifted = np.clip(shifted, 1e-15, None)
            return np.log(shifted)

        if self.method == TransformMethod.LOG10:
            shifted = y + self.shift
            shifted = np.clip(shifted, 1e-15, None)
            return np.log10(shifted)

        if self.method == TransformMethod.SQRT:
            return np.sqrt(np.clip(y, 0.0, None))

        if self.method == TransformMethod.LOGIT:
            clipped = np.clip(y, 1e-10, 1.0 - 1e-10)
            return np.log(clipped / (1.0 - clipped))

        if self.method == TransformMethod.POWER:
            return np.sign(y) * np.abs(y) ** self.power

        if self.method == TransformMethod.BOX_COX:
            lam = self.box_cox_lambda
            yp = np.clip(y, 1e-15, None)
            if abs(lam) < 1e-10:
                return np.log(yp)
            return (yp ** lam - 1.0) / lam

        if self.method == TransformMethod.SHIFT_RATE_POWER:
            shifted = y + self.shift
            return self.rate * np.sign(shifted) * np.abs(shifted) ** self.power

        if self.method == TransformMethod.LINEAR_VALVE:
            # Linear valve: linearize equal-percentage valve characteristic
            # y is valve position (0-100%), output is linearized flow
            lo, hi = self.valve_range
            rng = hi - lo
            if rng <= 0:
                return y.copy()
            normalized = np.clip((y - lo) / rng, 0.001, 0.999)
            return np.log(normalized)

        if self.method == TransformMethod.PARABOLIC_VALVE:
            # Parabolic valve: y² relationship
            lo, hi = self.valve_range
            rng = hi - lo
            if rng <= 0:
                return y.copy()
            normalized = np.clip((y - lo) / rng, 0.0, 1.0)
            return np.sqrt(normalized) * rng + lo

        if self.method == TransformMethod.PWLN:
            # Piece-wise linear transform
            if self.breakpoints is None or self.slopes is None:
                return y.copy()
            return self._pwln_forward(y)

        return y.copy()

    # ---- Inverse transforms ------------------------------------------------
    def inverse(self, z: np.ndarray) -> np.ndarray:
        """Apply inverse transform (transform domain -> engineering units)."""
        z = np.asarray(z, dtype=np.float64)

        if self.method == TransformMethod.NONE:
            return z.copy()

        if self.method == TransformMethod.LOG:
            return np.exp(z) - self.shift

        if self.method == TransformMethod.LOG10:
            return 10.0 ** z - self.shift

        if self.method == TransformMethod.SQRT:
            return z ** 2

        if self.method == TransformMethod.LOGIT:
            return 1.0 / (1.0 + np.exp(-z))

        if self.method == TransformMethod.POWER:
            if abs(self.power) < 1e-15:
                return z.copy()
            inv_p = 1.0 / self.power
            return np.sign(z) * np.abs(z) ** inv_p

        if self.method == TransformMethod.BOX_COX:
            lam = self.box_cox_lambda
            if abs(lam) < 1e-10:
                return np.exp(z)
            inner = z * lam + 1.0
            inner = np.clip(inner, 1e-15, None)
            return inner ** (1.0 / lam)

        if self.method == TransformMethod.SHIFT_RATE_POWER:
            if abs(self.rate) < 1e-15 or abs(self.power) < 1e-15:
                return z.copy()
            inv_p = 1.0 / self.power
            scaled = z / self.rate
            return np.sign(scaled) * np.abs(scaled) ** inv_p - self.shift

        if self.method == TransformMethod.LINEAR_VALVE:
            lo, hi = self.valve_range
            rng = hi - lo
            if rng <= 0:
                return z.copy()
            return np.exp(z) * rng + lo

        if self.method == TransformMethod.PARABOLIC_VALVE:
            lo, hi = self.valve_range
            rng = hi - lo
            if rng <= 0:
                return z.copy()
            normalized = np.clip((z - lo) / rng, 0.0, 1.0)
            return normalized ** 2 * rng + lo

        if self.method == TransformMethod.PWLN:
            if self.breakpoints is None or self.slopes is None:
                return z.copy()
            return self._pwln_inverse(z)

        return z.copy()

    def _pwln_forward(self, y: np.ndarray) -> np.ndarray:
        """Piece-wise linear forward transform."""
        bp = np.array(self.breakpoints)
        sl = np.array(self.slopes)
        out = np.zeros_like(y)
        for i in range(len(y)):
            val = float(y[i])
            z = 0.0
            for seg in range(len(sl)):
                if val <= bp[seg + 1]:
                    z += sl[seg] * (val - bp[seg])
                    break
                else:
                    z += sl[seg] * (bp[seg + 1] - bp[seg])
            else:
                # Beyond last breakpoint: extrapolate with last slope
                z += sl[-1] * (val - bp[-1])
            out[i] = z
        return out

    def _pwln_inverse(self, z: np.ndarray) -> np.ndarray:
        """Piece-wise linear inverse transform."""
        bp = np.array(self.breakpoints)
        sl = np.array(self.slopes)
        # Build cumulative z breakpoints
        z_bp = [0.0]
        for seg in range(len(sl)):
            z_bp.append(z_bp[-1] + sl[seg] * (bp[seg + 1] - bp[seg]))
        z_bp = np.array(z_bp)

        out = np.zeros_like(z)
        for i in range(len(z)):
            val = float(z[i])
            y_val = bp[0]
            for seg in range(len(sl)):
                if val <= z_bp[seg + 1]:
                    if abs(sl[seg]) > 1e-15:
                        y_val = bp[seg] + (val - z_bp[seg]) / sl[seg]
                    break
                y_val = bp[seg + 1]
            else:
                if abs(sl[-1]) > 1e-15:
                    y_val = bp[-1] + (val - z_bp[-1]) / sl[-1]
            out[i] = y_val
        return out

    def auto_fit_lambda(self, y: np.ndarray) -> float:
        """Fit the Box-Cox lambda from data and store it.

        Uses scipy.stats.boxcox to find the optimal lambda.
        """
        y = np.asarray(y, dtype=np.float64)
        y_pos = y[y > 0]
        if len(y_pos) < 10:
            self.box_cox_lambda = 0.0
            return 0.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _, lam = sp_stats.boxcox(y_pos)
        self.box_cox_lambda = float(lam)
        return self.box_cox_lambda


# ---------------------------------------------------------------------------
# Transform evaluation result
# ---------------------------------------------------------------------------
@dataclass
class TransformCandidate:
    """Result of evaluating one transform candidate."""
    transform: OutputTransform
    shapiro_w: float       # Shapiro-Wilk W statistic (closer to 1 = more normal)
    shapiro_p: float       # Shapiro-Wilk p-value
    skewness: float
    kurtosis: float


# ---------------------------------------------------------------------------
# Auto-select
# ---------------------------------------------------------------------------
def auto_select_transform(
    y: np.ndarray,
    candidates: Optional[List[TransformMethod]] = None,
    max_samples: int = 5000,
) -> OutputTransform:
    """Evaluate candidate transforms via Shapiro-Wilk and pick the best.

    Parameters
    ----------
    y : ndarray
        Raw output variable.
    candidates : list[TransformMethod], optional
        Transforms to evaluate.  Default: NONE, LOG, LOG10, SQRT, BOX_COX.
    max_samples : int
        Shapiro-Wilk is O(n^2); subsample if the array is larger.

    Returns
    -------
    OutputTransform
        The transform whose forward output is closest to Gaussian.
    """
    y = np.asarray(y, dtype=np.float64)
    y = y[np.isfinite(y)]

    if len(y) < 10:
        return OutputTransform(method=TransformMethod.NONE)

    if candidates is None:
        candidates = [
            TransformMethod.NONE,
            TransformMethod.LOG,
            TransformMethod.LOG10,
            TransformMethod.SQRT,
            TransformMethod.BOX_COX,
        ]

    # Subsample for Shapiro-Wilk performance
    if len(y) > max_samples:
        rng = np.random.default_rng(42)
        y_test = rng.choice(y, max_samples, replace=False)
    else:
        y_test = y

    best_w = -1.0
    best_tf = OutputTransform(method=TransformMethod.NONE)

    for method in candidates:
        tf = OutputTransform(method=method)

        # Prepare the transform
        if method == TransformMethod.LOG or method == TransformMethod.LOG10:
            # Shift so all values are positive
            min_val = float(np.min(y_test))
            if min_val <= 0:
                tf.shift = abs(min_val) + 1.0

        if method == TransformMethod.BOX_COX:
            # Ensure positive data
            min_val = float(np.min(y_test))
            if min_val <= 0:
                tf.shift = abs(min_val) + 1.0
            y_shifted = y_test + tf.shift
            y_pos = y_shifted[y_shifted > 0]
            if len(y_pos) < 10:
                continue
            tf.auto_fit_lambda(y_pos)

        try:
            z = tf.forward(y_test)
        except Exception:
            continue

        z = z[np.isfinite(z)]
        if len(z) < 10:
            continue

        # Shapiro-Wilk normality test
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                w, p = sp_stats.shapiro(z[:5000])
            except Exception:
                continue

        if w > best_w:
            best_w = w
            best_tf = tf

    return best_tf


def evaluate_transforms(
    y: np.ndarray,
    candidates: Optional[List[TransformMethod]] = None,
    max_samples: int = 5000,
) -> List[TransformCandidate]:
    """Evaluate all candidates and return ranked results.

    Unlike ``auto_select_transform`` this returns the full scorecard
    so the engineer can review the trade-offs.
    """
    y = np.asarray(y, dtype=np.float64)
    y = y[np.isfinite(y)]

    if len(y) < 10:
        return []

    if candidates is None:
        candidates = [
            TransformMethod.NONE,
            TransformMethod.LOG,
            TransformMethod.LOG10,
            TransformMethod.SQRT,
            TransformMethod.BOX_COX,
            TransformMethod.POWER,
            TransformMethod.SHIFT_RATE_POWER,
        ]

    if len(y) > max_samples:
        rng = np.random.default_rng(42)
        y_test = rng.choice(y, max_samples, replace=False)
    else:
        y_test = y

    results: List[TransformCandidate] = []

    for method in candidates:
        tf = OutputTransform(method=method)

        if method in (TransformMethod.LOG, TransformMethod.LOG10):
            min_val = float(np.min(y_test))
            if min_val <= 0:
                tf.shift = abs(min_val) + 1.0

        if method == TransformMethod.BOX_COX:
            min_val = float(np.min(y_test))
            if min_val <= 0:
                tf.shift = abs(min_val) + 1.0
            y_pos = (y_test + tf.shift)
            y_pos = y_pos[y_pos > 0]
            if len(y_pos) < 10:
                continue
            tf.auto_fit_lambda(y_pos)

        if method == TransformMethod.POWER:
            tf.power = 0.5   # default to square root for power

        if method == TransformMethod.SHIFT_RATE_POWER:
            min_val = float(np.min(y_test))
            if min_val <= 0:
                tf.shift = abs(min_val) + 1.0
            tf.power = 0.5
            tf.rate = 1.0

        try:
            z = tf.forward(y_test)
        except Exception:
            continue

        z = z[np.isfinite(z)]
        if len(z) < 10:
            continue

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                w, p = sp_stats.shapiro(z[:5000])
            except Exception:
                continue

        results.append(TransformCandidate(
            transform=tf,
            shapiro_w=float(w),
            shapiro_p=float(p),
            skewness=float(sp_stats.skew(z)),
            kurtosis=float(sp_stats.kurtosis(z)),
        ))

    results.sort(key=lambda c: c.shapiro_w, reverse=True)
    return results
