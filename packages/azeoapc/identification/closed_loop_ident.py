"""Closed-loop subspace identification.

When data is collected while a controller is running, the standard
open-loop subspace methods (N4SID, MOESP, CVA) produce biased models
because the input u is correlated with the output noise through the
feedback loop:

    y -> controller -> u -> plant -> y  (feedback loop)

Three methods are implemented:

1. **Instrumental Variable (IV)** -- uses the setpoint/reference signal
   r as an instrument to break the u-noise correlation.  Requires that
   the setpoints were varied during the test (step-test on setpoints).

2. **Two-Stage** -- first identifies the controller K from (y, u), then
   reconstructs the open-loop input and identifies the plant.

3. **Regularized Direct** -- applies L2 regularization to the Hankel
   matrices to suppress the feedback bias.  Simpler, doesn't require
   setpoint data.

References
----------
- Kuntz & Rawlings (2024), Ch. 4: "Closed-loop subspace identification"
- Van den Hof & Schrama (1995), "Instrumental variable methods"
- Ljung & McKelvey (1996), "Subspace identification from closed-loop data"

Usage::

    # With setpoint data (best results)
    result = closed_loop_identify(u, y, r=setpoints, method="iv", dt=60.0)

    # Without setpoints (regularized direct)
    result = closed_loop_identify(u, y, method="regularized", dt=60.0)

    # Two-stage
    result = closed_loop_identify(u, y, method="two_stage", dt=60.0)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
from scipy import linalg, signal

logger = logging.getLogger(__name__)

Mat = np.ndarray
Vec = np.ndarray


class ClosedLoopMethod(str, Enum):
    IV = "iv"                     # instrumental variable (needs setpoints)
    TWO_STAGE = "two_stage"       # two-stage (controller + plant)
    REGULARIZED = "regularized"   # regularized direct


@dataclass
class ClosedLoopConfig:
    """Configuration for closed-loop identification."""
    method: ClosedLoopMethod = ClosedLoopMethod.REGULARIZED
    f: int = 20                   # future horizon
    p: Optional[int] = None       # past horizon (default = f)
    nx: Optional[int] = None      # model order (None = auto)
    nx_max: int = 20
    dt: float = 1.0
    regularization: float = 0.1   # L2 regularization strength
    detrend: bool = True
    remove_mean: bool = True
    force_stability: bool = True
    sv_threshold: float = 0.05

    def __post_init__(self):
        if self.p is None:
            self.p = self.f


# ---------------------------------------------------------------------------
# Block-Hankel builder (reused from subspace_ident)
# ---------------------------------------------------------------------------
def _block_hankel(data: Mat, block_rows: int) -> Mat:
    n_ch, N = data.shape
    N_cols = N - block_rows + 1
    H = np.zeros((block_rows * n_ch, N_cols))
    for i in range(block_rows):
        H[i * n_ch: (i + 1) * n_ch, :] = data[:, i: i + N_cols]
    return H


def _partition(u, y, f, p):
    nu, N = u.shape
    ny = y.shape[0]
    total = f + p
    U_full = _block_hankel(u, total)
    Y_full = _block_hankel(y, total)
    N_cols = U_full.shape[1]
    return (U_full[:p*nu, :], U_full[p*nu:, :],
            Y_full[:p*ny, :], Y_full[p*ny:, :], N_cols)


# ---------------------------------------------------------------------------
# Method 1: Instrumental Variable
# ---------------------------------------------------------------------------
def _identify_iv(u, y, r, config: ClosedLoopConfig):
    """Closed-loop identification using setpoints as instrumental variables.

    The key idea: the setpoint r is correlated with u (through the
    controller) but uncorrelated with the output noise e.  Using r
    as an instrument removes the feedback bias.

    Projection: instead of projecting Y_f onto [U_p; Y_p; U_f],
    we project onto [R_p; R_f; U_f] where R is the setpoint.
    """
    nu, N = u.shape
    ny = y.shape[0]
    nr = r.shape[0]
    f, p = config.f, config.p

    # Build Hankel matrices
    U_p, U_f, Y_p, Y_f, N_cols = _partition(u, y, f, p)

    # Build setpoint Hankel matrices
    R_full = _block_hankel(r, f + p)
    R_p = R_full[:p * nr, :]
    R_f = R_full[p * nr:, :]

    # Instrument matrix: past setpoints + past outputs
    Z = np.vstack([R_p, Y_p])  # instrumental variables

    # IV projection: Y_f * Z' * (Z * Z')^{-1} * Z
    ZZt = Z @ Z.T / N_cols
    # Regularize
    ZZt += config.regularization * np.eye(ZZt.shape[0]) * np.trace(ZZt) / ZZt.shape[0]

    ZZt_inv = np.linalg.inv(ZZt)
    O_iv = (Y_f @ Z.T / N_cols) @ ZZt_inv @ Z

    # SVD for observability matrix
    U_svd, S, Vt = np.linalg.svd(O_iv, full_matrices=False)

    # Order selection
    nx = _select_order(S, config)
    Gamma = U_svd[:, :nx] @ np.diag(np.sqrt(S[:nx]))

    return Gamma, S, nx, U_p, U_f, Y_p, Y_f, N_cols


# ---------------------------------------------------------------------------
# Method 2: Two-Stage
# ---------------------------------------------------------------------------
def _identify_two_stage(u, y, config: ClosedLoopConfig):
    """Two-stage closed-loop identification.

    Stage 1: Identify the controller y -> u using an ARX model.
    Stage 2: Reconstruct the 'innovation' input and identify the plant.

    The innovation input v = u - K*y is uncorrelated with the noise,
    so standard open-loop subspace ID can be applied to (v, y).
    """
    nu, N = u.shape
    ny = y.shape[0]
    f, p = config.f, config.p

    # Stage 1: Estimate controller transfer function K
    # Simple ARX with regularization: u[k] = sum_{i=1}^{p} K_i * y[k-i] + v[k]
    n_arx = min(p, 10)
    Phi_ctrl = np.zeros((N - n_arx, n_arx * ny))
    for lag in range(n_arx):
        start = n_arx - 1 - lag
        Phi_ctrl[:, lag * ny:(lag + 1) * ny] = y[:, start:start + N - n_arx].T

    U_target = u[:, n_arx:].T  # (N-n_arx, nu)

    # Ridge regression for controller (regularized to prevent blowup)
    PhiTPhi = Phi_ctrl.T @ Phi_ctrl
    alpha = config.regularization * np.trace(PhiTPhi) / max(PhiTPhi.shape[0], 1)
    K_arx = np.linalg.solve(
        PhiTPhi + alpha * np.eye(PhiTPhi.shape[0]),
        Phi_ctrl.T @ U_target)

    # Reconstruct innovation: v = u - Phi * K_arx
    u_predicted = (Phi_ctrl @ K_arx).T  # (nu, N-n_arx)
    v = u[:, n_arx:] - u_predicted  # innovation input

    # Stage 2: Open-loop subspace ID on (v, y)
    y_trimmed = y[:, n_arx:]

    # Ensure enough data
    min_needed = 2 * (f + config.p) + 10
    if v.shape[1] < min_needed:
        raise ValueError(
            f"Insufficient data after ARX stage: {v.shape[1]} < {min_needed}")

    V_p, V_f, Y_p, Y_f, N_cols = _partition(v, y_trimmed, f, config.p)

    # Standard N4SID on innovation inputs
    W_p = np.vstack([V_p, Y_p])
    # Oblique projection
    BC = np.vstack([V_f, W_p])
    BC_pinv = np.linalg.pinv(BC)
    n_B = V_f.shape[0]
    proj_C = np.zeros_like(BC)
    proj_C[n_B:, :] = W_p
    O_i = Y_f @ BC_pinv @ proj_C

    U_svd, S, Vt = np.linalg.svd(O_i, full_matrices=False)
    nx = _select_order(S, config)
    Gamma = U_svd[:, :nx] @ np.diag(np.sqrt(S[:nx]))

    return Gamma, S, nx, V_p, V_f, Y_p, Y_f, N_cols


# ---------------------------------------------------------------------------
# Method 3: Regularized Direct
# ---------------------------------------------------------------------------
def _identify_regularized(u, y, config: ClosedLoopConfig):
    """Regularized direct closed-loop identification.

    Applies Tikhonov regularization to the Hankel matrices to suppress
    feedback bias.  The regularization shrinks the estimated parameters
    toward zero, which reduces the bias from feedback correlation at
    the cost of some variance increase.

    This is the simplest method and doesn't require setpoint data.
    """
    nu, N = u.shape
    ny = y.shape[0]
    f, p = config.f, config.p

    U_p, U_f, Y_p, Y_f, N_cols = _partition(u, y, f, p)
    W_p = np.vstack([U_p, Y_p])

    # Regularized oblique projection
    # O_i = Y_f * [U_f; W_p]' * ([U_f; W_p] * [U_f; W_p]' + lambda*I)^{-1} * [0; W_p]
    BC = np.vstack([U_f, W_p])
    BCBCt = BC @ BC.T / N_cols

    # Regularization
    lam = config.regularization
    reg = lam * np.eye(BCBCt.shape[0]) * np.trace(BCBCt) / BCBCt.shape[0]
    BCBCt_reg = BCBCt + reg

    BCBCt_inv = np.linalg.inv(BCBCt_reg)

    n_U = U_f.shape[0]
    # Select W_p columns only
    selector = np.zeros((BC.shape[0], W_p.shape[0]))
    selector[n_U:, :] = np.eye(W_p.shape[0])

    O_i = (Y_f @ BC.T / N_cols) @ BCBCt_inv @ selector @ W_p

    U_svd, S, Vt = np.linalg.svd(O_i, full_matrices=False)
    nx = _select_order(S, config)
    Gamma = U_svd[:, :nx] @ np.diag(np.sqrt(S[:nx]))

    return Gamma, S, nx, U_p, U_f, Y_p, Y_f, N_cols


# ---------------------------------------------------------------------------
# Order selection (shared)
# ---------------------------------------------------------------------------
def _select_order(S, config):
    if config.nx is not None:
        return min(config.nx, len(S))
    S_pos = np.maximum(S, 1e-30)
    nx_max = min(config.nx_max, len(S_pos) - 1)
    if nx_max < 2:
        return 1
    # Gap criterion
    ratios = S_pos[:nx_max] / S_pos[1:nx_max + 1]
    best_gap = 0.0
    nx_gap = 1
    for n in range(1, min(nx_max, len(ratios))):
        if ratios[n] > best_gap:
            best_gap = ratios[n]
            nx_gap = n + 1
    return max(1, min(nx_gap, nx_max))


# ---------------------------------------------------------------------------
# System matrix extraction (shared)
# ---------------------------------------------------------------------------
def _extract_ss(Gamma, U_p, U_f, Y_p, Y_f, ny, nu, f, p, N_cols, nx, config):
    """Extract A, B, C, D from observability matrix."""
    C = Gamma[:ny, :]
    Gamma_up = Gamma[:-ny, :]
    Gamma_down = Gamma[ny:, :]
    A = np.linalg.pinv(Gamma_up) @ Gamma_down

    # State sequence
    Gamma_pinv = np.linalg.pinv(Gamma)
    W_p = np.vstack([U_p, Y_p])
    BC = np.vstack([U_f, W_p])
    n_B = U_f.shape[0]
    proj_C = np.zeros_like(BC)
    proj_C[n_B:, :] = W_p
    O_i = Y_f @ np.linalg.pinv(BC) @ proj_C
    X = Gamma_pinv @ O_i

    X_k = X[:, :-1]
    X_k1 = X[:, 1:]
    U_k = U_f[:nu, :-1]
    Y_k = Y_f[:ny, :-1]

    LHS = np.vstack([X_k1, Y_k])
    RHS = np.vstack([X_k, U_k])
    Theta = LHS @ np.linalg.pinv(RHS)

    A = Theta[:nx, :nx]
    B = Theta[:nx, nx:]
    C = Theta[nx:, :nx]
    D = Theta[nx:, nx:]

    if config.force_stability:
        eigvals, eigvecs = np.linalg.eig(A)
        modified = False
        for i in range(len(eigvals)):
            if np.abs(eigvals[i]) >= 1.0:
                eigvals[i] = eigvals[i] / np.abs(eigvals[i]) * 0.99
                modified = True
        if modified:
            A = np.real(eigvecs @ np.diag(eigvals) @ np.linalg.inv(eigvecs))

    return A, B, C, D


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def closed_loop_identify(
    u: np.ndarray,
    y: np.ndarray,
    r: Optional[np.ndarray] = None,
    method: str = "regularized",
    f: int = 20,
    dt: float = 1.0,
    nx: Optional[int] = None,
    regularization: float = 0.1,
    force_stability: bool = True,
    **kwargs,
) -> dict:
    """Closed-loop MIMO identification.

    Parameters
    ----------
    u : ndarray (N, nu) -- controller outputs (MV values)
    y : ndarray (N, ny) -- process outputs (CV measurements)
    r : ndarray (N, nr), optional -- setpoints/references (needed for IV method)
    method : str -- "iv", "two_stage", or "regularized"
    f : int -- future/past horizon
    dt : float -- sample period
    nx : int, optional -- model order (None = auto)
    regularization : float -- L2 regularization strength

    Returns
    -------
    dict with A, B, C, D, singular_values, nx, gain_matrix, fit metrics
    """
    u = np.atleast_2d(np.asarray(u, dtype=np.float64))
    y = np.atleast_2d(np.asarray(y, dtype=np.float64))
    if u.shape[0] > u.shape[1]:
        u = u.T
    if y.shape[0] > y.shape[1]:
        y = y.T
    if r is not None:
        r = np.atleast_2d(np.asarray(r, dtype=np.float64))
        if r.shape[0] > r.shape[1]:
            r = r.T

    nu, N = u.shape
    ny = y.shape[0]

    config = ClosedLoopConfig(
        method=ClosedLoopMethod(method),
        f=f, dt=dt, nx=nx,
        regularization=regularization,
        force_stability=force_stability,
    )

    # Preprocessing
    if config.detrend:
        for ch in range(nu):
            u[ch, :] = signal.detrend(u[ch, :])
        for ch in range(ny):
            y[ch, :] = signal.detrend(y[ch, :])
        if r is not None:
            for ch in range(r.shape[0]):
                r[ch, :] = signal.detrend(r[ch, :])

    if config.remove_mean:
        u = u - u.mean(axis=1, keepdims=True)
        y = y - y.mean(axis=1, keepdims=True)
        if r is not None:
            r = r - r.mean(axis=1, keepdims=True)

    logger.info("Closed-loop identification: method=%s, ny=%d, nu=%d, N=%d",
                method, ny, nu, N)

    # Run selected method
    if config.method == ClosedLoopMethod.IV:
        if r is None:
            raise ValueError("IV method requires setpoint data r")
        Gamma, sv, nx_sel, U_p, U_f, Y_p, Y_f, N_cols = _identify_iv(
            u, y, r, config)
    elif config.method == ClosedLoopMethod.TWO_STAGE:
        try:
            Gamma, sv, nx_sel, U_p, U_f, Y_p, Y_f, N_cols = _identify_two_stage(
                u, y, config)
        except Exception as e:
            logger.warning("Two-stage failed (%s), falling back to regularized", e)
            Gamma, sv, nx_sel, U_p, U_f, Y_p, Y_f, N_cols = _identify_regularized(
                u, y, config)
    else:
        Gamma, sv, nx_sel, U_p, U_f, Y_p, Y_f, N_cols = _identify_regularized(
            u, y, config)

    # Extract system matrices
    A, B, C, D = _extract_ss(
        Gamma, U_p, U_f, Y_p, Y_f,
        ny, nu, config.f, config.p, N_cols, nx_sel, config)

    # Fit metrics
    x = np.zeros(nx_sel)
    y_pred = np.zeros((ny, N))
    for k in range(N):
        y_pred[:, k] = C @ x + D @ u[:, k]
        x = A @ x + B @ u[:, k]

    residuals = y - y_pred
    fit_r2 = np.zeros(ny)
    fit_rmse = np.zeros(ny)
    for j in range(ny):
        ss_res = np.sum(residuals[j, :] ** 2)
        ss_tot = np.sum((y[j, :] - y[j, :].mean()) ** 2)
        fit_r2[j] = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0
        fit_rmse[j] = np.sqrt(np.mean(residuals[j, :] ** 2))

    eigenvalues = np.linalg.eigvals(A)
    is_stable = bool(np.all(np.abs(eigenvalues) < 1.0))

    # Gain matrix
    try:
        gain = C @ np.linalg.solve(np.eye(nx_sel) - A, B) + D
    except np.linalg.LinAlgError:
        gain = np.full((ny, nu), np.nan)

    # Step response
    n_step = 120
    step_list = []
    Ak = np.eye(nx_sel)
    acc = D.copy()
    step_list.append(acc.copy())
    for k in range(1, n_step):
        acc = acc + C @ Ak @ B
        step_list.append(acc.copy())
        Ak = Ak @ A

    logger.info("Closed-loop ID done: nx=%d, stable=%s, R2=%s",
                nx_sel, is_stable, fit_r2.round(3))

    return {
        "A": A, "B": B, "C": C, "D": D,
        "nx": nx_sel, "ny": ny, "nu": nu,
        "singular_values": sv,
        "eigenvalues": eigenvalues,
        "is_stable": is_stable,
        "gain_matrix": gain,
        "step": step_list,
        "fit_r2": fit_r2,
        "fit_rmse": fit_rmse,
        "y_pred": y_pred.T,
        "residuals": residuals.T,
        "method": method,
        "dt": dt,
        "config": config,
    }
