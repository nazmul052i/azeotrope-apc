"""Round-trip tests for the .apcmodel HDF5 bundle format."""
from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from azeoapc.identification import (
    bundle_from_ident, identify_fir, load_model_bundle, save_model_bundle,
    ModelBundle, validate_model,
)


# ---------------------------------------------------------------------------
# Helper: build a synthetic IdentResult
# ---------------------------------------------------------------------------
def _make_synthetic_result(seed: int = 0):
    """Synthesize a 2x2 step test and identify it."""
    rng = np.random.default_rng(seed)
    n = 800

    mv1 = np.zeros(n)
    mv1[100:300] = 1.0
    mv1[500:700] = -0.5
    mv2 = np.zeros(n)
    mv2[200:500] = 0.6
    mv2[600:] = -0.3
    u = np.column_stack([mv1, mv2])

    def foptd(x, gain, tau):
        p = np.exp(-1.0 / tau)
        y = np.zeros(len(x))
        for k in range(len(x) - 1):
            y[k + 1] = p * y[k] + gain * (1 - p) * x[k]
        return y

    cv1 = foptd(mv1, 2.0, 8.0) + foptd(mv2, 1.0, 6.0)
    cv2 = foptd(mv1, -1.5, 12.0) + foptd(mv2, 2.0, 10.0)
    cv1 += 0.02 * rng.normal(size=n)
    cv2 += 0.02 * rng.normal(size=n)
    y = np.column_stack([cv1, cv2])

    return identify_fir(
        u, y, n_coeff=40, dt=60.0, method="dls", smooth="pipeline",
        detrend=False, remove_mean=False,
    )


# ---------------------------------------------------------------------------
# bundle_from_ident
# ---------------------------------------------------------------------------
def test_bundle_from_ident_populates_all_fields():
    result = _make_synthetic_result()
    bundle = bundle_from_ident(
        result, name="Test Bundle",
        mv_tags=["FIC-101.SP", "FIC-102.SP"],
        cv_tags=["TI-201.PV", "TI-202.PV"],
        source_csv="step_test.csv",
        source_project="test.apcident",
    )
    assert bundle.name == "Test Bundle"
    assert bundle.dt == 60.0
    assert bundle.ny == 2
    assert bundle.nu == 2
    assert bundle.n_coeff == 40
    assert bundle.fir.shape == (2, 40, 2)
    assert bundle.confidence_lo.shape == (2, 40, 2)
    assert bundle.confidence_hi.shape == (2, 40, 2)
    assert bundle.step.shape == (2, 40, 2)
    assert bundle.gain_matrix.shape == (2, 2)
    assert bundle.settling_index.shape == (2, 2)
    # State-space realisation populated via ERA
    assert bundle.A is not None
    assert bundle.A.shape[0] >= 1
    assert bundle.B.shape == (bundle.A.shape[0], 2)
    assert bundle.C.shape == (2, bundle.A.shape[0])
    assert bundle.D.shape == (2, 2)
    assert bundle.era_order >= 1
    # Provenance
    assert bundle.source_csv == "step_test.csv"
    assert bundle.ident_method == "dls"
    assert "channels" in bundle.fit_summary


def test_bundle_from_ident_validates_tag_count():
    result = _make_synthetic_result()
    with pytest.raises(ValueError, match="mv_tags length"):
        bundle_from_ident(result, name="x",
                          mv_tags=["only_one"], cv_tags=["a", "b"])
    with pytest.raises(ValueError, match="cv_tags length"):
        bundle_from_ident(result, name="x",
                          mv_tags=["a", "b"], cv_tags=["only_one"])


# ---------------------------------------------------------------------------
# Save / load round trip
# ---------------------------------------------------------------------------
def test_save_load_round_trip_preserves_all_fields(tmp_path):
    result = _make_synthetic_result()
    bundle = bundle_from_ident(
        result, name="Round Trip",
        mv_tags=["FIC-101.SP", "FIC-102.SP"],
        cv_tags=["TI-201.PV", "TI-202.PV"],
        dv_tags=["TI-101.PV"],
        source_csv="data.csv",
    )

    out_path = str(tmp_path / "round_trip.apcmodel")
    save_model_bundle(bundle, out_path)
    assert os.path.exists(out_path)

    loaded = load_model_bundle(out_path)
    assert loaded.name == "Round Trip"
    assert loaded.dt == 60.0
    assert loaded.mv_tags == ["FIC-101.SP", "FIC-102.SP"]
    assert loaded.cv_tags == ["TI-201.PV", "TI-202.PV"]
    assert loaded.dv_tags == ["TI-101.PV"]
    assert loaded.ident_method == "dls"
    assert loaded.ident_n_coeff == 40
    assert loaded.source_csv == "data.csv"

    np.testing.assert_allclose(loaded.fir, bundle.fir, atol=1e-12)
    np.testing.assert_allclose(loaded.confidence_lo, bundle.confidence_lo, atol=1e-12)
    np.testing.assert_allclose(loaded.confidence_hi, bundle.confidence_hi, atol=1e-12)
    np.testing.assert_allclose(loaded.step, bundle.step, atol=1e-12)
    np.testing.assert_allclose(loaded.gain_matrix, bundle.gain_matrix, atol=1e-12)
    np.testing.assert_array_equal(loaded.settling_index, bundle.settling_index)

    np.testing.assert_allclose(loaded.A, bundle.A, atol=1e-12)
    np.testing.assert_allclose(loaded.B, bundle.B, atol=1e-12)
    np.testing.assert_allclose(loaded.C, bundle.C, atol=1e-12)
    np.testing.assert_allclose(loaded.D, bundle.D, atol=1e-12)
    np.testing.assert_allclose(loaded.u0, bundle.u0, atol=1e-12)
    np.testing.assert_allclose(loaded.y0, bundle.y0, atol=1e-12)
    assert loaded.era_order == bundle.era_order

    # Fit summary survives JSON round-trip
    assert "channels" in loaded.fit_summary
    assert len(loaded.fit_summary["channels"]) == len(bundle.fit_summary["channels"])


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_model_bundle(str(tmp_path / "nope.apcmodel"))


def test_to_control_model_simulates(tmp_path):
    result = _make_synthetic_result()
    bundle = bundle_from_ident(
        result, name="x",
        mv_tags=["FIC-101.SP", "FIC-102.SP"],
        cv_tags=["TI-201.PV", "TI-202.PV"],
    )
    save_model_bundle(bundle, str(tmp_path / "x.apcmodel"))
    loaded = load_model_bundle(str(tmp_path / "x.apcmodel"))

    # to_control_model gives us back a usable ControlModel for validation
    cm = loaded.to_control_model()
    assert cm.fir is not None
    assert cm.ss is not None
    assert cm.dt == 60.0

    # Sanity: validate it on the original training data, expect high R^2
    n = 200
    u = np.zeros((n, 2))
    u[20:100, 0] = 1.0
    u[120:, 1] = 0.5

    def foptd(x, gain, tau):
        p = np.exp(-1.0 / tau)
        y = np.zeros(len(x))
        for k in range(len(x) - 1):
            y[k + 1] = p * y[k] + gain * (1 - p) * x[k]
        return y

    y = np.column_stack([
        foptd(u[:, 0], 2.0, 8.0) + foptd(u[:, 1], 1.0, 6.0),
        foptd(u[:, 0], -1.5, 12.0) + foptd(u[:, 1], 2.0, 10.0),
    ])
    rep = validate_model(cm, u, y, mode="ss")
    assert rep.overall_r2 > 0.9
