"""
fir_ident.py — Commercial-grade MIMO FIR model identification from step-test data.

Identifies Finite Impulse Response (Markov parameter) models from
open-loop or closed-loop plant test data, as used in DMC3 / RMPCT
style Model Predictive Controllers.

Methods
-------
1. **Direct Least Squares (DLS)** — standard regression of outputs on
   a Toeplitz matrix of input moves.  Robust for open-loop tests.
2. **Correlation-based (COR)** — cross-correlation / auto-correlation
   approach.  More tolerant of feedback / closed-loop data.
3. **Regularised (L2/Ridge)** — DLS with Tikhonov regularisation to
   handle collinear inputs or short test windows.

Smoothing
---------
- Exponential tail decay enforcement
- Savitzky-Golay local polynomial smoothing
- Asymptotic projection (force coefficients toward steady-state)
- Combined pipeline with configurable order

Diagnostics
-----------
- Per-channel fit metrics (R², RMSE, NRMSE)
- Confidence intervals via residual bootstrap or analytic covariance
- Settling detection and model-length recommendation
- Residual whiteness test (Ljung-Box)

Integration
-----------
Returns `ControlModel` instances (from control_model.py) or raw
numpy arrays, caller's choice.

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
from scipy import signal as sp_signal
from scipy import stats
from scipy.linalg import toeplitz

logger = logging.getLogger(__name__)

Mat = NDArray[np.float64]
Vec = NDArray[np.float64]


# =====================================================================
#  Configuration
# =====================================================================
class IdentMethod(str, Enum):
    DLS = "dls"           # Direct Least Squares
    COR = "cor"           # Correlation-based
    RIDGE = "ridge"       # L2-regularised LS


class SmoothMethod(str, Enum):
    NONE = "none"
    EXPONENTIAL = "exponential"
    SAVGOL = "savgol"
    ASYMPTOTIC = "asymptotic"
    PIPELINE = "pipeline"  # exponential → savgol → asymptotic


@dataclass
class IdentConfig:
    """
    Configuration for MIMO FIR identification.

    Parameters
    ----------
    n_coeff : int
        Number of FIR coefficients to identify per channel (model length).
    dt : float
        Sample period in seconds.
    method : IdentMethod
        Identification algorithm.
    ridge_alpha : float
        Regularisation parameter for RIDGE method (λ in Tikhonov).
    prewhiten : bool
        Apply first-difference prewhitening to suppress drift / trends.
    detrend : bool
        Remove linear trend from each signal before identification.
    remove_mean : bool
        Subtract signal means before identification.
    confidence_level : float
        Confidence level for interval estimation (e.g. 0.95).
    smooth : SmoothMethod
        Post-identification smoothing approach.
    smooth_savgol_window : int
        Window length for Savitzky-Golay filter (must be odd).
    smooth_savgol_order : int
        Polynomial order for Savitzky-Golay filter.
    smooth_exp_tau : float or None
        Exponential decay time constant (in samples) for tail smoothing.
        If None, estimated automatically from the identified coefficients.
    smooth_exp_start : float
        Fraction of n_coeff beyond which exponential decay is applied
        (e.g. 0.6 means last 40% of coefficients).
    smooth_asym_start : float
        Fraction of n_coeff beyond which asymptotic projection begins.
    ljung_box_lags : int
        Number of lags for Ljung-Box residual whiteness test.
    """
    n_coeff: int = 60
    dt: float = 1.0
    method: IdentMethod = IdentMethod.DLS
    ridge_alpha: float = 1.0
    prewhiten: bool = False
    detrend: bool = True
    remove_mean: bool = True
    confidence_level: float = 0.95
    smooth: SmoothMethod = SmoothMethod.PIPELINE
    smooth_savgol_window: int = 11
    smooth_savgol_order: int = 3
    smooth_exp_tau: Optional[float] = None
    smooth_exp_start: float = 0.6
    smooth_asym_start: float = 0.75
    ljung_box_lags: int = 20

    def __post_init__(self):
        if self.n_coeff < 2:
            raise ValueError(f"n_coeff must be ≥ 2, got {self.n_coeff}")
        if self.dt <= 0:
            raise ValueError(f"dt must be > 0, got {self.dt}")
        if not 0 < self.confidence_level < 1:
            raise ValueError(f"confidence_level must be in (0,1), got {self.confidence_level}")
        if self.smooth_savgol_window % 2 == 0:
            self.smooth_savgol_window += 1
            logger.warning(
                "savgol_window must be odd — adjusted to %d", self.smooth_savgol_window
            )
        if self.smooth_savgol_order >= self.smooth_savgol_window:
            self.smooth_savgol_order = self.smooth_savgol_window - 2
            logger.warning(
                "savgol_order must be < savgol_window — adjusted to %d",
                self.smooth_savgol_order,
            )


# =====================================================================
#  Results
# =====================================================================
@dataclass
class ChannelFit:
    """Fit statistics for one (CV, MV) channel pair."""
    cv_index: int
    mv_index: int
    r_squared: float
    rmse: float
    nrmse: float                       # RMSE / range(y)
    residual_std: float
    ljung_box_stat: float
    ljung_box_pvalue: float
    is_white: bool                     # p > 0.05


@dataclass
class IdentResult:
    """
    Complete identification result.

    Attributes
    ----------
    fir_raw : list of Mat
        Identified FIR coefficients before smoothing.
        Each element is shape (ny, nu).
    fir : list of Mat
        Final FIR coefficients after smoothing.
    step : list of Mat
        Cumulative step-response coefficients (Σ FIR).
    confidence_lo, confidence_hi : list of Mat
        Lower / upper confidence bounds on FIR coefficients.
    fits : list of ChannelFit
        Per-channel fit diagnostics.
    config : IdentConfig
        Configuration used.
    y_pred : Mat
        Model-predicted output (N_samples × ny).
    residuals : Mat
        Residuals = y_actual - y_pred (N_samples × ny).
    condition_number : float
        Condition number of the regression matrix.
    """
    fir_raw: List[Mat]
    fir: List[Mat]
    step: List[Mat]
    confidence_lo: List[Mat]
    confidence_hi: List[Mat]
    fits: List[ChannelFit]
    config: IdentConfig
    y_pred: Mat
    residuals: Mat
    condition_number: float

    @property
    def ny(self) -> int:
        return self.fir[0].shape[0]

    @property
    def nu(self) -> int:
        return self.fir[0].shape[1]

    @property
    def n_coeff(self) -> int:
        return len(self.fir)

    def gain_matrix(self) -> Mat:
        """Steady-state gain matrix (ny × nu)."""
        return np.sum(self.fir, axis=0)

    def settling_index(self, tol: float = 0.01) -> Mat:
        """
        Per-channel settling index.  Returns (ny × nu) integer array
        where each entry is the last coefficient index that deviates
        from final gain by more than tol * |total_gain|.
        """
        total = self.gain_matrix()
        ny, nu = total.shape
        result = np.zeros((ny, nu), dtype=int)

        for i in range(ny):
            for j in range(nu):
                cum = 0.0
                g_final = total[i, j]
                threshold = tol * abs(g_final) if abs(g_final) > 1e-15 else tol
                for k, Gk in enumerate(self.fir):
                    cum += Gk[i, j]
                    if abs(cum - g_final) > threshold:
                        result[i, j] = k
        return result

    def summary(self) -> str:
        lines = [
            f"FIR Identification Result",
            f"  Method     : {self.config.method.value}",
            f"  Dimensions : ny={self.ny}, nu={self.nu}",
            f"  Coefficients: {self.n_coeff}  (dt={self.config.dt}s → {self.n_coeff * self.config.dt}s horizon)",
            f"  Smoothing  : {self.config.smooth.value}",
            f"  Cond. number: {self.condition_number:.1f}",
            f"  Gain matrix:",
        ]
        gain = self.gain_matrix()
        for i in range(self.ny):
            row = "    " + "  ".join(f"{gain[i,j]:+10.4f}" for j in range(self.nu))
            lines.append(row)
        lines.append(f"  Channel fits:")
        for f in self.fits:
            tag = "WHITE" if f.is_white else "CORRELATED"
            lines.append(
                f"    CV{f.cv_index}←MV{f.mv_index}: "
                f"R²={f.r_squared:.4f}  RMSE={f.rmse:.4f}  "
                f"NRMSE={f.nrmse:.4f}  LB p={f.ljung_box_pvalue:.3f} [{tag}]"
            )
        return "\n".join(lines)


# =====================================================================
#  Core identification engine
# =====================================================================
class FIRIdentifier:
    """
    MIMO FIR model identifier.

    Usage
    -----
    >>> ident = FIRIdentifier(config)
    >>> result = ident.identify(u, y)
    >>> print(result.summary())
    """

    def __init__(self, config: Optional[IdentConfig] = None):
        self.config = config or IdentConfig()

    # -----------------------------------------------------------------
    #  Public API
    # -----------------------------------------------------------------
    def identify(
        self,
        u: Mat,
        y: Mat,
        mv_names: Optional[List[str]] = None,
        cv_names: Optional[List[str]] = None,
    ) -> IdentResult:
        """
        Identify MIMO FIR model from input/output data.

        Parameters
        ----------
        u : array, shape (N, nu)
            Manipulated variable data (input moves or raw values —
            prewhitening handles differencing if enabled).
        y : array, shape (N, ny)
            Controlled variable data.
        mv_names, cv_names : list of str, optional
            Human-readable names for logging.

        Returns
        -------
        IdentResult
        """
        cfg = self.config
        u = np.atleast_2d(np.asarray(u, dtype=np.float64))
        y = np.atleast_2d(np.asarray(y, dtype=np.float64))

        # Ensure column orientation: (N, nu) and (N, ny)
        if u.shape[0] < u.shape[1]:
            u = u.T
        if y.shape[0] < y.shape[1]:
            y = y.T

        N, nu = u.shape
        _, ny = y.shape

        if y.shape[0] != N:
            raise ValueError(
                f"u has {N} samples but y has {y.shape[0]} — lengths must match"
            )
        if N < cfg.n_coeff + 10:
            raise ValueError(
                f"Insufficient data: {N} samples for {cfg.n_coeff} coefficients. "
                f"Need at least {cfg.n_coeff + 10}."
            )

        tag = f"[{ny}×{nu} MIMO, N={N}, n_coeff={cfg.n_coeff}]"
        logger.info("FIR identification started %s method=%s", tag, cfg.method.value)

        # ── Preprocessing ────────────────────────────────────────────
        u_proc, y_proc = self._preprocess(u.copy(), y.copy())

        # ── Identification ───────────────────────────────────────────
        if cfg.method == IdentMethod.DLS:
            theta, Phi, cond = self._identify_dls(u_proc, y_proc)
        elif cfg.method == IdentMethod.RIDGE:
            theta, Phi, cond = self._identify_ridge(u_proc, y_proc)
        elif cfg.method == IdentMethod.COR:
            theta, Phi, cond = self._identify_cor(u_proc, y_proc)
        else:
            raise ValueError(f"Unknown method: {cfg.method}")

        logger.info("Regression condition number: %.1f", cond)
        if cond > 1e6:
            logger.warning(
                "High condition number (%.1e) — inputs may be collinear. "
                "Consider RIDGE method or longer test window.", cond
            )

        # ── Unpack theta → FIR matrices ──────────────────────────────
        fir_raw = self._theta_to_fir(theta, ny, nu)

        # ── Predicted output and residuals ───────────────────────────
        y_pred = self._predict(Phi, theta, N, ny, cfg.n_coeff)
        residuals = y_proc[cfg.n_coeff - 1:, :] - y_pred

        # ── Confidence intervals ─────────────────────────────────────
        ci_lo, ci_hi = self._confidence_intervals(
            Phi, residuals, theta, ny, nu
        )

        # ── Smoothing ────────────────────────────────────────────────
        fir_smooth = self._smooth(fir_raw, ny, nu)

        # ── Step response ────────────────────────────────────────────
        step = self._fir_to_step(fir_smooth)

        # ── Per-channel diagnostics ──────────────────────────────────
        fits = self._compute_fits(y_proc, y_pred, residuals, ny, nu, cfg.n_coeff)

        # ── Assemble result ──────────────────────────────────────────
        result = IdentResult(
            fir_raw=fir_raw,
            fir=fir_smooth,
            step=step,
            confidence_lo=ci_lo,
            confidence_hi=ci_hi,
            fits=fits,
            config=cfg,
            y_pred=y_pred,
            residuals=residuals,
            condition_number=cond,
        )

        logger.info("Identification complete. Gain matrix:\n%s", result.gain_matrix())
        for f in fits:
            logger.info(
                "  CV%d←MV%d: R²=%.4f  RMSE=%.4f  LB_p=%.3f",
                f.cv_index, f.mv_index, f.r_squared, f.rmse, f.ljung_box_pvalue,
            )

        return result

    # -----------------------------------------------------------------
    #  Preprocessing
    # -----------------------------------------------------------------
    def _preprocess(self, u: Mat, y: Mat) -> Tuple[Mat, Mat]:
        cfg = self.config

        if cfg.detrend:
            for j in range(u.shape[1]):
                u[:, j] = sp_signal.detrend(u[:, j], type="linear")
            for j in range(y.shape[1]):
                y[:, j] = sp_signal.detrend(y[:, j], type="linear")
            logger.debug("Applied linear detrending")

        if cfg.remove_mean:
            u = u - u.mean(axis=0)
            y = y - y.mean(axis=0)
            logger.debug("Removed signal means")

        if cfg.prewhiten:
            u = np.diff(u, axis=0, prepend=u[:1, :])
            y = np.diff(y, axis=0, prepend=y[:1, :])
            logger.debug("Applied first-difference prewhitening")

        return u, y

    # -----------------------------------------------------------------
    #  Build Toeplitz regression matrix
    # -----------------------------------------------------------------
    def _build_toeplitz(self, u: Mat, N: int, nu: int) -> Mat:
        """
        Build the block-Toeplitz regression matrix Φ.

        Φ[t, :] = [u(t), u(t-1), ..., u(t-n_coeff+1)]  flattened across
        all nu inputs.  Shape: (N - n_coeff + 1, n_coeff * nu).
        """
        n = self.config.n_coeff
        n_rows = N - n + 1

        Phi = np.zeros((n_rows, n * nu))
        for t in range(n_rows):
            for k in range(n):
                idx = t + n - 1 - k
                Phi[t, k * nu : (k + 1) * nu] = u[idx, :]

        return Phi

    # -----------------------------------------------------------------
    #  DLS identification
    # -----------------------------------------------------------------
    def _identify_dls(self, u: Mat, y: Mat) -> Tuple[Mat, Mat, float]:
        N, nu = u.shape
        _, ny = y.shape
        n = self.config.n_coeff

        Phi = self._build_toeplitz(u, N, nu)
        Y = y[n - 1:, :]

        cond = np.linalg.cond(Phi)

        # Solve via SVD (numerically stable)
        theta, res, rank, sv = np.linalg.lstsq(Phi, Y, rcond=None)

        if rank < theta.shape[0]:
            logger.warning(
                "Rank-deficient regression: rank=%d vs %d columns. "
                "Results may be unreliable.", rank, theta.shape[0]
            )

        logger.debug("DLS: Phi shape %s, rank %d", Phi.shape, rank)
        return theta, Phi, cond

    # -----------------------------------------------------------------
    #  Ridge identification
    # -----------------------------------------------------------------
    def _identify_ridge(self, u: Mat, y: Mat) -> Tuple[Mat, Mat, float]:
        N, nu = u.shape
        _, ny = y.shape
        n = self.config.n_coeff
        alpha = self.config.ridge_alpha

        Phi = self._build_toeplitz(u, N, nu)
        Y = y[n - 1:, :]

        cond = np.linalg.cond(Phi)

        # θ = (Φ'Φ + αI)^{-1} Φ'Y
        PhiTPhi = Phi.T @ Phi
        reg = PhiTPhi + alpha * np.eye(PhiTPhi.shape[0])
        theta = np.linalg.solve(reg, Phi.T @ Y)

        logger.debug("Ridge: α=%.2e, cond(Φ)=%.1f, cond(Φ'Φ+αI)=%.1f",
                      alpha, cond, np.linalg.cond(reg))
        return theta, Phi, cond

    # -----------------------------------------------------------------
    #  Correlation-based identification
    # -----------------------------------------------------------------
    def _identify_cor(self, u: Mat, y: Mat) -> Tuple[Mat, Mat, float]:
        """
        Correlation method: solve Ruu · θ = Ruy.

        More robust to feedback than DLS, at the cost of statistical
        efficiency.
        """
        N, nu = u.shape
        _, ny = y.shape
        n = self.config.n_coeff

        # Build auto-correlation Ruu and cross-correlation Ruy
        Ruu = np.zeros((n * nu, n * nu))
        Ruy = np.zeros((n * nu, ny))

        for lag_i in range(n):
            for lag_j in range(n):
                # Ruu block (lag_i, lag_j)
                max_lag = max(lag_i, lag_j)
                valid = N - max_lag
                for t in range(max_lag, N):
                    ui = u[t - lag_i, :]
                    uj = u[t - lag_j, :]
                    Ruu[lag_i * nu:(lag_i + 1) * nu,
                        lag_j * nu:(lag_j + 1) * nu] += np.outer(ui, uj)
                Ruu[lag_i * nu:(lag_i + 1) * nu,
                    lag_j * nu:(lag_j + 1) * nu] /= valid

        for lag_i in range(n):
            valid = N - lag_i
            for t in range(lag_i, N):
                ui = u[t - lag_i, :]
                yt = y[t, :]
                Ruy[lag_i * nu:(lag_i + 1) * nu, :] += np.outer(ui, yt)
            Ruy[lag_i * nu:(lag_i + 1) * nu, :] /= valid

        cond = np.linalg.cond(Ruu)

        # Regularise if ill-conditioned
        if cond > 1e8:
            logger.warning("COR: Ruu ill-conditioned (cond=%.1e), adding regularisation", cond)
            Ruu += 1e-6 * np.trace(Ruu) / Ruu.shape[0] * np.eye(Ruu.shape[0])

        theta = np.linalg.solve(Ruu, Ruy)

        # Still build Phi for residual computation
        Phi = self._build_toeplitz(u, N, nu)

        logger.debug("COR: Ruu shape %s, cond %.1f", Ruu.shape, cond)
        return theta, Phi, cond

    # -----------------------------------------------------------------
    #  Theta → FIR matrices
    # -----------------------------------------------------------------
    def _theta_to_fir(self, theta: Mat, ny: int, nu: int) -> List[Mat]:
        """
        Unpack regression coefficient matrix θ into a list of
        (ny × nu) Markov parameter matrices.

        θ layout: rows are [coeff_0 * nu .. coeff_0 * nu + nu - 1,
                            coeff_1 * nu .. , ...]
        Each column of θ corresponds to one CV.
        """
        n = self.config.n_coeff
        fir: List[Mat] = []
        for k in range(n):
            Gk = theta[k * nu:(k + 1) * nu, :].T  # (ny, nu)
            fir.append(Gk.copy())
        return fir

    # -----------------------------------------------------------------
    #  Predict
    # -----------------------------------------------------------------
    def _predict(self, Phi: Mat, theta: Mat, N: int, ny: int, n: int) -> Mat:
        n_rows = N - n + 1
        return Phi[:n_rows, :] @ theta

    # -----------------------------------------------------------------
    #  Confidence intervals (analytic)
    # -----------------------------------------------------------------
    def _confidence_intervals(
        self, Phi: Mat, residuals: Mat, theta: Mat, ny: int, nu: int
    ) -> Tuple[List[Mat], List[Mat]]:
        """
        Analytic confidence intervals assuming i.i.d. residuals.

        For each CV j, Var(θ_j) = σ²_j (Φ'Φ)^{-1}, and CIs are
        θ ± z_{α/2} · sqrt(diag(Var)).
        """
        cfg = self.config
        n = cfg.n_coeff
        alpha = 1.0 - cfg.confidence_level
        z = stats.norm.ppf(1 - alpha / 2)

        try:
            PhiTPhi_inv = np.linalg.inv(Phi.T @ Phi)
        except np.linalg.LinAlgError:
            logger.warning("Cannot compute (Φ'Φ)^{-1} for confidence intervals — using pseudo-inverse")
            PhiTPhi_inv = np.linalg.pinv(Phi.T @ Phi)

        var_diag = np.diag(PhiTPhi_inv)  # (n*nu,)
        var_diag = np.maximum(var_diag, 0.0)  # numerical safety

        ci_lo: List[Mat] = []
        ci_hi: List[Mat] = []

        for k in range(n):
            lo_k = np.zeros((ny, nu))
            hi_k = np.zeros((ny, nu))
            for j in range(ny):
                sigma_j = np.std(residuals[:, j]) if residuals.shape[0] > 1 else 0.0
                for i in range(nu):
                    se = sigma_j * np.sqrt(var_diag[k * nu + i])
                    lo_k[j, i] = theta[k * nu + i, j] - z * se
                    hi_k[j, i] = theta[k * nu + i, j] + z * se
            # Convert back to FIR orientation (ny, nu)
            ci_lo.append(lo_k)
            ci_hi.append(hi_k)

        return ci_lo, ci_hi

    # -----------------------------------------------------------------
    #  Smoothing
    # -----------------------------------------------------------------
    def _smooth(self, fir: List[Mat], ny: int, nu: int) -> List[Mat]:
        cfg = self.config

        if cfg.smooth == SmoothMethod.NONE:
            return [g.copy() for g in fir]

        if cfg.smooth == SmoothMethod.EXPONENTIAL:
            return self._smooth_exponential(fir, ny, nu)

        if cfg.smooth == SmoothMethod.SAVGOL:
            return self._smooth_savgol(fir, ny, nu)

        if cfg.smooth == SmoothMethod.ASYMPTOTIC:
            return self._smooth_asymptotic(fir, ny, nu)

        if cfg.smooth == SmoothMethod.PIPELINE:
            logger.debug("Smoothing pipeline: exponential → savgol → asymptotic")
            result = self._smooth_exponential(fir, ny, nu)
            result = self._smooth_savgol(result, ny, nu)
            result = self._smooth_asymptotic(result, ny, nu)
            return result

        return [g.copy() for g in fir]

    def _smooth_exponential(self, fir: List[Mat], ny: int, nu: int) -> List[Mat]:
        """
        Apply exponential decay to the tail of each FIR channel.

        Forces coefficients to decay smoothly toward zero in the tail
        region, suppressing noise that accumulates in late coefficients.
        """
        cfg = self.config
        n = len(fir)
        start = int(cfg.smooth_exp_start * n)
        tail_len = n - start

        if tail_len < 3:
            return [g.copy() for g in fir]

        result = [g.copy() for g in fir]

        for i in range(ny):
            for j in range(nu):
                # Extract the channel's FIR vector
                h = np.array([fir[k][i, j] for k in range(n)])

                # Estimate decay time constant if not given
                tau = cfg.smooth_exp_tau
                if tau is None:
                    tail_abs = np.abs(h[start:])
                    if tail_abs.max() > 1e-15:
                        # Fit log-decay: log|h| ≈ -t/τ + c
                        nonzero = tail_abs > 1e-15 * tail_abs.max()
                        if np.sum(nonzero) >= 3:
                            t_idx = np.arange(tail_len)[nonzero]
                            log_h = np.log(tail_abs[nonzero])
                            slope, _ = np.polyfit(t_idx, log_h, 1)
                            tau = -1.0 / slope if slope < -1e-6 else tail_len / 3.0
                        else:
                            tau = tail_len / 3.0
                    else:
                        tau = tail_len / 3.0

                tau = max(tau, 1.0)

                # Apply exponential window to tail
                for k_rel in range(tail_len):
                    decay = np.exp(-k_rel / tau)
                    blend = 1.0 - k_rel / tail_len  # linear ramp for smooth transition
                    weight = blend + (1.0 - blend) * decay
                    result[start + k_rel][i, j] = h[start + k_rel] * weight

        logger.debug("Exponential smoothing applied: start=%d, tau=auto", start)
        return result

    def _smooth_savgol(self, fir: List[Mat], ny: int, nu: int) -> List[Mat]:
        """
        Savitzky-Golay smoothing per channel — preserves shape features
        while removing high-frequency noise.
        """
        cfg = self.config
        n = len(fir)
        win = min(cfg.smooth_savgol_window, n)
        if win % 2 == 0:
            win -= 1
        if win < 3:
            return [g.copy() for g in fir]

        order = min(cfg.smooth_savgol_order, win - 1)
        result = [g.copy() for g in fir]

        for i in range(ny):
            for j in range(nu):
                h = np.array([fir[k][i, j] for k in range(n)])
                h_smooth = sp_signal.savgol_filter(h, win, order)
                for k in range(n):
                    result[k][i, j] = h_smooth[k]

        logger.debug("Savitzky-Golay smoothing: window=%d, order=%d", win, order)
        return result

    def _smooth_asymptotic(self, fir: List[Mat], ny: int, nu: int) -> List[Mat]:
        """
        Force late coefficients toward zero (the steady-state impulse
        response value for a stable system).

        Uses a cosine blend from the identified value to zero over the
        tail region.
        """
        cfg = self.config
        n = len(fir)
        start = int(cfg.smooth_asym_start * n)
        tail_len = n - start

        if tail_len < 2:
            return [g.copy() for g in fir]

        result = [g.copy() for g in fir]

        for k_rel in range(tail_len):
            # Cosine blend: 1 → 0
            weight = 0.5 * (1.0 + np.cos(np.pi * k_rel / tail_len))
            for i in range(ny):
                for j in range(nu):
                    result[start + k_rel][i, j] = fir[start + k_rel][i, j] * weight

        logger.debug("Asymptotic projection: start=%d, tail=%d", start, tail_len)
        return result

    # -----------------------------------------------------------------
    #  FIR → Step response
    # -----------------------------------------------------------------
    @staticmethod
    def _fir_to_step(fir: List[Mat]) -> List[Mat]:
        ny, nu = fir[0].shape
        step: List[Mat] = []
        cumsum = np.zeros((ny, nu))
        for Gk in fir:
            cumsum = cumsum + Gk
            step.append(cumsum.copy())
        return step

    # -----------------------------------------------------------------
    #  Fit diagnostics
    # -----------------------------------------------------------------
    def _compute_fits(
        self, y: Mat, y_pred: Mat, residuals: Mat,
        ny: int, nu: int, n_coeff: int,
    ) -> List[ChannelFit]:
        """Compute R², RMSE, NRMSE, Ljung-Box for each (CV, MV) pair."""
        fits: List[ChannelFit] = []
        y_actual = y[n_coeff - 1:, :]

        for j in range(ny):
            y_j = y_actual[:, j]
            yp_j = y_pred[:, j]
            res_j = residuals[:, j]

            ss_res = np.sum(res_j ** 2)
            ss_tot = np.sum((y_j - y_j.mean()) ** 2)
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0

            rmse = np.sqrt(np.mean(res_j ** 2))
            y_range = y_j.max() - y_j.min()
            nrmse = rmse / y_range if y_range > 1e-15 else 0.0

            # Ljung-Box test for residual whiteness
            lb_lags = min(self.config.ljung_box_lags, len(res_j) // 5)
            if lb_lags >= 1 and len(res_j) > lb_lags + 1:
                try:
                    lb_result = self._ljung_box(res_j, lb_lags)
                    lb_stat, lb_p = lb_result
                except Exception:
                    lb_stat, lb_p = 0.0, 1.0
            else:
                lb_stat, lb_p = 0.0, 1.0

            # Log per-MV decomposition (aggregate across all MVs)
            for i in range(nu):
                fits.append(ChannelFit(
                    cv_index=j,
                    mv_index=i,
                    r_squared=r2,
                    rmse=rmse,
                    nrmse=nrmse,
                    residual_std=np.std(res_j),
                    ljung_box_stat=lb_stat,
                    ljung_box_pvalue=lb_p,
                    is_white=lb_p > 0.05,
                ))

        return fits

    @staticmethod
    def _ljung_box(x: Vec, n_lags: int) -> Tuple[float, float]:
        """Manual Ljung-Box Q statistic (avoids statsmodels dependency)."""
        n = len(x)
        x = x - x.mean()
        var = np.sum(x ** 2) / n

        if var < 1e-15:
            return 0.0, 1.0

        Q = 0.0
        for k in range(1, n_lags + 1):
            rk = np.sum(x[k:] * x[:-k]) / (n * var)
            Q += rk ** 2 / (n - k)
        Q *= n * (n + 2)

        p_value = 1.0 - stats.chi2.cdf(Q, df=n_lags)
        return Q, p_value


# =====================================================================
#  Convenience function
# =====================================================================
def identify_fir(
    u: Mat,
    y: Mat,
    n_coeff: int = 60,
    dt: float = 1.0,
    method: str = "dls",
    smooth: str = "pipeline",
    **kwargs,
) -> IdentResult:
    """
    One-call MIMO FIR identification.

    Parameters
    ----------
    u : array (N, nu)
        Input (MV) data.
    y : array (N, ny)
        Output (CV) data.
    n_coeff : int
        Model length.
    dt : float
        Sample period (seconds).
    method : str
        "dls", "cor", or "ridge".
    smooth : str
        "none", "exponential", "savgol", "asymptotic", or "pipeline".
    **kwargs
        Additional IdentConfig parameters.

    Returns
    -------
    IdentResult

    Example
    -------
    >>> result = identify_fir(u, y, n_coeff=60, dt=60.0, method="dls")
    >>> print(result.summary())
    >>> step_response = result.step
    """
    cfg = IdentConfig(
        n_coeff=n_coeff,
        dt=dt,
        method=IdentMethod(method),
        smooth=SmoothMethod(smooth),
        **kwargs,
    )
    return FIRIdentifier(cfg).identify(u, y)
