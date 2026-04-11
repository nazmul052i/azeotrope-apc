"""Tests for the model validation engine."""
from __future__ import annotations

import numpy as np
import pytest

from azeoapc.identification import (
    from_fir, identify_fir, validate_model,
)


def _foptd_simulate(u, gain, tau, dt):
    p = np.exp(-dt / tau)
    n = len(u)
    y = np.zeros(n)
    for k in range(n - 1):
        y[k + 1] = p * y[k] + gain * (1 - p) * u[k]
    return y


def _make_step_data(n, gain, tau, dt, seed=0, noise=0.0):
    rng = np.random.default_rng(seed)
    u = np.zeros(n)
    for edge, lvl in zip([100, 250, 400, 550], [1.0, 0.0, 1.0, -1.0]):
        u[edge:] = lvl
    y = _foptd_simulate(u, gain, tau, dt)
    if noise > 0:
        y = y + rng.normal(0, noise, n)
    return u.reshape(-1, 1), y.reshape(-1, 1)


def test_validate_recovers_high_r2_on_clean_data():
    """Identify on first half, validate on second half: clean -> R^2 close to 1."""
    u, y = _make_step_data(700, gain=2.0, tau=10.0, dt=1.0, noise=0.0)
    u_train, y_train = u[:400], y[:400]
    u_test, y_test = u[400:], y[400:]

    result = identify_fir(
        u_train, y_train, n_coeff=40, dt=1.0,
        method="dls", smooth="pipeline",
        detrend=False, remove_mean=False,
    )
    model = from_fir(result.fir, dt=1.0).to_ss_from_fir(method="era", order=6)

    report = validate_model(model, u_test, y_test, mode="ss",
                             cv_names=["TI201"])
    assert report.overall_r2 > 0.95, \
        f"validation R^2 {report.overall_r2} too low on clean data"
    assert len(report.metrics) == 1
    assert report.metrics[0].cv_name == "TI201"


def test_validate_fir_mode_works():
    """FIR-mode validation produces (N - n_coeff + 1) predictions with warmup."""
    u, y = _make_step_data(500, gain=1.5, tau=5.0, dt=1.0)
    result = identify_fir(
        u, y, n_coeff=30, dt=1.0, smooth="none",
        detrend=False, remove_mean=False,
    )
    model = from_fir(result.fir, dt=1.0)

    report = validate_model(model, u, y, mode="fir")
    assert report.n_warmup == 30 - 1
    assert report.y_pred.shape[0] == len(u) - (30 - 1)
    assert report.overall_r2 > 0.9


def test_validate_auto_picks_ss_when_available():
    """When the model has an SS realisation, mode='auto' should use it.

    For a SISO FOPTD the true order is 1, so we use order=2 (safely
    above true rank, comfortably inside ERA's energy budget).
    """
    u, y = _make_step_data(700, gain=1.0, tau=5.0, dt=1.0)
    result = identify_fir(u, y, n_coeff=40, dt=1.0, smooth="none",
                           detrend=False, remove_mean=False)
    model = from_fir(result.fir, dt=1.0).to_ss_from_fir(method="era", order=2)
    assert model.is_stable(), "ERA realisation should be stable at true order"
    report = validate_model(model, u, y, mode="auto")
    assert report.mode == "ss"
    assert report.n_warmup == 0
    assert report.overall_r2 > 0.95


def test_validate_handles_divergent_model_gracefully():
    """An unstable A matrix shouldn't crash validation -- it should
    return finite sentinel metrics so the GUI can flag the failure."""
    # Construct a deliberately unstable SS model: A with eigenvalue > 1
    from azeoapc.identification import from_ss
    A = np.array([[1.5]])
    B = np.array([[1.0]])
    C = np.array([[1.0]])
    D = np.array([[0.0]])
    bad_model = from_ss(A, B, C, D, dt=1.0)

    u, y = _make_step_data(300, gain=1.0, tau=5.0, dt=1.0)
    report = validate_model(bad_model, u, y, mode="ss")
    # The model diverges -> the channel is marked failed (R^2 = -inf)
    # Validation should not raise.
    assert len(report.metrics) == 1
    assert not np.isfinite(report.metrics[0].r_squared) or report.metrics[0].r_squared < 0


def test_per_channel_metrics_populated():
    # 2 CV synthetic
    n = 600
    u = np.zeros((n, 1))
    u[100:300, 0] = 1.0
    u[400:, 0] = -0.5
    y1 = _foptd_simulate(u[:, 0], 2.0, 10.0, 1.0)
    y2 = _foptd_simulate(u[:, 0], -1.5, 8.0, 1.0)
    y = np.column_stack([y1, y2])

    result = identify_fir(u, y, n_coeff=30, dt=1.0, smooth="pipeline",
                           detrend=False, remove_mean=False)
    model = from_fir(result.fir, dt=1.0).to_ss_from_fir(method="era", order=6)
    report = validate_model(model, u, y, cv_names=["A", "B"])
    assert len(report.metrics) == 2
    assert report.metrics[0].cv_name == "A"
    assert report.metrics[1].cv_name == "B"
    for m in report.metrics:
        assert m.r_squared > 0.95
        assert m.rmse >= 0
        assert 0 <= m.nrmse < 1


# ---------------------------------------------------------------------------
# C5.1: dual-mode validation
# ---------------------------------------------------------------------------
def test_dual_mode_validation_returns_both_reports():
    """``validate_model_dual`` runs SS and FIR backends in one call.

    On a clean SISO FOPTD step test, one-step-ahead should land near
    perfect (it is the loss FIR identification minimises) while
    open-loop is honestly lower because state evolves freely. The gap
    between them is exactly what the validation tab needs to surface.
    """
    from azeoapc.identification import validate_model_dual

    u, y = _make_step_data(800, gain=2.0, tau=8.0, dt=1.0, noise=0.01)
    result = identify_fir(
        u, y, n_coeff=40, dt=1.0, smooth="pipeline",
        detrend=False, remove_mean=False,
    )
    model = from_fir(result.fir, dt=1.0).to_ss_from_fir(method="era", order=2)

    dual = validate_model_dual(model, u, y, cv_names=["TI201"])
    assert dual.open_loop.mode == "ss"
    assert dual.one_step.mode == "fir"
    # One-step is essentially exact on this synthetic data
    assert dual.one_step.overall_r2 > 0.99
    # Open-loop is honestly worse because state drifts -- but still positive
    assert dual.open_loop.overall_r2 > 0.5
    # And open-loop should always be <= one-step
    assert dual.open_loop.overall_r2 <= dual.one_step.overall_r2
    # The one-step warmup is n_coeff - 1 because we need a full window
    assert dual.one_step.n_warmup == 39
    # Excitation diagnostic populated
    assert len(dual.excitation) == 1
    assert dual.is_window_excited


def test_dual_validation_requires_both_representations():
    """Dual mode should raise if either SS or FIR is missing."""
    from azeoapc.identification import from_ss, validate_model_dual

    A = 0.9 * np.eye(2)
    B = np.eye(2)[:, :1]
    C = np.eye(2)[:1, :]
    D = np.zeros((1, 1))
    ss_only = from_ss(A, B, C, D, dt=1.0)

    u, y = _make_step_data(200, gain=1.0, tau=5.0, dt=1.0)
    with pytest.raises(ValueError, match="FIR representation"):
        validate_model_dual(ss_only, u, y)


# ---------------------------------------------------------------------------
# C5.3: excitation detector
# ---------------------------------------------------------------------------
def test_excitation_detector_flags_quiet_input():
    from azeoapc.identification import compute_excitation

    n = 300
    # Two MVs: one moves a lot, one is stuck at a constant 100
    moving = np.zeros(n)
    moving[100:200] = 1.0
    stuck = np.full(n, 100.0)
    u = np.column_stack([moving, stuck])

    diag = compute_excitation(u, mv_names=["FIC101", "FIC102"])
    assert len(diag) == 2
    assert diag[0].mv_name == "FIC101"
    assert diag[0].is_excited            # std = ~0.5, mean ~0.33 -> rel >> 0.005
    assert not diag[1].is_excited        # std = 0, range = 0
    assert diag[1].std == 0.0


def test_excitation_detector_handles_zero_mean_inputs():
    from azeoapc.identification import compute_excitation

    n = 300
    rng = np.random.default_rng(0)
    u = rng.normal(0, 1, size=(n, 1))    # zero mean, unit std

    diag = compute_excitation(u)
    assert diag[0].is_excited            # absolute-std fallback kicks in


def test_excitation_window_excited_helper():
    from azeoapc.identification import (
        ExcitationDiagnostic, compute_excitation,
    )

    # All MVs quiet -> not excited
    u = np.full((200, 2), 50.0)
    diag = compute_excitation(u)
    assert not ExcitationDiagnostic.is_window_excited(diag)

    # One MV moving -> excited
    u[:, 0] += np.linspace(0, 5, 200)
    diag = compute_excitation(u)
    assert ExcitationDiagnostic.is_window_excited(diag)
