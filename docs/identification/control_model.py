"""
control_model.py — Commercial-grade control-model representation converter.

Supports three canonical representations used in Advanced Process Control:
    • Transfer Function  (TF)  — (num, den) polynomials, discrete-time
    • State-Space         (SS)  — (A, B, C, D) matrices, discrete-time
    • Finite Impulse Response (FIR) — Markov parameter sequence [G₀, G₁, …, G_{N-1}]

Conversion paths:
    TF  ⇌  SS   — exact   (scipy.signal)
    SS  →  FIR  — exact   (Markov parameter expansion)
    FIR →  SS   — shift realisation (exact, high-order) or ERA/Ho-Kalman (reduced)
    TF  →  FIR  — via dimpulse (exact for the truncation length)
    FIR →  TF   — via reduced SS (approximate)

Design targets:
    • Full MIMO support with rigorous dimension tracking
    • Validated inputs — shape mismatches raise immediately, not deep in NumPy
    • Deterministic dead-time insertion / extraction on FIR sequences
    • Immutable conversion — every method returns a *new* ControlModel
    • Logging via stdlib `logging` — no print statements

Author : Azeotrope Process Control
License: Proprietary
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Sequence, Tuple, Union

import numpy as np
from numpy.typing import NDArray
from scipy import signal

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Type aliases
# ──────────────────────────────────────────────────────────────────────
Mat = NDArray[np.float64]
TFRepr = Tuple[Mat, Mat]                       # (num, den)
SSRepr = Tuple[Mat, Mat, Mat, Mat]              # (A, B, C, D)
FIRRepr = List[Mat]                            # [G_0, G_1, …, G_{N-1}]


# ──────────────────────────────────────────────────────────────────────
# Validation helpers
# ──────────────────────────────────────────────────────────────────────
def _assert_ss(A: Mat, B: Mat, C: Mat, D: Mat) -> Tuple[int, int, int]:
    """Validate SS dimensions. Returns (nx, nu, ny)."""
    A, B, C, D = (np.atleast_2d(x) for x in (A, B, C, D))
    nx = A.shape[0]
    if A.shape != (nx, nx):
        raise ValueError(f"A must be square, got {A.shape}")
    if B.shape[0] != nx:
        raise ValueError(f"B row count {B.shape[0]} != state dim {nx}")
    nu = B.shape[1]
    if C.shape[1] != nx:
        raise ValueError(f"C col count {C.shape[1]} != state dim {nx}")
    ny = C.shape[0]
    if D.shape != (ny, nu):
        raise ValueError(f"D shape {D.shape} inconsistent with ny={ny}, nu={nu}")
    return nx, nu, ny


def _assert_fir(G: FIRRepr) -> Tuple[int, int, int]:
    """Validate FIR sequence. Returns (N, ny, nu)."""
    if not G or len(G) == 0:
        raise ValueError("FIR sequence is empty")
    ny, nu = np.atleast_2d(G[0]).shape
    for k, Gk in enumerate(G):
        Gk = np.atleast_2d(Gk)
        if Gk.shape != (ny, nu):
            raise ValueError(
                f"FIR[{k}] shape {Gk.shape} inconsistent with FIR[0] shape ({ny}, {nu})"
            )
    return len(G), ny, nu


def _ensure_2d_list(G: FIRRepr) -> FIRRepr:
    """Guarantee every element is a 2-D ndarray."""
    return [np.atleast_2d(np.asarray(g, dtype=np.float64)) for g in G]


# ──────────────────────────────────────────────────────────────────────
# Main class
# ──────────────────────────────────────────────────────────────────────
@dataclass
class ControlModel:
    """
    Unified container for TF / SS / FIR discrete-time model representations.

    Parameters
    ----------
    tf : tuple of (num, den) array-likes, optional
    ss : tuple of (A, B, C, D) array-likes, optional
    fir : list of 2-D array-likes, optional
    dt : float
        Sample period in seconds (must be > 0).
    name : str
        Human-readable tag (e.g. "40WESTCRUDE_CV3_MV2").
    ny, nu : int or None
        Output / input counts — inferred automatically on first
        representation set; used for cross-checks thereafter.
    """

    tf: Optional[TFRepr] = None
    ss: Optional[SSRepr] = None
    fir: Optional[FIRRepr] = None
    dt: float = 1.0
    name: str = ""
    ny: Optional[int] = field(default=None, repr=False)
    nu: Optional[int] = field(default=None, repr=False)

    def __post_init__(self):
        if self.dt <= 0:
            raise ValueError(f"dt must be positive, got {self.dt}")
        # Normalise whatever was supplied
        if self.ss is not None:
            self._set_ss(self.ss)
        if self.tf is not None:
            self._set_tf(self.tf)
        if self.fir is not None:
            self._set_fir(self.fir)

    # ── internal setters with validation ─────────────────────────────
    def _register_dims(self, ny: int, nu: int):
        if self.ny is None:
            self.ny, self.nu = ny, nu
        elif (self.ny, self.nu) != (ny, nu):
            raise ValueError(
                f"Dimension mismatch: existing (ny={self.ny}, nu={self.nu}) "
                f"vs new (ny={ny}, nu={nu})"
            )

    def _set_ss(self, ss: SSRepr):
        A, B, C, D = (np.atleast_2d(np.asarray(x, dtype=np.float64)) for x in ss)
        nx, nu, ny = _assert_ss(A, B, C, D)
        self._register_dims(ny, nu)
        self.ss = (A, B, C, D)
        logger.debug("SS set: nx=%d, nu=%d, ny=%d", nx, nu, ny)

    def _set_tf(self, tf: TFRepr):
        num, den = tf
        num = np.atleast_1d(np.asarray(num, dtype=np.float64))
        den = np.atleast_1d(np.asarray(den, dtype=np.float64))
        # For SISO: register dims as (1,1); for MIMO TF arrays the caller
        # is responsible for providing proper polynomial matrices.
        if num.ndim <= 1:
            self._register_dims(1, 1)
        self.tf = (num, den)
        logger.debug("TF set: num order %d, den order %d", len(num) - 1, len(den) - 1)

    def _set_fir(self, fir: FIRRepr):
        fir = _ensure_2d_list(fir)
        N, ny, nu = _assert_fir(fir)
        self._register_dims(ny, nu)
        self.fir = fir
        logger.debug("FIR set: N=%d, ny=%d, nu=%d", N, ny, nu)

    # ── deep copy helper ─────────────────────────────────────────────
    def _clone(self, **overrides) -> "ControlModel":
        """Return a deep copy with optional field overrides."""
        obj = copy.deepcopy(self)
        for k, v in overrides.items():
            setattr(obj, k, v)
        return obj

    # =================================================================
    #  TF ⇌ SS  (exact)
    # =================================================================
    def to_ss_from_tf(self) -> "ControlModel":
        """TF → SS via scipy.signal.tf2ss (controllable canonical form)."""
        if self.tf is None:
            raise ValueError("TF representation not available")
        num, den = self.tf
        A, B, C, D = signal.tf2ss(num, den)
        out = self._clone()
        out._set_ss((A, B, C, D))
        logger.info("TF → SS  (nx=%d)", A.shape[0])
        return out

    def to_tf_from_ss(self) -> "ControlModel":
        """SS → TF via scipy.signal.ss2tf."""
        if self.ss is None:
            raise ValueError("SS representation not available")
        A, B, C, D = self.ss
        num, den = signal.ss2tf(A, B, C, D)
        out = self._clone()
        out._set_tf((np.squeeze(num), den))
        logger.info("SS → TF")
        return out

    # =================================================================
    #  SS → FIR  (exact Markov parameter expansion)
    # =================================================================
    def to_fir_from_ss(self, N: int = 120) -> "ControlModel":
        """
        Compute N Markov parameters: G_k = C A^{k-1} B,  G_0 = D.

        Parameters
        ----------
        N : int
            Number of FIR coefficients (≥ 2).
        """
        if self.ss is None:
            raise ValueError("SS representation not available")
        if N < 2:
            raise ValueError(f"N must be ≥ 2, got {N}")

        A, B, C, D = self.ss
        nx = A.shape[0]

        G: FIRRepr = [D.copy()]
        Ak = np.eye(nx)
        for k in range(1, N):
            Gk = C @ Ak @ B
            G.append(Gk)
            Ak = Ak @ A

        out = self._clone()
        out._set_fir(G)
        logger.info("SS → FIR  (N=%d)", N)
        return out

    # =================================================================
    #  FIR → SS
    # =================================================================
    def to_ss_from_fir(
        self,
        method: Literal["shift", "era"] = "era",
        order: Optional[int] = None,
    ) -> "ControlModel":
        """
        Realise a state-space model from an FIR (Markov) sequence.

        Parameters
        ----------
        method : {"shift", "era"}
            "shift" — full shift-register realisation (nx = N·nu, exact).
            "era"   — Eigensystem Realisation Algorithm / Ho-Kalman
                       balanced realisation (reduced order, approximate).
        order : int, optional
            Required for method="era". Number of states to retain.
            Must satisfy  order ≤ (N-1)//2  where N = len(fir).
        """
        if self.fir is None:
            raise ValueError("FIR representation not available")

        fir = _ensure_2d_list(self.fir)
        N, ny, nu = _assert_fir(fir)

        if method == "shift":
            ss = self._shift_realisation(fir, N, ny, nu)
        elif method == "era":
            if order is None:
                order = min(10, (N - 1) // 2)
                logger.info("ERA order not specified — defaulting to %d", order)
            max_order = (N - 1) // 2
            if order > max_order:
                raise ValueError(
                    f"ERA order {order} exceeds maximum (N-1)//2 = {max_order} "
                    f"for FIR length N={N}"
                )
            if order < 1:
                raise ValueError(f"ERA order must be ≥ 1, got {order}")
            ss = self._era_realisation(fir, N, ny, nu, order)
        else:
            raise ValueError(f"Unknown method '{method}'. Use 'shift' or 'era'.")

        out = self._clone()
        out._set_ss(ss)
        logger.info("FIR → SS  (method=%s, nx=%d)", method, ss[0].shape[0])
        return out

    # ── shift realisation ────────────────────────────────────────────
    @staticmethod
    def _shift_realisation(
        G: FIRRepr, N: int, ny: int, nu: int
    ) -> SSRepr:
        """
        Companion-form realisation.  D = G[0]; shift register feeds
        delayed inputs to C which holds G[1], G[2], …, G[N-1].
        """
        n_delay = N - 1
        nx = n_delay * nu

        if nx == 0:
            # Pure gain — no dynamics
            return (
                np.zeros((0, 0)),
                np.zeros((0, nu)),
                np.zeros((ny, 0)),
                G[0].copy(),
            )

        A = np.zeros((nx, nx))
        B = np.zeros((nx, nu))
        C = np.zeros((ny, nx))
        D = G[0].copy()

        # Shift register:  x_{k+1}[i] = x_k[i-1],  x_{k+1}[0] = u_k
        B[:nu, :] = np.eye(nu)
        for i in range(1, n_delay):
            A[i * nu : (i + 1) * nu, (i - 1) * nu : i * nu] = np.eye(nu)

        # Output map:  y_k = D u_k + Σ G[i+1] x_k[i]
        for i in range(n_delay):
            C[:, i * nu : (i + 1) * nu] = G[i + 1]

        return (A, B, C, D)

    # ── ERA / Ho-Kalman realisation ──────────────────────────────────
    @staticmethod
    def _era_realisation(
        G: FIRRepr, N: int, ny: int, nu: int, order: int
    ) -> SSRepr:
        """
        Eigensystem Realisation Algorithm.

        Constructs block-Hankel matrices from Markov parameters G[1:],
        performs SVD, and extracts a balanced (A, B, C, D) of dimension
        `order`.

        References
        ----------
        Juang & Pappa (1985), "An Eigensystem Realization Algorithm for
        Modal Parameter Identification and Model Reduction", AIAA J.
        """
        r = order
        c = order

        # Markov params starting from G[1] (strip direct feed-through)
        markov = G[1:]  # length N-1

        required = r + c  # indices 0..(r+c-1) in markov → G[1]..G[r+c]
        if required > len(markov):
            raise ValueError(
                f"ERA needs {required} Markov params beyond G[0], "
                f"but only {len(markov)} available"
            )

        def _block_hankel(seq: List[Mat], nrows: int, ncols: int) -> Mat:
            H = np.zeros((nrows * ny, ncols * nu))
            for i in range(nrows):
                for j in range(ncols):
                    H[i * ny : (i + 1) * ny, j * nu : (j + 1) * nu] = seq[i + j]
            return H

        H0 = _block_hankel(markov, r, c)           # H(0)
        H1 = _block_hankel(markov[1:], r, c)        # H(1) — shifted

        U, sigma, Vt = np.linalg.svd(H0, full_matrices=False)

        # Truncate to desired order
        if order > len(sigma):
            raise ValueError(
                f"Requested order {order} exceeds available singular values "
                f"({len(sigma)})"
            )

        # Condition check — warn if truncation drops significant energy
        energy_retained = np.sum(sigma[:order] ** 2) / np.sum(sigma ** 2)
        if energy_retained < 0.99:
            logger.warning(
                "ERA: retained energy = %.4f (order %d / %d SVs). "
                "Consider increasing order.",
                energy_retained, order, len(sigma),
            )

        U1 = U[:, :order]
        S1_sqrt = np.diag(np.sqrt(sigma[:order]))
        S1_sqrt_inv = np.diag(1.0 / np.sqrt(sigma[:order]))
        V1 = Vt[:order, :]

        Ob = U1 @ S1_sqrt          # Observability matrix
        Co = S1_sqrt @ V1           # Controllability matrix

        A = S1_sqrt_inv @ U1.T @ H1 @ V1.T @ S1_sqrt_inv
        B = Co[:, :nu]
        C = Ob[:ny, :]
        D = G[0].copy()

        return (A, B, C, D)

    # =================================================================
    #  TF → FIR  (via dimpulse)
    # =================================================================
    def to_fir_from_tf(self, N: int = 120) -> "ControlModel":
        """
        Compute FIR coefficients from a discrete TF using impulse response.

        Handles both SISO and MIMO transfer functions.
        """
        if self.tf is None:
            raise ValueError("TF representation not available")
        if N < 2:
            raise ValueError(f"N must be ≥ 2, got {N}")

        num, den = self.tf
        system = signal.dlti(num, den, dt=self.dt)
        t_out, y_out = signal.dimpulse(system, n=N)

        # dimpulse returns (t, [y_for_input_0, y_for_input_1, ...])
        # Each y_for_input_j is shape (N, ny)
        n_inputs = len(y_out)
        y0 = np.squeeze(y_out[0])
        if y0.ndim == 1:
            n_outputs = 1
        else:
            n_outputs = y0.shape[1] if y0.ndim == 2 else 1

        G: FIRRepr = []
        for k in range(N):
            Gk = np.zeros((n_outputs, n_inputs))
            for j in range(n_inputs):
                col = np.squeeze(y_out[j])
                if col.ndim == 1:
                    Gk[0, j] = col[k]
                else:
                    Gk[:, j] = col[k, :]
            G.append(Gk)

        out = self._clone()
        out._set_fir(G)
        logger.info("TF → FIR  (N=%d)", N)
        return out

    # =================================================================
    #  FIR → TF  (via ERA + ss2tf)
    # =================================================================
    def to_tf_from_fir(self, order: Optional[int] = None) -> "ControlModel":
        """FIR → (ERA) SS → TF.  Approximate."""
        if self.fir is None:
            raise ValueError("FIR representation not available")
        out = self.to_ss_from_fir(method="era", order=order)
        out = out.to_tf_from_ss()
        logger.info("FIR → TF  (via ERA)")
        return out

    # =================================================================
    #  Dead-time handling
    # =================================================================
    def apply_dead_time(self, delay_steps: int) -> "ControlModel":
        """
        Prepend `delay_steps` zero matrices to the FIR sequence.

        Parameters
        ----------
        delay_steps : int ≥ 0
        """
        if self.fir is None:
            raise ValueError("FIR representation not available")
        if delay_steps < 0:
            raise ValueError(f"delay_steps must be ≥ 0, got {delay_steps}")
        if delay_steps == 0:
            return self._clone()

        fir = _ensure_2d_list(self.fir)
        ny, nu = fir[0].shape
        pad = [np.zeros((ny, nu)) for _ in range(delay_steps)]
        out = self._clone()
        out._set_fir(pad + fir)
        logger.info("Dead time applied: %d steps (%.1f s)", delay_steps, delay_steps * self.dt)
        return out

    def strip_dead_time(self) -> Tuple["ControlModel", int]:
        """
        Remove leading zero matrices from the FIR sequence.

        Returns
        -------
        model : ControlModel
            New model with dead time removed.
        delay : int
            Number of zero-coefficient steps that were stripped.
        """
        if self.fir is None:
            raise ValueError("FIR representation not available")

        fir = _ensure_2d_list(self.fir)
        delay = 0
        for Gk in fir:
            if np.allclose(Gk, 0.0):
                delay += 1
            else:
                break

        if delay == len(fir):
            raise ValueError("FIR sequence is entirely zero — no dynamics to preserve")

        out = self._clone()
        out._set_fir(fir[delay:])
        logger.info("Dead time stripped: %d steps (%.1f s)", delay, delay * self.dt)
        return out, delay

    # =================================================================
    #  Steady-state gain
    # =================================================================
    def steady_state_gain(self) -> Mat:
        """
        Compute the DC (steady-state) gain matrix.

        Works from whichever representation is available,
        preferring SS → FIR → TF.
        """
        if self.ss is not None:
            A, B, C, D = self.ss
            nx = A.shape[0]
            try:
                gain = C @ np.linalg.solve(np.eye(nx) - A, B) + D
            except np.linalg.LinAlgError:
                raise ValueError(
                    "Cannot compute SS steady-state gain: (I - A) is singular "
                    "(integrating or unstable system)"
                )
            return gain

        if self.fir is not None:
            fir = _ensure_2d_list(self.fir)
            return np.sum(fir, axis=0)

        if self.tf is not None:
            num, den = self.tf
            # G(z=1) = num(1) / den(1)
            den_sum = np.sum(den)
            if np.abs(den_sum) < 1e-14:
                raise ValueError(
                    "Cannot compute TF steady-state gain: den(z=1) ≈ 0 "
                    "(integrating or unstable system)"
                )
            return np.atleast_2d(np.sum(num) / den_sum)

        raise ValueError("No representation available")

    # =================================================================
    #  Stability check
    # =================================================================
    def is_stable(self) -> bool:
        """
        Check discrete-time stability (all eigenvalues of A inside unit circle).

        Requires SS representation (converts from TF if needed).
        """
        if self.ss is None and self.tf is not None:
            tmp = self.to_ss_from_tf()
            A = tmp.ss[0]
        elif self.ss is not None:
            A = self.ss[0]
        else:
            raise ValueError("SS or TF representation required for stability check")

        if A.size == 0:
            return True  # static gain

        eigs = np.linalg.eigvals(A)
        max_mag = np.max(np.abs(eigs))
        stable = bool(max_mag < 1.0)
        logger.debug("Stability check: max |λ| = %.6f → %s", max_mag, "stable" if stable else "UNSTABLE")
        return stable

    # =================================================================
    #  FIR metrics (useful for APC diagnostics)
    # =================================================================
    def fir_settling_index(self, tol: float = 0.01) -> int:
        """
        Index at which FIR coefficients settle to within `tol` of the
        final (steady-state) gain.  Useful for choosing DMC3 model length.

        Returns the last index where |cumulative_gain - final_gain| > tol * |final_gain|.
        """
        if self.fir is None:
            raise ValueError("FIR representation not available")

        fir = _ensure_2d_list(self.fir)
        total = np.sum(fir, axis=0)
        total_norm = np.linalg.norm(total)
        if total_norm < 1e-15:
            return 0

        cumsum = np.zeros_like(total)
        last_unsettled = 0
        for k, Gk in enumerate(fir):
            cumsum = cumsum + Gk
            if np.linalg.norm(cumsum - total) > tol * total_norm:
                last_unsettled = k

        return last_unsettled

    # =================================================================
    #  Pretty printing
    # =================================================================
    def summary(self) -> str:
        """One-line summary of available representations."""
        parts = []
        if self.tf is not None:
            num, den = self.tf
            parts.append(f"TF(num_order={len(np.atleast_1d(num))-1}, den_order={len(np.atleast_1d(den))-1})")
        if self.ss is not None:
            parts.append(f"SS(nx={self.ss[0].shape[0]})")
        if self.fir is not None:
            parts.append(f"FIR(N={len(self.fir)})")
        tag = f"[{self.name}] " if self.name else ""
        dims = f"ny={self.ny}, nu={self.nu}, " if self.ny is not None else ""
        return f"{tag}{dims}dt={self.dt} | {' + '.join(parts) if parts else '(empty)'}"

    def __repr__(self) -> str:
        return f"ControlModel({self.summary()})"


# ──────────────────────────────────────────────────────────────────────
# Convenience constructors
# ──────────────────────────────────────────────────────────────────────

def from_tf(num, den, dt: float = 1.0, name: str = "") -> ControlModel:
    """Create a ControlModel from discrete transfer-function polynomials."""
    return ControlModel(tf=(num, den), dt=dt, name=name)


def from_ss(A, B, C, D, dt: float = 1.0, name: str = "") -> ControlModel:
    """Create a ControlModel from discrete state-space matrices."""
    return ControlModel(ss=(A, B, C, D), dt=dt, name=name)


def from_fir(G: Sequence, dt: float = 1.0, name: str = "") -> ControlModel:
    """Create a ControlModel from a Markov parameter sequence."""
    return ControlModel(fir=list(G), dt=dt, name=name)


def from_step_response(
    step_coeffs: Union[Sequence[float], NDArray],
    dt: float = 1.0,
    name: str = "",
) -> ControlModel:
    """
    Create a ControlModel from DMC-style step-response coefficients.

    DMC step coefficients are cumulative sums of the impulse (FIR)
    coefficients: S[k] = Σ_{i=0}^{k} G[i].

    This function converts S → G and stores the FIR.
    """
    s = np.asarray(step_coeffs, dtype=np.float64).ravel()
    if len(s) < 2:
        raise ValueError("Need at least 2 step-response coefficients")

    # G[0] = S[0],  G[k] = S[k] - S[k-1]
    g = np.diff(s, prepend=0.0)
    fir = [np.atleast_2d(gk) for gk in g]
    return ControlModel(fir=fir, dt=dt, name=name)
