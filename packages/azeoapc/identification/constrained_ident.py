"""Constrained FIR identification -- enforce gain, dead-time, and ratio
constraints during the least-squares solve.

This is the key feature that distinguishes INCA-style identification
from traditional DMC3:

- **Gain constraints**: ``gain(CV1/MV1) > 0``, ``gain(CV2/MV1) < -0.5``
- **Dead-time constraints**: ``deadtime(CV1/MV1) >= 3``
- **Ratio constraints**: ``gain(CV1/MV1) / gain(CV1/MV2) = 2.5``
- **Bound constraints**: ``0.1 <= gain(CV1/MV1) <= 5.0``

The solver uses scipy's ``minimize`` with constraints to find FIR
coefficients that minimize prediction error while satisfying all
engineering constraints.

Usage::

    constraints = [
        GainConstraint(cv=0, mv=0, sign="positive"),
        GainConstraint(cv=0, mv=0, lower=0.5, upper=2.0),
        DeadTimeConstraint(cv=0, mv=0, min_samples=3),
        GainRatioConstraint(cv=0, mv_num=0, mv_den=1, ratio=2.5, tol=0.2),
    ]
    result = constrained_fir_identify(u, y, config, constraints)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize, LinearConstraint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constraint definitions
# ---------------------------------------------------------------------------
@dataclass
class GainConstraint:
    """Constrain the steady-state gain of a specific CV/MV pair."""
    cv: int
    mv: int
    sign: Optional[str] = None    # "positive" or "negative"
    lower: Optional[float] = None  # lower bound on gain
    upper: Optional[float] = None  # upper bound on gain


@dataclass
class DeadTimeConstraint:
    """Constrain the dead time (first non-zero FIR coefficient)."""
    cv: int
    mv: int
    min_samples: int = 0
    max_samples: Optional[int] = None


@dataclass
class GainRatioConstraint:
    """Constrain the ratio of two gains: gain(cv/mv_num) / gain(cv/mv_den) = ratio."""
    cv: int
    mv_num: int          # numerator MV
    mv_den: int          # denominator MV
    ratio: float = 1.0   # target ratio
    tol: float = 0.1     # tolerance (±)


IdentConstraint = GainConstraint | DeadTimeConstraint | GainRatioConstraint


# ---------------------------------------------------------------------------
# Constrained identification
# ---------------------------------------------------------------------------
def constrained_fir_identify(
    u: np.ndarray,
    y: np.ndarray,
    n_coeff: int = 60,
    dt: float = 1.0,
    constraints: Optional[List[IdentConstraint]] = None,
    detrend: bool = True,
    remove_mean: bool = True,
    regularization: float = 0.01,
) -> dict:
    """Identify FIR model with engineering constraints.

    Parameters
    ----------
    u : ndarray (N, nu)
        Input data.
    y : ndarray (N, ny)
        Output data.
    n_coeff : int
        Number of FIR coefficients per channel.
    dt : float
        Sample period.
    constraints : list
        Engineering constraints to enforce.
    regularization : float
        L2 regularization weight (prevents overfitting).

    Returns
    -------
    dict with keys:
        fir : list of (ny, nu) ndarray -- FIR coefficients
        step : list of (ny, nu) ndarray -- cumulative step response
        gain_matrix : (ny, nu) ndarray
        cost : float -- final objective value
        success : bool
        message : str
    """
    u = np.atleast_2d(np.asarray(u, dtype=np.float64))
    y = np.atleast_2d(np.asarray(y, dtype=np.float64))
    if u.shape[0] < u.shape[1]:
        u = u.T
    if y.shape[0] < y.shape[1]:
        y = y.T

    N, nu = u.shape
    ny = y.shape[1]
    n = n_coeff
    constraints = constraints or []

    # Preprocessing
    if detrend:
        from scipy.signal import detrend as sp_detrend
        for ch in range(nu):
            u[:, ch] = sp_detrend(u[:, ch])
        for ch in range(ny):
            y[:, ch] = sp_detrend(y[:, ch])
    if remove_mean:
        u = u - u.mean(axis=0)
        y = y - y.mean(axis=0)

    # Build Toeplitz regression matrix
    n_rows = N - n + 1
    Phi = np.zeros((n_rows, n * nu))
    for k in range(n):
        start = n - 1 - k
        Phi[:, k * nu: (k + 1) * nu] = u[start: start + n_rows, :]
    Y = y[n - 1:, :]

    # Unconstrained solution as starting point
    theta0, _, _, _ = np.linalg.lstsq(Phi, Y, rcond=None)

    # Objective: ||Y - Phi @ theta||^2 + lambda * ||theta||^2
    def objective(theta_flat):
        theta = theta_flat.reshape(n * nu, ny)
        residual = Y - Phi @ theta
        cost = np.sum(residual ** 2) + regularization * np.sum(theta_flat ** 2)
        return cost

    def gradient(theta_flat):
        theta = theta_flat.reshape(n * nu, ny)
        residual = Y - Phi @ theta
        grad = -2.0 * (Phi.T @ residual).ravel() + 2.0 * regularization * theta_flat
        return grad

    # Build scipy constraint list
    scipy_constraints = []

    for c in constraints:
        if isinstance(c, GainConstraint):
            # Gain = sum of FIR coefficients for (cv, mv) pair
            # gain = sum_{k=0}^{n-1} theta[k*nu + mv, cv]
            A_row = np.zeros(n * nu * ny)
            for k in range(n):
                # theta is stored as (n*nu, ny) flattened to (n*nu*ny,)
                # Index: row = k*nu + mv, col = cv -> flat = (k*nu + mv)*ny + cv
                A_row[(k * nu + c.mv) * ny + c.cv] = 1.0

            if c.sign == "positive":
                scipy_constraints.append({
                    "type": "ineq",
                    "fun": lambda x, A=A_row: A @ x,
                    "jac": lambda x, A=A_row: A,
                })
            elif c.sign == "negative":
                scipy_constraints.append({
                    "type": "ineq",
                    "fun": lambda x, A=A_row: -(A @ x),
                    "jac": lambda x, A=A_row: -A,
                })

            if c.lower is not None:
                scipy_constraints.append({
                    "type": "ineq",
                    "fun": lambda x, A=A_row, lb=c.lower: A @ x - lb,
                    "jac": lambda x, A=A_row: A,
                })
            if c.upper is not None:
                scipy_constraints.append({
                    "type": "ineq",
                    "fun": lambda x, A=A_row, ub=c.upper: ub - A @ x,
                    "jac": lambda x, A=A_row: -A,
                })

        elif isinstance(c, DeadTimeConstraint):
            # Force first min_samples FIR coefficients to zero for (cv, mv)
            for k in range(c.min_samples):
                eq_row = np.zeros(n * nu * ny)
                eq_row[(k * nu + c.mv) * ny + c.cv] = 1.0
                scipy_constraints.append({
                    "type": "eq",
                    "fun": lambda x, A=eq_row: A @ x,
                    "jac": lambda x, A=eq_row: A,
                })

        elif isinstance(c, GainRatioConstraint):
            # gain(cv/mv_num) / gain(cv/mv_den) = ratio
            # => gain(cv/mv_num) - ratio * gain(cv/mv_den) = 0
            A_row = np.zeros(n * nu * ny)
            for k in range(n):
                A_row[(k * nu + c.mv_num) * ny + c.cv] += 1.0
                A_row[(k * nu + c.mv_den) * ny + c.cv] -= c.ratio

            # Equality within tolerance: |constraint| <= tol
            if c.tol > 0:
                scipy_constraints.append({
                    "type": "ineq",
                    "fun": lambda x, A=A_row, t=c.tol: t - abs(A @ x),
                })
            else:
                scipy_constraints.append({
                    "type": "eq",
                    "fun": lambda x, A=A_row: A @ x,
                    "jac": lambda x, A=A_row: A,
                })

    # Solve
    x0 = theta0.ravel()
    logger.info("Constrained identification: %d variables, %d constraints",
                len(x0), len(scipy_constraints))

    result = minimize(
        objective, x0, jac=gradient,
        constraints=scipy_constraints if scipy_constraints else (),
        method="SLSQP",
        options={"maxiter": 500, "ftol": 1e-10, "disp": False},
    )

    theta_opt = result.x.reshape(n * nu, ny)

    # Unpack to FIR list
    fir_list = []
    for k in range(n):
        Gk = theta_opt[k * nu: (k + 1) * nu, :].T  # (ny, nu)
        fir_list.append(Gk.copy())

    # Step response
    step_list = []
    acc = np.zeros((ny, nu))
    for k in range(n):
        acc = acc + fir_list[k]
        step_list.append(acc.copy())

    gain_matrix = step_list[-1].copy()

    return {
        "fir": fir_list,
        "step": step_list,
        "gain_matrix": gain_matrix,
        "cost": float(result.fun),
        "success": bool(result.success),
        "message": result.message,
        "n_coeff": n,
        "dt": dt,
        "ny": ny,
        "nu": nu,
    }
