"""Round-trip tests for the TF / SS / FIR conversion graph."""
from __future__ import annotations

import numpy as np
import pytest

from azeoapc.identification import (
    ControlModel, from_fir, from_ss, from_step_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _foptd_fir(gain: float, tau: float, dt: float, n: int) -> list:
    """Discrete first-order FIR coefficients for a process G/(tau*s+1).

    Discrete pole p = exp(-dt/tau). Markov parameters:
        G[0] = 0
        G[k] = gain * (1 - p) * p^(k-1)   for k >= 1
    """
    p = np.exp(-dt / tau)
    G = [np.array([[0.0]])]
    for k in range(1, n):
        G.append(np.array([[gain * (1.0 - p) * p ** (k - 1)]]))
    return G


# ---------------------------------------------------------------------------
# SS <-> FIR
# ---------------------------------------------------------------------------
def test_fir_to_ss_shift_round_trip():
    """SHIFT realisation reproduces the original FIR exactly."""
    fir = _foptd_fir(gain=2.5, tau=10.0, dt=1.0, n=30)
    m = from_fir(fir, dt=1.0)
    ss = m.to_ss_from_fir(method="shift")
    fir2 = ss.to_fir_from_ss(N=30).fir
    for k in range(30):
        np.testing.assert_allclose(fir[k], fir2[k], atol=1e-10)


def test_fir_to_ss_era_reproduces_step_response():
    """ERA reduction must preserve the steady-state gain and step shape."""
    fir = _foptd_fir(gain=2.5, tau=10.0, dt=1.0, n=60)
    m = from_fir(fir, dt=1.0)
    ss_red = m.to_ss_from_fir(method="era", order=4)
    fir_back = ss_red.to_fir_from_ss(N=60).fir

    # Steady-state gains agree (cumulative sum)
    g_orig = sum(fir)
    g_back = sum(fir_back)
    np.testing.assert_allclose(g_orig, g_back, atol=1e-2)

    # Mid-trajectory step value within ~1% of original
    s_orig = np.cumsum([fk[0, 0] for fk in fir])
    s_back = np.cumsum([fk[0, 0] for fk in fir_back])
    rel_err = np.max(np.abs(s_orig - s_back)) / np.max(np.abs(s_orig))
    assert rel_err < 0.01, f"ERA step response error too high: {rel_err}"


def test_steady_state_gain_from_ss_matches_fir_sum():
    fir = _foptd_fir(gain=3.7, tau=15.0, dt=1.0, n=80)
    m = from_fir(fir, dt=1.0)
    g_fir = m.steady_state_gain()
    ss = m.to_ss_from_fir(method="shift")
    g_ss = ss.steady_state_gain()
    # SS and FIR-sum representations must agree exactly
    np.testing.assert_allclose(g_ss, g_fir, atol=1e-8)
    # And both should be within FIR truncation of the true gain.
    # For n=80, tau=15: residual exp(-80/15) ~ 0.5%, so 3.7 * (1 - 0.005) ~ 3.68
    np.testing.assert_allclose(g_ss[0, 0], 3.7, atol=0.05)


def test_is_stable_flags_unstable_system():
    # A scaled identity with eigenvalue 1.1 -> unstable
    A = 1.1 * np.eye(2)
    B = np.eye(2)
    C = np.eye(2)
    D = np.zeros((2, 2))
    m = from_ss(A, B, C, D)
    assert not m.is_stable()


def test_is_stable_passes_stable_system():
    fir = _foptd_fir(gain=1.0, tau=5.0, dt=1.0, n=30)
    m = from_fir(fir, dt=1.0).to_ss_from_fir(method="shift")
    assert m.is_stable()


def test_step_response_constructor_inverts_diff():
    """from_step_response should round-trip through cumulative sum."""
    fir = _foptd_fir(gain=2.0, tau=8.0, dt=1.0, n=40)
    s = np.cumsum([f[0, 0] for f in fir])
    m = from_step_response(s, dt=1.0)
    fir2 = m.fir
    for k in range(40):
        assert abs(fir[k][0, 0] - fir2[k][0, 0]) < 1e-12


def test_settling_index_increases_with_tau():
    fast = from_fir(_foptd_fir(gain=1.0, tau=2.0, dt=1.0, n=80), dt=1.0)
    slow = from_fir(_foptd_fir(gain=1.0, tau=20.0, dt=1.0, n=80), dt=1.0)
    assert slow.fir_settling_index() > fast.fir_settling_index()


def test_dimension_mismatch_raises():
    fir = _foptd_fir(gain=1.0, tau=5.0, dt=1.0, n=10)
    m = from_fir(fir, dt=1.0)  # ny=1, nu=1
    # Try to set a 2x2 SS that contradicts the registered dims
    A = np.eye(3)
    B = np.zeros((3, 2))
    C = np.zeros((2, 3))
    D = np.zeros((2, 2))
    with pytest.raises(ValueError):
        m._set_ss((A, B, C, D))
