"""End-to-end FIR identification on a synthetic FOPTD plant.

We generate a clean step-test by simulating a known FOPTD model in
discrete time, then call ``identify_fir`` and verify the recovered
gain matrix and settling time match the truth.
"""
from __future__ import annotations

import numpy as np
import pytest

from azeoapc.identification import (
    FIRIdentifier, IdentConfig, IdentMethod, SmoothMethod, identify_fir,
)


# ---------------------------------------------------------------------------
# Synthetic plant simulator
# ---------------------------------------------------------------------------
def _simulate_foptd(u: np.ndarray, gain: float, tau: float, dt: float) -> np.ndarray:
    """One-input one-output FOPTD discrete simulation.

    y[k+1] = p*y[k] + gain*(1-p)*u[k]   with p = exp(-dt/tau)
    """
    p = np.exp(-dt / tau)
    n = len(u)
    y = np.zeros(n)
    for k in range(n - 1):
        y[k + 1] = p * y[k] + gain * (1 - p) * u[k]
    return y


def _make_step_test(
    n_samples: int, gain: float, tau: float, dt: float, noise_std: float = 0.0,
    seed: int = 0,
) -> tuple:
    """A multi-step test: rest -> +1 -> +0 -> +1 -> -1 -> 0."""
    rng = np.random.default_rng(seed)
    u = np.zeros(n_samples)
    edges = np.linspace(50, n_samples - 50, 5).astype(int)
    levels = [1.0, 0.0, 1.0, -1.0, 0.0]
    for e, lvl in zip(edges, levels):
        u[e:] = lvl
    y = _simulate_foptd(u, gain=gain, tau=tau, dt=dt)
    if noise_std > 0:
        y = y + rng.normal(0.0, noise_std, size=n_samples)
    return u.reshape(-1, 1), y.reshape(-1, 1)


# ---------------------------------------------------------------------------
# DLS recovers a clean step test
# ---------------------------------------------------------------------------
def test_dls_recovers_foptd_gain_clean():
    u, y = _make_step_test(n_samples=600, gain=2.5, tau=8.0, dt=1.0,
                            noise_std=0.0)
    result = identify_fir(
        u, y, n_coeff=40, dt=1.0, method="dls", smooth="none",
        detrend=False, remove_mean=False,
    )
    g = result.gain_matrix()
    assert g.shape == (1, 1)
    assert abs(g[0, 0] - 2.5) < 0.1, f"gain {g[0,0]} != 2.5"


def test_dls_recovers_foptd_gain_with_noise():
    u, y = _make_step_test(n_samples=900, gain=1.8, tau=12.0, dt=1.0,
                            noise_std=0.02, seed=42)
    result = identify_fir(
        u, y, n_coeff=60, dt=1.0, method="dls", smooth="pipeline",
        detrend=False, remove_mean=False,
    )
    g = result.gain_matrix()
    assert abs(g[0, 0] - 1.8) < 0.15, f"gain {g[0,0]} != 1.8 (noisy)"
    # R^2 should be high for clean SISO recovery
    assert result.fits[0].r_squared > 0.95


def test_ridge_handles_collinear_inputs():
    """Two MVs that move together: ridge regularises the redundancy.

    With u2 ~ u1 and the true plant y = G*(u1+u2) = 2G*u1, the model
    is unidentifiable from this data alone -- any (g1,g2) with
    g1+g2 ~ 2G fits equally well. Ridge picks the minimum-norm
    solution, which splits the gain evenly: g1 ~ g2 ~ G, sum ~ 2G.
    """
    rng = np.random.default_rng(0)
    n = 600
    G_true = 2.0
    u1 = np.zeros(n)
    u1[100:] = 1.0
    u1[300:] = 0.0
    u1[450:] = 1.0
    u2 = u1 + 0.01 * rng.normal(size=n)  # nearly identical to u1
    u = np.column_stack([u1, u2])

    y = _simulate_foptd(u1 + u2, gain=G_true, tau=10.0, dt=1.0)
    y = y.reshape(-1, 1)

    result = identify_fir(
        u, y, n_coeff=40, dt=1.0, method="ridge", smooth="pipeline",
        ridge_alpha=1.0, detrend=False, remove_mean=False,
    )
    g = result.gain_matrix()
    # Sum of the two channel gains should be ~ 2*G_true (= 4.0)
    assert abs(g.sum() - 2 * G_true) < 0.4, \
        f"gain sum {g.sum()} != ~{2 * G_true}"
    # And ridge should split roughly equally
    assert abs(g[0, 0] - g[0, 1]) < 0.3, \
        f"ridge split unbalanced: {g[0, 0]} vs {g[0, 1]}"


def test_ident_result_has_consistent_shapes():
    u, y = _make_step_test(n_samples=400, gain=1.0, tau=5.0, dt=1.0)
    result = identify_fir(u, y, n_coeff=30, dt=1.0)
    assert result.ny == 1
    assert result.nu == 1
    assert result.n_coeff == 30
    assert len(result.fir) == 30
    assert len(result.step) == 30
    assert len(result.confidence_lo) == 30
    assert len(result.confidence_hi) == 30
    assert result.condition_number > 0


def test_settling_index_per_channel():
    u, y = _make_step_test(n_samples=600, gain=2.5, tau=10.0, dt=1.0)
    result = identify_fir(u, y, n_coeff=80, dt=1.0)
    si = result.settling_index(tol=0.02)
    assert si.shape == (1, 1)
    # tau=10 with 1s sampling settles within ~5*tau samples
    assert 20 < si[0, 0] < 70


def test_insufficient_data_raises():
    u = np.zeros((30, 1))
    y = np.zeros((30, 1))
    with pytest.raises(ValueError, match="Insufficient data"):
        identify_fir(u, y, n_coeff=60, dt=1.0)
