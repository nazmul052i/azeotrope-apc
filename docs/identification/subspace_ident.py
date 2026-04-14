"""
subspace_ident.py — Commercial-grade MIMO Subspace State-Space Identification.

Implements three classical subspace identification algorithms:
    • N4SID  — Numerical Algorithms for Subspace State Space System ID
               (Van Overschee & De Moor, 1994)
    • MOESP  — Multivariable Output-Error State Space
               (Verhaegen & Dewilde, 1992)
    • CVA    — Canonical Variate Analysis
               (Larimore, 1990)

All methods share the same block-Hankel / projection infrastructure
and return a unified SubspaceResult containing the identified
(A, B, C, D, K) matrices, singular values for order selection,
fit diagnostics, and a ControlModel instance for downstream use.

Integration:
    Works with control_model.py (TF/SS/FIR conversions) and
    fir_ident.py (FIR identification).  Identified models can be
    converted to DMC-style step-response coefficients via
    ControlModel.to_fir_from_ss().

Author : Azeotrope Process Control
License: Proprietary
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from numpy.typing import NDArray
from scipy import linalg, signal, stats

logger = logging.getLogger(__name__)

Mat = NDArray[np.float64]
Vec = NDArray[np.float64]


# =====================================================================
#  Configuration
# =====================================================================
class SubspaceMethod(str, Enum):
    N4SID = "n4sid"
    MOESP = "moesp"
    CVA = "cva"


@dataclass
class SubspaceConfig:
    """
    Configuration for subspace identification.

    Parameters
    ----------
    method : SubspaceMethod
        Algorithm to use.
    nx : int or None
        Fixed model order.  If None, order is selected automatically
        from the singular value gap.
    nx_max : int
        Maximum model order to consider during auto-selection.
    f : int
        Future horizon (block rows in the future Hankel matrices).
        Must be > nx + max dead time.  Rule of thumb: 1.5–2× expected nx.
    p : int or None
        Past horizon.  If None, defaults to f.
    dt : float
        Sample period in seconds.
    estimate_K : bool
        Whether to estimate the Kalman gain K from residuals.
    force_stability : bool
        If True, reflect unstable eigenvalues inside the unit circle.
    force_zero_D : bool
        If True, constrain D = 0 (strictly proper model).
    sv_threshold : float
        Relative threshold for singular-value gap detection.
        Order is selected where σ_{n+1}/σ_1 < sv_threshold.
    detrend : bool
        Remove linear trend from signals before identification.
    remove_mean : bool
        Subtract signal means before identification.
    """
    method: SubspaceMethod = SubspaceMethod.N4SID
    nx: Optional[int] = None
    nx_max: int = 20
    f: int = 20
    p: Optional[int] = None
    dt: float = 1.0
    estimate_K: bool = True
    force_stability: bool = False
    force_zero_D: bool = False
    sv_threshold: float = 0.05
    detrend: bool = True
    remove_mean: bool = True

    def __post_init__(self):
        if self.f < 2:
            raise ValueError(f"Future horizon f must be ≥ 2, got {self.f}")
        if self.p is None:
            self.p = self.f
        if self.p < 2:
            raise ValueError(f"Past horizon p must be ≥ 2, got {self.p}")
        if self.dt <= 0:
            raise ValueError(f"dt must be > 0, got {self.dt}")
        if self.nx is not None and self.nx < 1:
            raise ValueError(f"nx must be ≥ 1, got {self.nx}")


# =====================================================================
#  Result
# =====================================================================
@dataclass
class SubspaceResult:
    """
    Complete result from subspace identification.

    Attributes
    ----------
    A, B, C, D : ndarray
        Identified discrete-time state-space matrices.
    K : ndarray or None
        Kalman gain (innovation form).
    nx : int
        Selected model order.
    ny, nu : int
        Number of outputs and inputs.
    singular_values : ndarray
        All singular values from the projection SVD (for order selection).
    config : SubspaceConfig
        Configuration used.
    eigenvalues : ndarray
        Eigenvalues of A (complex).
    y_pred : ndarray
        Model-predicted output on identification data.
    residuals : ndarray
        y_actual - y_pred.
    fit_r2 : ndarray
        Per-output R² on identification data.
    fit_rmse : ndarray
        Per-output RMSE.
    fit_nrmse : ndarray
        Per-output NRMSE (RMSE / range).
    is_stable : bool
        Whether all eigenvalues are inside the unit circle.
    condition_number : float
        Condition number of the primary data matrix.
    """
    A: Mat
    B: Mat
    C: Mat
    D: Mat
    K: Optional[Mat]
    nx: int
    ny: int
    nu: int
    singular_values: Vec
    config: SubspaceConfig
    eigenvalues: Vec
    y_pred: Mat
    residuals: Mat
    fit_r2: Vec
    fit_rmse: Vec
    fit_nrmse: Vec
    is_stable: bool
    condition_number: float

    def gain_matrix(self) -> Mat:
        """Steady-state gain: C (I - A)^{-1} B + D."""
        nx = self.A.shape[0]
        try:
            return self.C @ np.linalg.solve(np.eye(nx) - self.A, self.B) + self.D
        except np.linalg.LinAlgError:
            logger.warning("Cannot compute gain: (I-A) singular")
            return np.full((self.ny, self.nu), np.nan)

    def to_fir(self, N: int = 120) -> List[Mat]:
        """Convert to FIR (Markov parameter) sequence."""
        A, B, C, D = self.A, self.B, self.C, self.D
        nx = A.shape[0]
        G = [D.copy()]
        Ak = np.eye(nx)
        for k in range(1, N):
            G.append(C @ Ak @ B)
            Ak = Ak @ A
        return G

    def to_step(self, N: int = 120) -> List[Mat]:
        """Convert to cumulative step-response sequence."""
        fir = self.to_fir(N)
        step = []
        acc = np.zeros_like(fir[0])
        for g in fir:
            acc = acc + g
            step.append(acc.copy())
        return step

    def dead_times(self, tol: float = 0.01, N: int = 120) -> Mat:
        """
        Estimate dead time per channel from the FIR sequence.
        Returns (ny, nu) integer array of dead-time steps.
        """
        fir = self.to_fir(N)
        result = np.zeros((self.ny, self.nu), dtype=int)
        for i in range(self.ny):
            for j in range(self.nu):
                for k, Gk in enumerate(fir):
                    if abs(Gk[i, j]) > tol * abs(self.gain_matrix()[i, j]):
                        result[i, j] = k
                        break
                else:
                    result[i, j] = N
        return result

    def summary(self) -> str:
        lines = [
            "Subspace Identification Result",
            f"  Method       : {self.config.method.value.upper()}",
            f"  Order (nx)   : {self.nx}",
            f"  Dimensions   : ny={self.ny}, nu={self.nu}",
            f"  dt           : {self.config.dt}s",
            f"  Stable       : {self.is_stable}",
            f"  Cond. number : {self.condition_number:.1f}",
            f"  Eigenvalues  : {np.array2string(self.eigenvalues, precision=4, separator=', ')}",
            f"  |λ|_max      : {np.max(np.abs(self.eigenvalues)):.6f}",
            f"",
            f"  Gain matrix (C(I-A)⁻¹B + D):",
        ]
        gain = self.gain_matrix()
        for i in range(self.ny):
            row = "    " + "  ".join(f"{gain[i, j]:+10.4f}" for j in range(self.nu))
            lines.append(row)

        lines.append(f"")
        lines.append(f"  Fit metrics:")
        for j in range(self.ny):
            lines.append(
                f"    CV{j}: R²={self.fit_r2[j]:.4f}  "
                f"RMSE={self.fit_rmse[j]:.4f}  "
                f"NRMSE={self.fit_nrmse[j]:.4f}"
            )

        dt_mat = self.dead_times()
        lines.append(f"")
        lines.append(f"  Estimated dead times (samples):")
        for i in range(self.ny):
            row = "    " + "  ".join(f"{dt_mat[i, j]:4d}" for j in range(self.nu))
            lines.append(row)

        lines.append(f"")
        lines.append(f"  Singular values (top 15):")
        sv_show = self.singular_values[:min(15, len(self.singular_values))]
        lines.append(f"    {np.array2string(sv_show, precision=3, separator=', ')}")

        return "\n".join(lines)


# =====================================================================
#  Block-Hankel and projection infrastructure
# =====================================================================
def _block_hankel(data: Mat, block_rows: int) -> Mat:
    """
    Build a block-Hankel matrix from data.

    Parameters
    ----------
    data : (n_channels, N_samples)
    block_rows : int
        Number of block rows (horizon).

    Returns
    -------
    H : (block_rows * n_channels, N_cols)
    """
    n_ch, N = data.shape
    N_cols = N - block_rows + 1
    if N_cols < 1:
        raise ValueError(
            f"Not enough data: {N} samples for {block_rows} block rows"
        )
    H = np.zeros((block_rows * n_ch, N_cols))
    for i in range(block_rows):
        H[i * n_ch: (i + 1) * n_ch, :] = data[:, i: i + N_cols]
    return H


def _partition_data(
    u: Mat, y: Mat, f: int, p: int
) -> Tuple[Mat, Mat, Mat, Mat, int]:
    """
    Build past/future block-Hankel partitions.

    Returns (U_p, U_f, Y_p, Y_f, N_cols).
    """
    nu, N = u.shape
    ny = y.shape[0]
    total_rows = f + p

    if N < total_rows + 1:
        raise ValueError(
            f"Need at least {total_rows + 1} samples, got {N}"
        )

    # Build full Hankel matrices and split
    U_full = _block_hankel(u, total_rows)
    Y_full = _block_hankel(y, total_rows)

    N_cols = U_full.shape[1]

    U_p = U_full[: p * nu, :]
    U_f = U_full[p * nu:, :]
    Y_p = Y_full[: p * ny, :]
    Y_f = Y_full[p * ny:, :]

    return U_p, U_f, Y_p, Y_f, N_cols


# =====================================================================
#  Oblique and orthogonal projections
# =====================================================================
def _oblique_projection(A: Mat, B: Mat, C: Mat) -> Mat:
    """
    Oblique projection of row space of A along row space of B
    onto row space of C.

    Ob = A /_{B} C = A · [B; C]^† · [0; C]

    where ^† is the Moore-Penrose pseudoinverse applied row-wise.
    """
    BC = np.vstack([B, C])
    n_B = B.shape[0]
    n_C = C.shape[0]

    # Project: A * pinv(BC) * [0; C]
    BC_pinv = np.linalg.pinv(BC)

    # Select columns corresponding to C
    proj_C = np.zeros_like(BC)
    proj_C[n_B:, :] = C

    return A @ BC_pinv @ proj_C


def _orth_projection(A: Mat, B: Mat) -> Mat:
    """
    Orthogonal projection of rows of A onto row space of B.

    Pi_B(A) = A · B^T · (B · B^T)^{-1} · B
    """
    return A @ B.T @ np.linalg.pinv(B @ B.T) @ B


def _orth_complement_projection(A: Mat, B: Mat) -> Mat:
    """
    Project rows of A onto the orthogonal complement of row space of B.

    Pi_B^perp(A) = A - Pi_B(A)
    """
    return A - _orth_projection(A, B)


# =====================================================================
#  N4SID
# =====================================================================
def _n4sid(
    U_p: Mat, U_f: Mat, Y_p: Mat, Y_f: Mat,
    ny: int, nu: int, f: int, p: int, N_cols: int,
    config: SubspaceConfig,
) -> Tuple[Mat, Vec, int]:
    """
    N4SID algorithm.

    Returns (observability_matrix, singular_values, selected_order).
    """
    # Stack past data
    W_p = np.vstack([U_p, Y_p])  # (p*(nu+ny), N_cols)

    # Oblique projection of Y_f along U_f onto W_p
    O_i = _oblique_projection(Y_f, U_f, W_p)

    # SVD
    U, S, Vt = np.linalg.svd(O_i, full_matrices=False)

    # Order selection
    nx = _select_order(S, config)

    # Observability matrix
    Gamma = U[:, :nx] @ np.diag(np.sqrt(S[:nx]))

    logger.info("N4SID: oblique projection shape %s, selected nx=%d", O_i.shape, nx)
    return Gamma, S, nx


# =====================================================================
#  MOESP
# =====================================================================
def _moesp(
    U_p: Mat, U_f: Mat, Y_p: Mat, Y_f: Mat,
    ny: int, nu: int, f: int, p: int, N_cols: int,
    config: SubspaceConfig,
) -> Tuple[Mat, Vec, int]:
    """
    MOESP algorithm.

    Uses QR decomposition to remove input contribution,
    then SVD on the residual.
    """
    # Project Y_f onto orthogonal complement of U_f
    Y_f_perp = _orth_complement_projection(Y_f, U_f)

    # SVD of the projected output
    U, S, Vt = np.linalg.svd(Y_f_perp, full_matrices=False)

    # Order selection
    nx = _select_order(S, config)

    # Observability matrix
    Gamma = U[:, :nx] @ np.diag(np.sqrt(S[:nx]))

    logger.info("MOESP: projected shape %s, selected nx=%d", Y_f_perp.shape, nx)
    return Gamma, S, nx


# =====================================================================
#  CVA
# =====================================================================
def _cva(
    U_p: Mat, U_f: Mat, Y_p: Mat, Y_f: Mat,
    ny: int, nu: int, f: int, p: int, N_cols: int,
    config: SubspaceConfig,
) -> Tuple[Mat, Vec, int]:
    """
    Canonical Variate Analysis.

    Applies statistical weighting based on covariance of
    future outputs and past data.
    """
    W_p = np.vstack([U_p, Y_p])

    # Remove future input contribution
    Y_f_perp = _orth_complement_projection(Y_f, U_f)
    W_p_perp = _orth_complement_projection(W_p, U_f)

    # Covariance weighting
    Sigma_ff = Y_f_perp @ Y_f_perp.T / N_cols
    Sigma_pp = W_p_perp @ W_p_perp.T / N_cols

    # Regularise for numerical safety
    eps = 1e-10 * np.trace(Sigma_ff) / Sigma_ff.shape[0]
    Sigma_ff += eps * np.eye(Sigma_ff.shape[0])
    eps_p = 1e-10 * np.trace(Sigma_pp) / Sigma_pp.shape[0]
    Sigma_pp += eps_p * np.eye(Sigma_pp.shape[0])

    # Inverse square roots
    try:
        L_ff = np.linalg.cholesky(Sigma_ff)
        L_pp = np.linalg.cholesky(Sigma_pp)
        L_ff_inv = np.linalg.inv(L_ff)
        L_pp_inv = np.linalg.inv(L_pp)
    except np.linalg.LinAlgError:
        logger.warning("CVA: Cholesky failed — falling back to SVD-based pseudo square root")
        L_ff_inv = _matrix_sqrt_inv(Sigma_ff)
        L_pp_inv = _matrix_sqrt_inv(Sigma_pp)

    # Cross-covariance
    Sigma_fp = Y_f_perp @ W_p_perp.T / N_cols

    # Weighted cross-covariance
    H_cva = L_ff_inv @ Sigma_fp @ L_pp_inv.T

    U, S, Vt = np.linalg.svd(H_cva, full_matrices=False)

    # Order selection
    nx = _select_order(S, config)

    # Observability matrix (undo weighting)
    Gamma = np.linalg.inv(L_ff_inv)[:, :] @ U[:, :nx] @ np.diag(np.sqrt(S[:nx]))

    logger.info("CVA: canonical correlations top-5: %s, selected nx=%d",
                S[:min(5, len(S))].round(4), nx)
    return Gamma, S, nx


def _matrix_sqrt_inv(M: Mat) -> Mat:
    """Compute M^{-1/2} via eigendecomposition."""
    eigvals, eigvecs = np.linalg.eigh(M)
    eigvals = np.maximum(eigvals, 1e-15)
    return eigvecs @ np.diag(1.0 / np.sqrt(eigvals)) @ eigvecs.T


# =====================================================================
#  Order selection
# =====================================================================
def _select_order(S: Vec, config: SubspaceConfig) -> int:
    """
    Select model order from singular values.

    If config.nx is set, use it directly.
    Otherwise, use a combined energy + gap strategy:
      1. Compute cumulative energy: E(n) = Σσ²(1..n) / Σσ²(all).
      2. Find the smallest n where E(n) ≥ 0.99 (captures 99% energy).
      3. Within candidates, find the largest consecutive SV ratio gap.
      4. Take the maximum of (2) and the gap-based estimate for robustness.
    """
    if config.nx is not None:
        nx = min(config.nx, len(S))
        logger.debug("Order fixed at nx=%d", nx)
        return nx

    S_pos = np.maximum(S, 1e-30)
    nx_max = min(config.nx_max, len(S_pos) - 1)

    if nx_max < 2:
        return 1

    # Energy criterion: find where 99% cumulative energy is reached
    energy = S_pos[:nx_max + 1] ** 2
    cum_energy = np.cumsum(energy)
    total_energy = np.sum(S_pos ** 2)
    energy_ratio = cum_energy / total_energy

    nx_energy = 1
    for n in range(1, nx_max + 1):
        if energy_ratio[n - 1] >= 0.99:
            nx_energy = n
            break
    else:
        nx_energy = nx_max

    # Gap criterion: largest ratio σ(n)/σ(n+1) after removing the
    # dominant first ratio (which is almost always the largest)
    ratios = S_pos[:nx_max] / S_pos[1:nx_max + 1]

    # Skip index 0 — the first SV always dominates
    best_gap = 0.0
    nx_gap = 1
    for n in range(1, min(nx_max, len(ratios))):
        if ratios[n] > best_gap:
            best_gap = ratios[n]
            nx_gap = n + 1  # order = index after the gap

    # Take the larger of the two estimates for robustness
    # (energy tends to under-estimate, gap tends to find real structure)
    best_nx = max(nx_energy, nx_gap)
    best_nx = min(best_nx, nx_max)
    best_nx = max(best_nx, 1)

    logger.info(
        "Auto order selection: nx=%d (energy@99%%=%d, gap=%d at ratio=%.2f, "
        "σ_%d/σ_1=%.4f)",
        best_nx, nx_energy, nx_gap, best_gap,
        best_nx + 1, S_pos[best_nx] / S_pos[0] if best_nx < len(S_pos) else 0.0,
    )
    return best_nx


# =====================================================================
#  System matrix extraction
# =====================================================================
def _extract_system_matrices(
    Gamma: Mat, U_p: Mat, U_f: Mat, Y_p: Mat, Y_f: Mat,
    ny: int, nu: int, f: int, p: int, N_cols: int,
    nx: int, config: SubspaceConfig,
) -> Tuple[Mat, Mat, Mat, Mat]:
    """
    Extract (A, B, C, D) from the observability matrix Gamma.

    C = Gamma[0:ny, :]  (first block row)
    A = Gamma^† · Gamma_shifted   (shift structure)
    B, D from least-squares on the state equation.
    """
    # C: first ny rows of Gamma
    C = Gamma[:ny, :]

    # A: shift property of observability matrix
    # Gamma_up = Gamma[:-ny, :],  Gamma_down = Gamma[ny:, :]
    # Gamma_down = Gamma_up · A  →  A = pinv(Gamma_up) · Gamma_down
    Gamma_up = Gamma[:-ny, :]
    Gamma_down = Gamma[ny:, :]
    A = np.linalg.pinv(Gamma_up) @ Gamma_down

    # State sequence from projection
    Gamma_pinv = np.linalg.pinv(Gamma)

    # Reconstruct state sequence X
    W_p = np.vstack([U_p, Y_p])

    # For N4SID: X = Gamma^† · O_i
    O_i = _oblique_projection(Y_f, U_f, W_p)
    X = Gamma_pinv @ O_i  # (nx, N_cols)

    # Build shifted state and output for LS fit
    # x(k+1) = A x(k) + B u(k)
    # y(k)   = C x(k) + D u(k)
    X_k = X[:, :-1]        # (nx, N_cols-1)
    X_k1 = X[:, 1:]        # (nx, N_cols-1)
    U_k = U_f[:nu, :-1]    # (nu, N_cols-1) — first block row of U_f
    Y_k = Y_f[:ny, :-1]    # (ny, N_cols-1) — first block row of Y_f

    # Solve [X_k1; Y_k] = [A B; C D] · [X_k; U_k]
    LHS = np.vstack([X_k1, Y_k])               # (nx+ny, N_cols-1)
    RHS = np.vstack([X_k, U_k])                 # (nx+nu, N_cols-1)

    # Least squares: Theta = LHS · pinv(RHS)
    Theta = LHS @ np.linalg.pinv(RHS)           # (nx+ny, nx+nu)

    A = Theta[:nx, :nx]
    B = Theta[:nx, nx:]
    C = Theta[nx:, :nx]
    D = Theta[nx:, nx:]

    if config.force_zero_D:
        D = np.zeros((ny, nu))
        logger.debug("D matrix forced to zero")

    return A, B, C, D


# =====================================================================
#  Kalman gain estimation
# =====================================================================
def _estimate_kalman_gain(
    A: Mat, B: Mat, C: Mat, D: Mat,
    u: Mat, y: Mat, nx: int
) -> Tuple[Mat, Mat, Mat]:
    """
    Estimate Kalman gain K from one-step prediction residuals.

    Uses the steady-state covariance approach:
    K = A P C^T (C P C^T + R)^{-1}

    Also returns predicted output and residuals.
    """
    nu, N = u.shape
    ny = y.shape[0]

    # Simulate forward to get residuals
    x = np.zeros(nx)
    y_pred = np.zeros((ny, N))
    residuals = np.zeros((ny, N))

    for k in range(N):
        y_pred[:, k] = C @ x + D @ u[:, k]
        residuals[:, k] = y[:, k] - y_pred[:, k]
        x = A @ x + B @ u[:, k]

    # Innovation covariance
    R_e = residuals @ residuals.T / N

    # Solve DARE for P: P = A P A^T + Q - A P C^T (C P C^T + R)^{-1} C P A^T
    # Simplified: use direct residual-based approach
    # K ≈ (A · X_res · Y_res^T) / (Y_res · Y_res^T)
    # where X_res, Y_res are innovation-driven sequences

    # Practical approach: solve via scipy DARE if available, otherwise
    # use the simple innovation gain from residuals
    try:
        from scipy.linalg import solve_discrete_are
        Q = np.eye(nx) * np.trace(R_e) / ny * 0.01  # rough process noise
        R = R_e.copy()
        P = solve_discrete_are(A.T, C.T, Q, R)
        S = C @ P @ C.T + R
        K = A @ P @ C.T @ np.linalg.inv(S)
    except Exception:
        # Fallback: simple least-squares on innovation form
        # x(k+1) = A x(k) + B u(k) + K e(k)
        # Re-simulate with innovation feedback
        K = np.zeros((nx, ny))
        logger.debug("Kalman gain estimation: DARE failed, using K=0")

    return K, y_pred, residuals


# =====================================================================
#  Stability enforcement
# =====================================================================
def _enforce_stability(A: Mat, gamma: float = 0.99) -> Mat:
    """
    Reflect eigenvalues outside the unit circle to magnitude gamma.
    Preserves eigenvector directions.
    """
    eigvals, eigvecs = np.linalg.eig(A)
    modified = False
    for i in range(len(eigvals)):
        mag = np.abs(eigvals[i])
        if mag >= 1.0:
            eigvals[i] = eigvals[i] / mag * gamma
            modified = True

    if modified:
        A_stable = np.real(eigvecs @ np.diag(eigvals) @ np.linalg.inv(eigvecs))
        logger.warning("Unstable eigenvalues reflected inside unit circle (γ=%.3f)", gamma)
        return A_stable
    return A


# =====================================================================
#  Main identification engine
# =====================================================================
class SubspaceIdentifier:
    """
    MIMO subspace state-space identifier.

    Usage
    -----
    >>> ident = SubspaceIdentifier(config)
    >>> result = ident.identify(u, y)
    >>> print(result.summary())
    """

    def __init__(self, config: Optional[SubspaceConfig] = None):
        self.config = config or SubspaceConfig()

    def identify(self, u: Mat, y: Mat) -> SubspaceResult:
        """
        Identify a discrete-time state-space model from I/O data.

        Parameters
        ----------
        u : array, shape (N, nu) or (nu, N)
            Input (MV) data.
        y : array, shape (N, ny) or (ny, N)
            Output (CV) data.

        Returns
        -------
        SubspaceResult
        """
        cfg = self.config

        # ── Ensure (channels, samples) orientation ───────────────────
        u = np.atleast_2d(np.asarray(u, dtype=np.float64))
        y = np.atleast_2d(np.asarray(y, dtype=np.float64))

        if u.shape[0] > u.shape[1]:
            u = u.T
        if y.shape[0] > y.shape[1]:
            y = y.T

        nu, N = u.shape
        ny = y.shape[0]

        if y.shape[1] != N:
            raise ValueError(
                f"u has {N} samples but y has {y.shape[1]}"
            )

        min_samples = 2 * (cfg.f + cfg.p) + 10
        if N < min_samples:
            raise ValueError(
                f"Insufficient data: {N} samples, need ≥ {min_samples} "
                f"for f={cfg.f}, p={cfg.p}"
            )

        logger.info(
            "Subspace identification: method=%s, ny=%d, nu=%d, N=%d, f=%d, p=%d",
            cfg.method.value, ny, nu, N, cfg.f, cfg.p,
        )

        # ── Preprocessing ────────────────────────────────────────────
        u_proc = u.copy()
        y_proc = y.copy()
        u_mean = np.zeros(nu)
        y_mean = np.zeros(ny)

        if cfg.detrend:
            for ch in range(nu):
                u_proc[ch, :] = signal.detrend(u_proc[ch, :], type="linear")
            for ch in range(ny):
                y_proc[ch, :] = signal.detrend(y_proc[ch, :], type="linear")
            logger.debug("Applied detrending")

        if cfg.remove_mean:
            u_mean = u_proc.mean(axis=1, keepdims=True)
            y_mean = y_proc.mean(axis=1, keepdims=True)
            u_proc = u_proc - u_mean
            y_proc = y_proc - y_mean
            logger.debug("Removed means")

        # ── Build Hankel partitions ──────────────────────────────────
        U_p, U_f, Y_p, Y_f, N_cols = _partition_data(
            u_proc, y_proc, cfg.f, cfg.p
        )

        cond = np.linalg.cond(np.vstack([U_p, U_f, Y_p]))
        logger.info("Data matrix condition number: %.1f", cond)

        # ── Run algorithm ────────────────────────────────────────────
        if cfg.method == SubspaceMethod.N4SID:
            Gamma, sv, nx = _n4sid(
                U_p, U_f, Y_p, Y_f, ny, nu, cfg.f, cfg.p, N_cols, cfg
            )
        elif cfg.method == SubspaceMethod.MOESP:
            Gamma, sv, nx = _moesp(
                U_p, U_f, Y_p, Y_f, ny, nu, cfg.f, cfg.p, N_cols, cfg
            )
        elif cfg.method == SubspaceMethod.CVA:
            Gamma, sv, nx = _cva(
                U_p, U_f, Y_p, Y_f, ny, nu, cfg.f, cfg.p, N_cols, cfg
            )
        else:
            raise ValueError(f"Unknown method: {cfg.method}")

        # ── Extract system matrices ──────────────────────────────────
        A, B, C, D = _extract_system_matrices(
            Gamma, U_p, U_f, Y_p, Y_f,
            ny, nu, cfg.f, cfg.p, N_cols, nx, cfg,
        )

        # ── Stability enforcement ────────────────────────────────────
        if cfg.force_stability:
            A = _enforce_stability(A)

        eigenvalues = np.linalg.eigvals(A)
        is_stable = bool(np.all(np.abs(eigenvalues) < 1.0))

        if not is_stable:
            logger.warning(
                "Identified model is UNSTABLE: max |λ| = %.4f. "
                "Consider force_stability=True or increasing data length.",
                np.max(np.abs(eigenvalues)),
            )

        # ── Kalman gain and prediction ───────────────────────────────
        K = None
        if cfg.estimate_K:
            K, y_pred_ch, residuals_ch = _estimate_kalman_gain(
                A, B, C, D, u_proc, y_proc, nx
            )
        else:
            # Just simulate for fit metrics
            x = np.zeros(nx)
            y_pred_ch = np.zeros((ny, N))
            for k in range(N):
                y_pred_ch[:, k] = C @ x + D @ u_proc[:, k]
                x = A @ x + B @ u_proc[:, k]
            residuals_ch = y_proc - y_pred_ch

        # ── Fit metrics ──────────────────────────────────────────────
        fit_r2 = np.zeros(ny)
        fit_rmse = np.zeros(ny)
        fit_nrmse = np.zeros(ny)

        for j in range(ny):
            y_j = y_proc[j, :]
            yp_j = y_pred_ch[j, :]
            res_j = residuals_ch[j, :]

            ss_res = np.sum(res_j ** 2)
            ss_tot = np.sum((y_j - y_j.mean()) ** 2)
            fit_r2[j] = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0
            fit_rmse[j] = np.sqrt(np.mean(res_j ** 2))
            y_range = y_j.max() - y_j.min()
            fit_nrmse[j] = fit_rmse[j] / y_range if y_range > 1e-15 else 0.0

        # ── Assemble result ──────────────────────────────────────────
        result = SubspaceResult(
            A=A, B=B, C=C, D=D, K=K,
            nx=nx, ny=ny, nu=nu,
            singular_values=sv,
            config=cfg,
            eigenvalues=eigenvalues,
            y_pred=y_pred_ch.T,        # (N, ny) for user convenience
            residuals=residuals_ch.T,
            fit_r2=fit_r2,
            fit_rmse=fit_rmse,
            fit_nrmse=fit_nrmse,
            is_stable=is_stable,
            condition_number=cond,
        )

        logger.info("Identification complete: nx=%d, stable=%s", nx, is_stable)
        for j in range(ny):
            logger.info(
                "  CV%d: R²=%.4f  RMSE=%.4f", j, fit_r2[j], fit_rmse[j]
            )

        return result


# =====================================================================
#  Convenience function
# =====================================================================
def identify_ss(
    u: Mat,
    y: Mat,
    method: str = "n4sid",
    nx: Optional[int] = None,
    f: int = 20,
    dt: float = 1.0,
    **kwargs,
) -> SubspaceResult:
    """
    One-call MIMO subspace identification.

    Parameters
    ----------
    u : array (N, nu)
        Input data.
    y : array (N, ny)
        Output data.
    method : str
        "n4sid", "moesp", or "cva".
    nx : int or None
        Model order (None for auto).
    f : int
        Future/past horizon.
    dt : float
        Sample period (seconds).

    Returns
    -------
    SubspaceResult

    Example
    -------
    >>> result = identify_ss(u, y, method="n4sid", nx=4, f=20, dt=1.0)
    >>> print(result.summary())
    >>> step = result.to_step(N=120)
    """
    cfg = SubspaceConfig(
        method=SubspaceMethod(method),
        nx=nx,
        f=f,
        dt=dt,
        **kwargs,
    )
    return SubspaceIdentifier(cfg).identify(u, y)


# =====================================================================
#  Wood-Berry simulation helper
# =====================================================================
class WoodBerrySimulator:
    """
    Simulate the Wood-Berry distillation column for testing.

    Continuous-time FOPTD model discretised via ZOH.

    Transfer function matrix:
        G11 = 12.8  / (16.7s+1) · e^{-1s}
        G12 = -18.9 / (21.0s+1) · e^{-3s}
        G21 = 6.6   / (10.9s+1) · e^{-7s}
        G22 = -19.4 / (14.4s+1) · e^{-3s}

    Parameters
    ----------
    dt : float
        Sample period in minutes.
    noise_std : float
        Measurement noise standard deviation (per output).
    """

    # Channel parameters: (gain, tau, theta)
    CHANNELS = {
        (0, 0): (12.8, 16.7, 1.0),
        (0, 1): (-18.9, 21.0, 3.0),
        (1, 0): (6.6, 10.9, 7.0),
        (1, 1): (-19.4, 14.4, 3.0),
    }

    def __init__(self, dt: float = 1.0, noise_std: float = 0.05):
        self.dt = dt
        self.noise_std = noise_std
        self.ny = 2
        self.nu = 2

        # Discretise each FOPTD channel
        self._systems = {}
        for (i, j), (K, tau, theta) in self.CHANNELS.items():
            delay_samples = max(1, int(round(theta / dt)))
            # Continuous: K / (tau*s + 1)  → discrete via ZOH
            a_c = -1.0 / tau
            b_c = K / tau
            # ZOH discretisation:
            #   a_d = exp(a_c * dt)
            #   b_d = (1 - a_d) * K  (for FOPTD)
            a_d = np.exp(a_c * dt)
            b_d = (1.0 - a_d) * K
            self._systems[(i, j)] = {
                "a": a_d,
                "b": b_d,
                "delay": delay_samples,
                "K": K,
                "tau": tau,
                "theta": theta,
            }

    def simulate(
        self,
        u: Mat,
        seed: Optional[int] = None,
    ) -> Mat:
        """
        Simulate the Wood-Berry column.

        Parameters
        ----------
        u : array (N, 2)
            Input signals [reflux, steam].
        seed : int, optional
            Random seed for noise.

        Returns
        -------
        y : array (N, 2)
            Output signals [X_D, X_B].
        """
        u = np.atleast_2d(np.asarray(u, dtype=np.float64))
        if u.shape[1] != 2:
            if u.shape[0] == 2:
                u = u.T
            else:
                raise ValueError("u must have 2 columns (reflux, steam)")

        N = u.shape[0]
        rng = np.random.default_rng(seed)

        # Simulate each FOPTD channel: y_ij(k+1) = a_d * y_ij(k) + (1-a_d) * K * u_j(k-d)
        y_out = np.zeros((N, 2))
        for (i, j), sys in self._systems.items():
            a_d = sys["a"]
            delay = sys["delay"]
            K = sys["K"]

            channel_y = 0.0
            for k in range(N):
                u_del = u[k - delay, j] if k >= delay else 0.0
                channel_y = a_d * channel_y + (1.0 - a_d) * K * u_del
                y_out[k, i] += channel_y

        # Add measurement noise
        if self.noise_std > 0:
            y_out += rng.normal(0, self.noise_std, y_out.shape)

        return y_out

    def true_gains(self) -> Mat:
        """Return the true steady-state gain matrix."""
        G = np.zeros((2, 2))
        for (i, j), sys in self._systems.items():
            G[i, j] = sys["K"]
        return G

    def true_dead_times(self) -> Mat:
        """Return true dead times in samples."""
        D = np.zeros((2, 2), dtype=int)
        for (i, j), sys in self._systems.items():
            D[i, j] = sys["delay"]
        return D

    @staticmethod
    def generate_prbs(
        N: int,
        nu: int = 2,
        amplitudes: Optional[List[float]] = None,
        switch_prob: float = 0.05,
        seed: Optional[int] = None,
    ) -> Mat:
        """
        Generate pseudo-random binary signals for step testing.

        Parameters
        ----------
        N : int
            Number of samples.
        nu : int
            Number of input channels.
        amplitudes : list of float
            Amplitude per channel (default: [1.0, 1.0]).
        switch_prob : float
            Probability of switching at each time step.
        seed : int, optional

        Returns
        -------
        u : array (N, nu)
        """
        rng = np.random.default_rng(seed)
        if amplitudes is None:
            amplitudes = [1.0] * nu

        u = np.zeros((N, nu))
        for j in range(nu):
            level = amplitudes[j]
            for k in range(N):
                if rng.random() < switch_prob:
                    level = -level
                u[k, j] = level

        return u
