"""Open-loop validation of an identified model on hold-out test data.

The Validation tab in apc_ident calls ``validate_model`` to ask:

  "Given an identified ControlModel and a chunk of plant data the
   identifier never saw, how well does the model predict the plant?"

This is the gate before exporting a bundle for use in apc_architect --
if the validation fit is poor, the model isn't ready for the controller.

Two simulation modes:

  * ``mode="ss"``  -- if the model has a state-space representation,
                     simulate ``x[k+1] = A x[k] + B u[k]`` directly.
                     Initial state x[0] = 0; we shift the predicted
                     trajectory to match the test mean so absolute
                     biases don't dominate the metrics.

  * ``mode="fir"`` -- otherwise, convolve the FIR with the input history.
                     Each predicted output is the sum over the FIR window
                     of past inputs.

The returned ``ValidationReport`` carries everything the GUI needs to
plot actual-vs-predicted and tabulate metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

import numpy as np

from .control_model import ControlModel


@dataclass
class ChannelMetric:
    """Per-CV fit metrics on a hold-out window."""
    cv_index: int
    cv_name: str = ""
    r_squared: float = 0.0
    rmse: float = 0.0
    nrmse: float = 0.0          # rmse / range(y_test)
    bias: float = 0.0           # mean(y_pred - y_test)
    max_abs_error: float = 0.0


@dataclass
class ValidationReport:
    """Output of ``validate_model``.

    ``y_pred`` is shape (N, ny) and aligned with ``y_test``. The first
    few samples may be trimmed when using FIR mode (because we need
    n_coeff history); use ``n_warmup`` to know how many.
    """
    y_pred: np.ndarray
    y_test: np.ndarray
    residuals: np.ndarray
    metrics: List[ChannelMetric]
    mode: str = "ss"
    n_warmup: int = 0
    cv_names: List[str] = field(default_factory=list)
    mv_names: List[str] = field(default_factory=list)

    @property
    def overall_r2(self) -> float:
        """Mean R² across CVs (simple average)."""
        if not self.metrics:
            return 0.0
        return float(np.mean([m.r_squared for m in self.metrics]))

    def summary(self) -> str:
        lines = [
            f"Validation report ({self.mode} mode)",
            f"  samples       : {len(self.y_test)}  (warmup {self.n_warmup})",
            f"  overall R^2   : {self.overall_r2:.4f}",
            f"  per CV:",
        ]
        for m in self.metrics:
            name = m.cv_name or f"CV{m.cv_index}"
            lines.append(
                f"    {name:24s}  R^2={m.r_squared:+.4f}  "
                f"RMSE={m.rmse:.4g}  NRMSE={m.nrmse:.4f}  "
                f"bias={m.bias:+.4g}"
            )
        return "\n".join(lines)


@dataclass
class ExcitationDiagnostic:
    """Per-MV signal diagnostics for a validation window.

    The validation tab uses these to warn the user when the test data
    contains too little MV movement to give meaningful metrics --
    "R^2 of pure noise" is the most common silent failure mode.
    """
    mv_index: int
    mv_name: str = ""
    std: float = 0.0              # absolute std of the test input
    relative_std: float = 0.0     # std / |mean|, dimensionless
    range: float = 0.0            # max - min over the window
    is_excited: bool = True       # False -> warn the user

    @staticmethod
    def is_window_excited(diags: List["ExcitationDiagnostic"]) -> bool:
        """True if at least ONE MV had real movement during the window."""
        return any(d.is_excited for d in diags)


# ---------------------------------------------------------------------------
# Excitation detector
# ---------------------------------------------------------------------------
def compute_excitation(
    u_test: np.ndarray,
    *,
    mv_names: Optional[List[str]] = None,
    rel_std_threshold: float = 0.005,
    abs_std_threshold: float = 1e-9,
) -> List[ExcitationDiagnostic]:
    """Diagnose how much each MV moved during the test window.

    A channel is "excited" if either its relative std (std / |mean|)
    exceeds ``rel_std_threshold`` OR its absolute std exceeds
    ``abs_std_threshold``. The dual threshold handles MVs centred near
    zero (where the relative measure is meaningless) as well as MVs
    sitting on a non-zero engineering operating point.
    """
    u = np.atleast_2d(np.asarray(u_test, dtype=np.float64))
    n, nu = u.shape
    out: List[ExcitationDiagnostic] = []
    for j in range(nu):
        col = u[:, j]
        std = float(np.std(col))
        mean = float(np.abs(np.mean(col)))
        rel = std / mean if mean > 1e-12 else float("inf") if std > 0 else 0.0
        rng = float(col.max() - col.min())
        excited = (rel >= rel_std_threshold) or (std >= abs_std_threshold and mean < 1e-12)
        name = mv_names[j] if mv_names and j < len(mv_names) else f"MV{j}"
        out.append(ExcitationDiagnostic(
            mv_index=j, mv_name=name,
            std=std, relative_std=rel, range=rng,
            is_excited=excited,
        ))
    return out


@dataclass
class DualValidationReport:
    """Result of ``validate_model_dual`` -- both prediction modes side by side.

    Engineers want to see both numbers in production: open-loop is the
    honest predictor (matches what the controller does internally) but
    is the harsher score; one-step-ahead is the loss the identifier
    optimised against and tells you how well the model matches the data
    sample-by-sample. Big gap between them means model dynamics drift
    over the prediction horizon.
    """
    open_loop: ValidationReport
    one_step: ValidationReport
    excitation: List[ExcitationDiagnostic]

    @property
    def is_window_excited(self) -> bool:
        return ExcitationDiagnostic.is_window_excited(self.excitation)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def validate_model(
    model: ControlModel,
    u_test: np.ndarray,
    y_test: np.ndarray,
    *,
    mode: Literal["auto", "ss", "fir"] = "auto",
    cv_names: Optional[List[str]] = None,
    mv_names: Optional[List[str]] = None,
    align_means: bool = True,
) -> ValidationReport:
    """Simulate ``model`` on ``u_test`` and compare to ``y_test``.

    Parameters
    ----------
    model : ControlModel
        Identified model. Must carry a state-space or FIR representation.
    u_test : array (N, nu)
        Hold-out input trajectory.
    y_test : array (N, ny)
        Hold-out measured output trajectory.
    mode : {"auto", "ss", "fir"}
        ``"auto"`` picks SS if available, else FIR. SS is faster and
        does not need warmup samples.
    align_means : bool
        If True, shift ``y_pred`` so its mean equals ``y_test``'s mean
        before computing metrics. This makes the report focus on
        dynamics rather than absolute bias (relevant when the model
        was identified on detrended/mean-removed data).
    """
    u = np.atleast_2d(np.asarray(u_test, dtype=np.float64))
    y = np.atleast_2d(np.asarray(y_test, dtype=np.float64))
    if u.shape[0] != y.shape[0]:
        raise ValueError(f"u_test rows {u.shape[0]} != y_test rows {y.shape[0]}")

    if mode == "auto":
        mode = "ss" if model.ss is not None else "fir"

    if mode == "ss":
        if model.ss is None:
            raise ValueError("validate_model(mode='ss') needs an SS representation")
        y_pred, n_warmup = _simulate_ss(model.ss, u, y.shape[1])
    elif mode == "fir":
        if model.fir is None:
            raise ValueError("validate_model(mode='fir') needs a FIR representation")
        y_pred, n_warmup = _simulate_fir(model.fir, u, y.shape[1])
    else:
        raise ValueError(f"unknown mode: {mode}")

    # Detect divergent simulations early -- a numerically unstable A
    # matrix (e.g. from a marginal ERA realisation) can blow predictions
    # to +/- inf and poison the downstream metrics. We don't try to "fix"
    # the predictions; we just record the divergence and return finite
    # but obviously-bad metrics.
    finite = np.isfinite(y_pred).all()

    if align_means and y_pred.shape[0] > 0 and finite:
        y_compare = y[n_warmup:]
        shift = y_compare.mean(axis=0) - y_pred.mean(axis=0)
        y_pred = y_pred + shift

    y_compare = y[n_warmup:]
    residuals = y_compare - y_pred
    metrics = _compute_metrics(y_compare, y_pred, residuals,
                                cv_names=cv_names)

    return ValidationReport(
        y_pred=y_pred,
        y_test=y_compare,
        residuals=residuals,
        metrics=metrics,
        mode=mode,
        n_warmup=n_warmup,
        cv_names=cv_names or [],
        mv_names=mv_names or [],
    )


# ---------------------------------------------------------------------------
# Dual-mode validation
# ---------------------------------------------------------------------------
def validate_model_dual(
    model: ControlModel,
    u_test: np.ndarray,
    y_test: np.ndarray,
    *,
    cv_names: Optional[List[str]] = None,
    mv_names: Optional[List[str]] = None,
    align_means: bool = True,
) -> DualValidationReport:
    """Run BOTH open-loop multi-step prediction AND one-step-ahead
    prediction in one call, plus an excitation diagnostic for the test
    window. The validation tab uses this to display both numbers side
    by side and warn when the test data has too little MV movement.

    The model must carry both an SS realisation (for open-loop) and a
    FIR sequence (for one-step). The default builder ``bundle_from_ident``
    produces both, so any bundle round-tripped through apc_ident will
    work here.

    The "open-loop" mode is the same as ``mode='ss'`` -- pure multi-step
    prediction with a steady-state warm start. The "one-step" mode is
    the same as ``mode='fir'`` -- a sliding window over the n_coeff
    most recent real inputs, which is exactly what FIR identification
    minimises in its loss function. Together they bracket how the model
    behaves between "predict the next sample" and "predict freely from
    here on out".
    """
    if model.ss is None:
        raise ValueError("validate_model_dual requires an SS representation")
    if model.fir is None:
        raise ValueError("validate_model_dual requires a FIR representation")

    open_loop = validate_model(
        model, u_test, y_test, mode="ss",
        cv_names=cv_names, mv_names=mv_names, align_means=align_means)
    one_step = validate_model(
        model, u_test, y_test, mode="fir",
        cv_names=cv_names, mv_names=mv_names, align_means=align_means)
    excitation = compute_excitation(u_test, mv_names=mv_names)
    return DualValidationReport(
        open_loop=open_loop,
        one_step=one_step,
        excitation=excitation,
    )


# ---------------------------------------------------------------------------
# Simulation backends
# ---------------------------------------------------------------------------
def _simulate_ss(ss, u, ny):
    """Simulate the SS model with a steady-state warm start.

    The state is initialised to ``x_ss = (I - A)^-1 B u_mean`` so the
    first prediction sits at the model's equilibrium for the test
    input mean. This eliminates the long transient that otherwise
    pollutes per-sample metrics when validation is run on data that
    sits well away from the model's deviation-zero operating point
    (e.g. engineering-unit data with mean ~100).

    If (I - A) is singular (integrating modes) we fall back to a zero
    initial state and warn via the returned ``n_warmup`` field, which
    the caller can use to discard the early samples from metrics.
    """
    A, B, C, D = ss
    nx = A.shape[0]
    n = u.shape[0]
    y_pred = np.zeros((n, ny))
    if nx == 0:
        for k in range(n):
            y_pred[k] = D @ u[k]
        return y_pred, 0

    u_mean = u.mean(axis=0)
    try:
        x = np.linalg.solve(np.eye(nx) - A, B @ u_mean)
        n_warmup = 0
    except np.linalg.LinAlgError:
        x = np.zeros(nx)
        # Warm up empirically: feed the model 5*nx samples at u_mean to
        # settle the state without scoring those samples.
        warm = min(5 * nx, n)
        for _ in range(warm):
            x = A @ x + B @ u_mean
        n_warmup = warm

    for k in range(n):
        y_pred[k] = C @ x + D @ u[k]
        x = A @ x + B @ u[k]
    return y_pred, n_warmup


def _simulate_fir(fir, u, ny):
    """Convolve the FIR with the input history.

    y[k] = sum_{i=0..n-1} G[i] @ u[k-i]

    The first ``n_coeff - 1`` predictions are not produced because we
    need a full window of past inputs.
    """
    n_coeff = len(fir)
    n = u.shape[0]
    if n < n_coeff:
        raise ValueError(
            f"FIR validation needs >= n_coeff={n_coeff} samples, got {n}")
    n_out = n - n_coeff + 1
    y_pred = np.zeros((n_out, ny))
    for k in range(n_out):
        acc = np.zeros(ny)
        for i in range(n_coeff):
            acc += fir[i] @ u[k + n_coeff - 1 - i]
        y_pred[k] = acc
    return y_pred, n_coeff - 1


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _compute_metrics(
    y_test: np.ndarray, y_pred: np.ndarray, residuals: np.ndarray,
    *, cv_names: Optional[List[str]] = None,
) -> List[ChannelMetric]:
    """Per-channel metrics. Suppresses overflow/invalid warnings from
    pathological inputs (e.g. divergent simulations) and returns finite
    sentinel values (R^2 = -inf, RMSE = inf) so the GUI can flag the
    channel as failed without raising."""
    n, ny = y_test.shape
    metrics: List[ChannelMetric] = []
    with np.errstate(over="ignore", invalid="ignore"):
        for j in range(ny):
            y_j = y_test[:, j]
            r_j = residuals[:, j]
            yp_j = y_pred[:, j]

            if not (np.isfinite(yp_j).all() and np.isfinite(r_j).all()):
                # Divergent prediction -- mark the channel as failed
                metrics.append(ChannelMetric(
                    cv_index=j,
                    cv_name=(cv_names[j] if cv_names and j < len(cv_names) else ""),
                    r_squared=float("-inf"),
                    rmse=float("inf"),
                    nrmse=float("inf"),
                    bias=float("nan"),
                    max_abs_error=float("inf"),
                ))
                continue

            ss_res = float(np.sum(r_j ** 2))
            ss_tot = float(np.sum((y_j - y_j.mean()) ** 2))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0
            rmse = float(np.sqrt(np.mean(r_j ** 2)))
            rng = float(y_j.max() - y_j.min())
            nrmse = rmse / rng if rng > 1e-15 else 0.0
            bias = float(np.mean(yp_j - y_j))
            max_abs = float(np.max(np.abs(r_j))) if len(r_j) else 0.0
            name = cv_names[j] if cv_names and j < len(cv_names) else ""
            metrics.append(ChannelMetric(
                cv_index=j, cv_name=name, r_squared=r2, rmse=rmse,
                nrmse=nrmse, bias=bias, max_abs_error=max_abs,
            ))
    return metrics
