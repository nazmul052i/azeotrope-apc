"""Model uncertainty analysis for identified step-response models.

Provides frequency-domain and time-domain uncertainty estimation with
DMC3-style A/B/C/D grading.

Frequency domain
----------------
For each MV-CV pair, compute the Bode magnitude of the identified
FIR model and overlay ±1σ / ±2σ confidence bands derived from the
parameter covariance matrix.

Time domain
-----------
Propagate parameter uncertainty through the step-response to get
time-domain confidence envelopes.

Grading
-------
=====  ====================  =====================
Grade  Steady-State Uncert.  Dynamic Uncertainty
=====  ====================  =====================
A      < 10% of gain         < 20% of gain
B      10-25%                20-50%
C      25-50%                50-100%
D      > 50%                 > 100%
=====  ====================  =====================

Usage::

    report = analyze_uncertainty(step, confidence, n_coeff, dt)
    print(report.summary())
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
def _grade_uncertainty(ratio: float) -> str:
    if ratio < 0.10:
        return "A"
    elif ratio < 0.25:
        return "B"
    elif ratio < 0.50:
        return "C"
    else:
        return "D"


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
@dataclass
class ChannelUncertainty:
    """Uncertainty analysis for one MV-CV pair."""
    cv_idx: int
    mv_idx: int
    cv_name: str = ""
    mv_name: str = ""

    # Frequency domain
    frequencies: Optional[np.ndarray] = None      # rad/sample
    magnitude_db: Optional[np.ndarray] = None     # dB
    magnitude_upper_2s: Optional[np.ndarray] = None
    magnitude_lower_2s: Optional[np.ndarray] = None
    magnitude_upper_1s: Optional[np.ndarray] = None
    magnitude_lower_1s: Optional[np.ndarray] = None

    # Time domain
    step_response: Optional[np.ndarray] = None
    step_upper_2s: Optional[np.ndarray] = None
    step_lower_2s: Optional[np.ndarray] = None
    step_upper_1s: Optional[np.ndarray] = None
    step_lower_1s: Optional[np.ndarray] = None

    # Grading
    ss_gain: float = 0.0
    ss_uncertainty: float = 0.0          # 2-sigma at steady state
    ss_uncertainty_pct: float = 0.0
    ss_grade: str = "D"
    dynamic_uncertainty_pct: float = 0.0  # max 2-sigma / gain over time
    dynamic_grade: str = "D"
    overall_grade: str = "D"

    # Signal-to-noise
    snr_db: float = 0.0


@dataclass
class UncertaintyReport:
    """Full uncertainty analysis for a model."""
    channels: List[ChannelUncertainty] = field(default_factory=list)
    ny: int = 0
    nu: int = 0
    cv_names: List[str] = field(default_factory=list)
    mv_names: List[str] = field(default_factory=list)

    def grade_matrix(self) -> List[List[str]]:
        """Return (ny x nu) matrix of overall grades."""
        matrix = [["D"] * self.nu for _ in range(self.ny)]
        for ch in self.channels:
            matrix[ch.cv_idx][ch.mv_idx] = ch.overall_grade
        return matrix

    def summary(self) -> str:
        lines = [f"Model Uncertainty Analysis ({self.ny} CVs x {self.nu} MVs)"]
        lines.append("  Grade matrix:")
        header = "         " + "  ".join(f"{m:>8s}" for m in self.mv_names)
        lines.append(header)
        gm = self.grade_matrix()
        for i, cv in enumerate(self.cv_names):
            row = "  ".join(f"{gm[i][j]:>8s}" for j in range(self.nu))
            lines.append(f"  {cv:>6s}: {row}")

        lines.append("")
        for ch in self.channels:
            lines.append(
                f"  {ch.cv_name}/{ch.mv_name}: SS={ch.ss_grade} "
                f"({ch.ss_uncertainty_pct:.1f}%)  "
                f"Dyn={ch.dynamic_grade} ({ch.dynamic_uncertainty_pct:.1f}%)  "
                f"SNR={ch.snr_db:.1f}dB")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------
def _fir_frequency_response(
    fir: np.ndarray,
    n_freq: int = 256,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute frequency response magnitude from FIR coefficients.

    Returns (frequencies in rad/sample, magnitude).
    """
    freqs = np.linspace(0, np.pi, n_freq, endpoint=False)
    n = len(fir)
    H = np.zeros(n_freq, dtype=complex)
    for k in range(n):
        H += fir[k] * np.exp(-1j * freqs * k)
    magnitude = np.abs(H)
    return freqs, magnitude


def _confidence_frequency_response(
    fir: np.ndarray,
    fir_std: np.ndarray,
    n_freq: int = 256,
    sigma: float = 2.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute upper and lower magnitude bounds from FIR uncertainty.

    Uses Monte Carlo-free analytical propagation:
    The variance of |H(ω)| is approximately propagated from coefficient variances.
    """
    freqs = np.linspace(0, np.pi, n_freq, endpoint=False)
    n = len(fir)

    H = np.zeros(n_freq, dtype=complex)
    H_var = np.zeros(n_freq)

    for k in range(n):
        basis = np.exp(-1j * freqs * k)
        H += fir[k] * basis
        # Variance contribution: |basis|² * var(fir[k]) = var(fir[k])
        H_var += fir_std[k] ** 2

    magnitude = np.abs(H)
    # Approximate: std(|H|) ≈ sqrt(H_var) (for real-dominated signals)
    mag_std = np.sqrt(H_var)

    upper = magnitude + sigma * mag_std
    lower = np.maximum(magnitude - sigma * mag_std, 0.0)
    return upper, lower


def analyze_uncertainty(
    step_response: np.ndarray,
    confidence_lo: Optional[np.ndarray] = None,
    confidence_hi: Optional[np.ndarray] = None,
    n_coeff: Optional[int] = None,
    dt: float = 1.0,
    cv_names: Optional[List[str]] = None,
    mv_names: Optional[List[str]] = None,
    residual_std: Optional[np.ndarray] = None,
) -> UncertaintyReport:
    """Run full uncertainty analysis on an identified model.

    Parameters
    ----------
    step_response : ndarray, shape (ny, n_coeff, nu)
        Cumulative step response matrix.
    confidence_lo, confidence_hi : ndarray, optional
        Lower/upper confidence bounds (same shape as step_response).
        If not provided, uses residual_std to estimate.
    dt : float
        Sample period (seconds).
    cv_names, mv_names : list[str], optional
        Variable names for reporting.
    residual_std : ndarray, optional
        Per-CV residual standard deviation for uncertainty estimation.
    """
    if step_response.ndim == 1:
        step_response = step_response.reshape(1, -1, 1)
    elif step_response.ndim == 2:
        step_response = step_response.reshape(1, step_response.shape[0],
                                               step_response.shape[1])

    ny, nc, nu = step_response.shape
    if n_coeff is None:
        n_coeff = nc

    if cv_names is None:
        cv_names = [f"CV{i}" for i in range(ny)]
    if mv_names is None:
        mv_names = [f"MV{j}" for j in range(nu)]

    # Estimate confidence bands if not provided
    if confidence_lo is None or confidence_hi is None:
        if residual_std is not None:
            # Simple heuristic: uncertainty grows with sqrt(k)
            confidence_lo = np.zeros_like(step_response)
            confidence_hi = np.zeros_like(step_response)
            for i in range(ny):
                for j in range(nu):
                    k = np.arange(nc)
                    band = 2.0 * residual_std[i] * np.sqrt(k + 1) / np.sqrt(nc)
                    confidence_lo[i, :, j] = step_response[i, :, j] - band
                    confidence_hi[i, :, j] = step_response[i, :, j] + band
        else:
            # No uncertainty info -- assume 10% of final gain
            confidence_lo = step_response * 0.9
            confidence_hi = step_response * 1.1

    channels: List[ChannelUncertainty] = []

    for i in range(ny):
        for j in range(nu):
            step = step_response[i, :, j]
            lo = confidence_lo[i, :, j]
            hi = confidence_hi[i, :, j]

            # FIR = diff of step response
            fir = np.diff(step, prepend=0.0)
            fir_half_width = (hi - lo) / 2.0
            fir_std = np.maximum(np.diff(fir_half_width, prepend=0.0), 1e-15)

            # Frequency response
            freqs, mag = _fir_frequency_response(fir)
            mag_upper_2s, mag_lower_2s = _confidence_frequency_response(
                fir, fir_std, sigma=2.0)
            mag_upper_1s, mag_lower_1s = _confidence_frequency_response(
                fir, fir_std, sigma=1.0)

            # Convert to dB
            eps = 1e-15
            mag_db = 20.0 * np.log10(mag + eps)

            # Steady-state analysis
            ss_gain = float(step[-1])
            ss_lo = float(lo[-1])
            ss_hi = float(hi[-1])
            ss_uncertainty = (ss_hi - ss_lo) / 2.0

            if abs(ss_gain) > 1e-15:
                ss_pct = abs(ss_uncertainty / ss_gain) * 100.0
            else:
                ss_pct = 0.0

            # Dynamic uncertainty: max relative 2-sigma band
            band_width = hi - lo
            if abs(ss_gain) > 1e-15:
                dyn_pct = float(np.max(band_width) / abs(ss_gain)) * 100.0
            else:
                dyn_pct = 0.0

            # Signal-to-noise ratio
            signal_power = np.mean(step ** 2)
            noise_power = np.mean(fir_half_width ** 2)
            snr = 10.0 * np.log10(signal_power / max(noise_power, eps))

            ch = ChannelUncertainty(
                cv_idx=i, mv_idx=j,
                cv_name=cv_names[i], mv_name=mv_names[j],
                frequencies=freqs,
                magnitude_db=mag_db,
                magnitude_upper_2s=20.0 * np.log10(mag_upper_2s + eps),
                magnitude_lower_2s=20.0 * np.log10(mag_lower_2s + eps),
                magnitude_upper_1s=20.0 * np.log10(mag_upper_1s + eps),
                magnitude_lower_1s=20.0 * np.log10(mag_lower_1s + eps),
                step_response=step,
                step_upper_2s=hi,
                step_lower_2s=lo,
                step_upper_1s=step + fir_half_width / 2,
                step_lower_1s=step - fir_half_width / 2,
                ss_gain=ss_gain,
                ss_uncertainty=ss_uncertainty,
                ss_uncertainty_pct=ss_pct,
                ss_grade=_grade_uncertainty(ss_pct / 100.0),
                dynamic_uncertainty_pct=dyn_pct,
                dynamic_grade=_grade_uncertainty(dyn_pct / 100.0),
                overall_grade=_grade_uncertainty(max(ss_pct, dyn_pct) / 100.0),
                snr_db=snr,
            )
            channels.append(ch)

    return UncertaintyReport(
        channels=channels,
        ny=ny, nu=nu,
        cv_names=cv_names,
        mv_names=mv_names,
    )
