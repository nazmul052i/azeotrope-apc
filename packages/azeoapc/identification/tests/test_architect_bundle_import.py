"""Integration test: identify -> save bundle -> apc_architect loads it -> SimEngine runs."""
from __future__ import annotations

import os

import numpy as np
import pytest
import yaml

from azeoapc.identification import (
    bundle_from_ident, identify_fir, save_model_bundle,
)
from azeoapc.models.config_loader import load_config


def _foptd(x, gain, tau, dt):
    p = np.exp(-dt / tau)
    y = np.zeros(len(x))
    for k in range(len(x) - 1):
        y[k + 1] = p * y[k] + gain * (1 - p) * x[k]
    return y


def _build_bundle(tmp_path):
    """Run a synthetic 2x2 ident and save the bundle."""
    n = 800
    rng = np.random.default_rng(0)
    mv1 = np.zeros(n)
    mv1[100:300] = 1.0
    mv1[500:700] = -0.5
    mv2 = np.zeros(n)
    mv2[200:500] = 0.6
    mv2[600:] = -0.3
    u = np.column_stack([mv1, mv2])

    cv1 = _foptd(mv1, 2.0, 8.0, 1.0) + _foptd(mv2, 1.0, 6.0, 1.0)
    cv2 = _foptd(mv1, -1.5, 12.0, 1.0) + _foptd(mv2, 2.0, 10.0, 1.0)
    cv1 += 0.02 * rng.normal(size=n)
    cv2 += 0.02 * rng.normal(size=n)
    y = np.column_stack([cv1, cv2])

    result = identify_fir(
        u, y, n_coeff=40, dt=1.0, method="dls", smooth="pipeline",
        detrend=False, remove_mean=False,
    )
    bundle = bundle_from_ident(
        result, name="ImportTest",
        mv_tags=["FIC-101.SP", "FIC-102.SP"],
        cv_tags=["TI-201.PV", "TI-202.PV"],
        u0=np.array([100.0, 50.0]),
        y0=np.array([750.0, 200.0]),
    )
    out_path = str(tmp_path / "import_test.apcmodel")
    save_model_bundle(bundle, out_path)
    return out_path, bundle


def _write_yaml(tmp_path, bundle_path):
    """Hand-write a minimal apc_architect controller YAML pointing at the bundle."""
    cfg = {
        "controller": {
            "name": "Bundle Import Test",
            "sample_time": 1.0,
            "time_to_steady_state": 60.0,
        },
        "manipulated_variables": [
            {"tag": "FIC-101.SP", "name": "Pass 1 Flow", "units": "BPH",
             "steady_state": 100.0,
             "limits": {"engineering": [80, 120], "operating": [85, 115]}},
            {"tag": "FIC-102.SP", "name": "Pass 2 Flow", "units": "BPH",
             "steady_state": 50.0,
             "limits": {"engineering": [30, 70], "operating": [35, 65]}},
        ],
        "controlled_variables": [
            {"tag": "TI-201.PV", "name": "Outlet Temp", "units": "degF",
             "steady_state": 750.0, "setpoint": 750.0,
             "limits": {"engineering": [700, 800]}},
            {"tag": "TI-202.PV", "name": "Pass2 Temp", "units": "degF",
             "steady_state": 200.0, "setpoint": 200.0,
             "limits": {"engineering": [150, 250]}},
        ],
        "model": {
            "type": "bundle",
            "source": os.path.basename(bundle_path),
        },
    }
    yaml_path = str(tmp_path / "bundle_import.yaml")
    with open(yaml_path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    return yaml_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_bundle_loads_into_simconfig(tmp_path):
    bundle_path, bundle = _build_bundle(tmp_path)
    yaml_path = _write_yaml(tmp_path, bundle_path)

    cfg = load_config(yaml_path)
    assert cfg.name == "Bundle Import Test"
    assert len(cfg.mvs) == 2
    assert len(cfg.cvs) == 2
    assert cfg.plant is not None

    # Plant should be a StateSpacePlant with the bundle's matrices
    plant = cfg.plant
    assert plant.A.shape == bundle.A.shape
    assert plant.Bu.shape == bundle.B.shape
    assert plant.C.shape == bundle.C.shape
    assert plant.D.shape == bundle.D.shape
    np.testing.assert_allclose(plant.A, bundle.A, atol=1e-12)
    np.testing.assert_allclose(plant.Bu, bundle.B, atol=1e-12)


def test_bundle_steady_state_taken_from_cv_mv_when_not_overridden(tmp_path):
    bundle_path, _ = _build_bundle(tmp_path)
    yaml_path = _write_yaml(tmp_path, bundle_path)
    cfg = load_config(yaml_path)
    plant = cfg.plant
    # u0 from MV.steady_state, y0 from CV.steady_state
    np.testing.assert_allclose(plant.u0, [100.0, 50.0])
    np.testing.assert_allclose(plant.y0, [750.0, 200.0])


def test_bundle_steady_state_yaml_override(tmp_path):
    bundle_path, _ = _build_bundle(tmp_path)
    yaml_path = str(tmp_path / "override.yaml")
    cfg = {
        "controller": {"name": "Override", "sample_time": 1.0},
        "manipulated_variables": [
            {"tag": "FIC-101.SP", "name": "x", "units": "", "steady_state": 100.0},
            {"tag": "FIC-102.SP", "name": "y", "units": "", "steady_state": 50.0},
        ],
        "controlled_variables": [
            {"tag": "TI-201.PV", "name": "x", "units": "", "steady_state": 750.0,
             "setpoint": 750.0},
            {"tag": "TI-202.PV", "name": "y", "units": "", "steady_state": 200.0,
             "setpoint": 200.0},
        ],
        "model": {
            "type": "bundle",
            "source": os.path.basename(bundle_path),
            "steady_state": {
                "u0": [110.0, 55.0],
                "y0": [770.0, 210.0],
            },
        },
    }
    with open(yaml_path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    loaded = load_config(yaml_path)
    np.testing.assert_allclose(loaded.plant.u0, [110.0, 55.0])
    np.testing.assert_allclose(loaded.plant.y0, [770.0, 210.0])


def test_bundle_engine_runs_cycles(tmp_path):
    """The most important integration check: SimEngine builds and runs."""
    bundle_path, _ = _build_bundle(tmp_path)
    yaml_path = _write_yaml(tmp_path, bundle_path)
    cfg = load_config(yaml_path)

    from azeoapc.sim_engine import SimEngine
    eng = SimEngine(cfg)
    for _ in range(10):
        y, u, d, du = eng.step()
    # Engine state advanced
    assert eng.cycle == 10
    # Output should still be near steady state (no setpoint change applied)
    assert all(np.isfinite(eng.y))
    assert all(np.isfinite(eng.u))


def test_missing_bundle_file_raises(tmp_path):
    yaml_path = str(tmp_path / "missing.yaml")
    cfg = {
        "controller": {"name": "x", "sample_time": 1.0},
        "manipulated_variables": [{"tag": "M", "name": "M", "units": "",
                                    "steady_state": 0.0}],
        "controlled_variables": [{"tag": "C", "name": "C", "units": "",
                                   "steady_state": 0.0, "setpoint": 0.0}],
        "model": {"type": "bundle", "source": "does_not_exist.apcmodel"},
    }
    with open(yaml_path, "w") as f:
        yaml.safe_dump(cfg, f)
    with pytest.raises(FileNotFoundError, match="Model bundle not found"):
        load_config(yaml_path)
