"""
Tests for the C++ core bindings exposed via pybind11.

These tests validate that all major C++ classes are accessible from Python
and that NumPy <-> Eigen conversion works correctly.
"""

import pytest
import numpy as np

# Skip entire module if C++ bindings are not built
try:
    import _azeoapc_core as core
    HAS_CORE = True
except ImportError:
    HAS_CORE = False

pytestmark = pytest.mark.skipif(not HAS_CORE, reason="C++ core bindings not built")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_siso_foptd_model(gain=1.5, tau=60.0, theta=5.0, dt=1.0, N=60):
    """Create a SISO FOPTD step response model."""
    return core.StepResponseModel.from_foptd(gain, tau, theta, dt, N)


def make_layer1_config(ny=1, nu=1, P=20, M=5):
    """Create a Layer1Config with sensible defaults."""
    cfg = core.Layer1Config()
    cfg.prediction_horizon = P
    cfg.control_horizon = M
    cfg.cv_weights = np.ones(ny)
    cfg.mv_weights = 0.1 * np.ones(nu)
    return cfg


def make_layer2_config(ny=1, nu=1, use_lp=False):
    """Create a Layer2Config."""
    cfg = core.Layer2Config()
    cfg.ss_cv_weights = np.ones(ny)
    cfg.ss_mv_costs = np.zeros(nu)
    cfg.use_lp = use_lp
    return cfg


# ---------------------------------------------------------------------------
# StepResponseModel
# ---------------------------------------------------------------------------

class TestStepResponseModel:
    def test_from_foptd(self):
        m = make_siso_foptd_model()
        assert m.ny() == 1
        assert m.nu() == 1
        assert m.model_horizon() == 60
        assert m.sample_time() == 1.0

    def test_from_state_space(self):
        A = np.array([[0.9]])
        B = np.array([[0.1]])
        C = np.array([[1.0]])
        D = np.array([[0.0]])
        m = core.StepResponseModel.from_state_space(A, B, C, D, 30, 1.0)
        assert m.ny() == 1
        assert m.nu() == 1
        # Steady-state gain = C (I - A)^-1 B = 1.0 * (1/(1-0.9)) * 0.1 = 1.0
        G = m.steady_state_gain()
        assert abs(G[0, 0] - 1.0) < 0.05

    def test_from_foptd_matrix_mimo(self):
        gains = np.array([[1.0, 0.5], [0.3, 1.2]])
        taus = np.array([[60.0, 30.0], [45.0, 90.0]])
        thetas = np.array([[3.0, 5.0], [2.0, 4.0]])
        m = core.StepResponseModel.from_foptd_matrix(gains, taus, thetas, 1.0, 60)
        assert m.ny() == 2
        assert m.nu() == 2

    def test_coefficient_and_step_response(self):
        m = make_siso_foptd_model()
        s = m.step_response(0, 0)
        assert len(s) == 60
        # Should be monotonically increasing (FOPTD with positive gain)
        assert all(s[i] <= s[i + 1] + 1e-10 for i in range(len(s) - 1))

    def test_steady_state_gain(self):
        m = make_siso_foptd_model(gain=2.0, tau=10.0, theta=0.0, N=120)
        G = m.steady_state_gain()
        assert abs(G[0, 0] - 2.0) < 0.1

    def test_cv_mv_names(self):
        m = make_siso_foptd_model()
        m.set_cv_names(["Temperature"])
        m.set_mv_names(["Coolant_Flow"])
        assert m.cv_names() == ["Temperature"]
        assert m.mv_names() == ["Coolant_Flow"]

    def test_repr(self):
        m = make_siso_foptd_model()
        r = repr(m)
        assert "StepResponseModel" in r
        assert "ny=1" in r


# ---------------------------------------------------------------------------
# DynamicMatrix
# ---------------------------------------------------------------------------

class TestDynamicMatrix:
    def test_construction(self):
        m = make_siso_foptd_model()
        dm = core.DynamicMatrix(m, 20, 5)
        assert dm.prediction_horizon() == 20
        assert dm.control_horizon() == 5
        assert dm.ny() == 1
        assert dm.nu() == 1

    def test_matrix_shape(self):
        m = make_siso_foptd_model()
        dm = core.DynamicMatrix(m, 20, 5)
        A = dm.matrix()
        assert A.shape == (20, 5)

    def test_cumulative_matrix_shape(self):
        m = make_siso_foptd_model()
        dm = core.DynamicMatrix(m, 20, 5)
        C = dm.cumulative_matrix()
        assert C.shape == (5, 5)

    def test_lower_triangular(self):
        m = make_siso_foptd_model()
        dm = core.DynamicMatrix(m, 10, 3)
        A = dm.matrix()
        # Upper triangle above the block diagonal should be zero
        # For SISO: A[i,j] == 0 when j > i
        for i in range(10):
            for j in range(3):
                if j > i:
                    assert abs(A[i, j]) < 1e-15


# ---------------------------------------------------------------------------
# PredictionEngine
# ---------------------------------------------------------------------------

class TestPredictionEngine:
    def test_construction(self):
        m = make_siso_foptd_model()
        pe = core.PredictionEngine(m, 20, 5)
        fr = pe.free_response()
        assert len(fr) == 20

    def test_update_and_free_response(self):
        m = make_siso_foptd_model()
        pe = core.PredictionEngine(m, 20, 5)
        # Apply a step move
        pe.update(np.array([0.0]), np.array([1.0]))
        fr = pe.free_response()
        assert len(fr) == 20
        # After a positive move with positive gain, free response should be positive
        assert fr[-1] > 0.0

    def test_reset(self):
        m = make_siso_foptd_model()
        pe = core.PredictionEngine(m, 20, 5)
        pe.update(np.array([0.0]), np.array([1.0]))
        pe.reset()
        fr = pe.free_response()
        assert np.allclose(fr, 0.0)


# ---------------------------------------------------------------------------
# DisturbanceObserver
# ---------------------------------------------------------------------------

class TestDisturbanceObserver:
    def test_exponential_filter(self):
        obs = core.DisturbanceObserver(1, core.ObserverMethod.EXPONENTIAL_FILTER)
        # Apply a constant bias
        for _ in range(50):
            d = obs.update(np.array([1.0]), np.array([0.0]))
        assert abs(d[0] - 1.0) < 0.1

    def test_kalman_filter(self):
        obs = core.DisturbanceObserver(1, core.ObserverMethod.KALMAN_FILTER)
        for _ in range(50):
            d = obs.update(np.array([1.0]), np.array([0.0]))
        assert abs(d[0] - 1.0) < 0.2

    def test_reset(self):
        obs = core.DisturbanceObserver(2)
        obs.update(np.array([1.0, 2.0]), np.array([0.0, 0.0]))
        obs.reset()
        est = obs.estimate()
        assert np.allclose(est, 0.0)


# ---------------------------------------------------------------------------
# Layer 1 QP
# ---------------------------------------------------------------------------

class TestLayer1QP:
    def test_unconstrained_tracking(self):
        model = make_siso_foptd_model()
        cfg = make_layer1_config()
        qp = core.Layer1DynamicQP(model, cfg)

        # Free response of zeros, target of 1.0
        P, M, ny, nu = 20, 5, 1, 1
        y_free = np.zeros(P * ny)
        y_target = np.array([1.0])
        u_current = np.array([0.0])
        disturbance = np.zeros(ny)

        result = qp.solve(y_free, y_target, u_current, disturbance)
        assert result.status == core.SolverStatus.OPTIMAL
        assert len(result.du) == M * nu
        # Should recommend positive moves to increase output
        assert result.du[0] > 0.0

    def test_move_constrained(self):
        model = make_siso_foptd_model()
        cfg = make_layer1_config()
        qp = core.Layer1DynamicQP(model, cfg)

        # Set tight move limits
        qp.constraints().set_mv_rate_bounds(
            np.array([-0.1]), np.array([0.1]))

        P, ny = 20, 1
        y_free = np.zeros(P * ny)
        y_target = np.array([10.0])
        u_current = np.array([0.0])
        disturbance = np.zeros(ny)

        result = qp.solve(y_free, y_target, u_current, disturbance)
        assert result.status == core.SolverStatus.OPTIMAL
        # Move should be clipped to 0.1
        assert result.du[0] <= 0.1 + 1e-6


# ---------------------------------------------------------------------------
# Layer 2 SS Target
# ---------------------------------------------------------------------------

class TestLayer2SSTarget:
    def test_qp_tracking(self):
        model = make_siso_foptd_model(gain=1.5, tau=60.0, theta=0.0, N=60)
        cfg = make_layer2_config(use_lp=False)
        l2 = core.Layer2SSTarget(model, cfg)

        y_sp = np.array([3.0])
        d = np.zeros(1)
        result = l2.solve(y_sp, d)
        assert result.status == core.SolverStatus.OPTIMAL
        # y_ss should be near setpoint
        assert abs(result.y_ss[0] - 3.0) < 0.5

    def test_lp_mode(self):
        model = make_siso_foptd_model(gain=1.5, tau=60.0, theta=0.0, N=60)
        cfg = make_layer2_config(use_lp=True)
        # Set bounds so LP is feasible
        l2 = core.Layer2SSTarget(model, cfg)
        l2.constraints().set_mv_bounds(np.array([-10.0]), np.array([10.0]))
        l2.constraints().set_cv_operating_bounds(np.array([-100.0]), np.array([100.0]))

        y_sp = np.array([3.0])
        d = np.zeros(1)
        result = l2.solve(y_sp, d)
        assert result.status == core.SolverStatus.OPTIMAL

    def test_gain_matrix_update(self):
        model = make_siso_foptd_model()
        cfg = make_layer2_config()
        l2 = core.Layer2SSTarget(model, cfg)

        G_new = np.array([[2.0]])
        l2.update_gain_matrix(G_new)
        G = l2.gain_matrix()
        assert abs(G[0, 0] - 2.0) < 1e-10


# ---------------------------------------------------------------------------
# Layer 3 NLP
# ---------------------------------------------------------------------------

class TestLayer3NLP:
    def test_linearize_linear_system(self):
        nlp = core.Layer3NLP("", core.Layer3Config())

        # Linear discrete system: x_next = 0.9*x + 0.1*u
        def linear_model(x, u):
            return np.array([0.9 * x[0] + 0.1 * u[0]])

        nlp.set_model_function(linear_model)
        ss = nlp.linearize_at(np.array([1.0]), np.array([0.5]))
        assert abs(ss.A[0, 0] - 0.9) < 1e-4
        assert abs(ss.B[0, 0] - 0.1) < 1e-4

    def test_solve_returns_current(self):
        nlp = core.Layer3NLP()
        result = nlp.solve(np.array([1.0]), np.array([0.5]))
        assert result.status == core.SolverStatus.OPTIMAL


# ---------------------------------------------------------------------------
# MPCController
# ---------------------------------------------------------------------------

class TestMPCController:
    def _make_controller(self):
        model = make_siso_foptd_model(gain=1.5, tau=60.0, theta=5.0)
        cfg = core.MPCConfig()
        cfg.sample_time = 1.0
        cfg.layer1 = make_layer1_config()
        cfg.layer2 = make_layer2_config()
        cfg.enable_layer3 = False
        cfg.enable_storage = False
        return core.MPCController(cfg, model)

    def test_construction(self):
        ctrl = self._make_controller()
        assert ctrl.ny() == 1
        assert ctrl.nu() == 1
        assert ctrl.cycle_count() == 0

    def test_execute(self):
        ctrl = self._make_controller()
        ctrl.set_setpoints(np.array([1.0]))

        out = ctrl.execute(np.array([0.0]), np.array([0.0]))
        assert out.layer1_status == core.SolverStatus.OPTIMAL
        assert out.layer2_status == core.SolverStatus.OPTIMAL
        assert len(out.du) == 1
        assert out.total_solve_time_ms > 0.0
        assert ctrl.cycle_count() == 1

    def test_manual_mode(self):
        ctrl = self._make_controller()
        ctrl.set_mode(core.ControllerMode.MANUAL)
        assert ctrl.mode() == core.ControllerMode.MANUAL

        out = ctrl.execute(np.array([0.0]), np.array([0.0]))
        # In manual mode, du should be zero
        assert abs(out.du[0]) < 1e-10

    def test_setpoint_tracking(self):
        ctrl = self._make_controller()
        ctrl.set_setpoints(np.array([1.0]))

        # Run several cycles
        y = np.array([0.0])
        u = np.array([0.0])
        for _ in range(10):
            out = ctrl.execute(y, u)
            u = out.u_new

        # After 10 cycles, the controller should have made positive moves
        assert u[0] > 0.0

    def test_repr(self):
        ctrl = self._make_controller()
        r = repr(ctrl)
        assert "MPCController" in r
        assert "ny=1" in r

    def test_status(self):
        ctrl = self._make_controller()
        s = ctrl.status()
        assert s.total_cvs == 1
        assert s.total_mvs == 1
        assert s.is_running is True

    def test_online_tuning(self):
        ctrl = self._make_controller()
        # Should not raise
        ctrl.set_cv_weight(0, 5.0)
        ctrl.set_mv_weight(0, 0.5)
        ctrl.set_mv_rate_limit(0, 2.0)
        ctrl.set_cv_bounds(0, -10.0, 10.0)
        ctrl.set_mv_bounds(0, -50.0, 50.0)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestLogging:
    def test_set_log_level(self):
        # Should not raise for valid levels
        for level in ["trace", "debug", "info", "warn", "error", "off"]:
            core.set_log_level(level)

    def test_invalid_log_level(self):
        with pytest.raises(Exception):
            core.set_log_level("invalid_level")


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------

class TestScaling:
    def test_scale_unscale_roundtrip(self):
        cv_lo = np.array([200.0])
        cv_hi = np.array([500.0])
        mv_lo = np.array([0.0])
        mv_hi = np.array([100.0])
        s = core.Scaling(cv_lo, cv_hi, mv_lo, mv_hi)

        cv_raw = np.array([350.0])
        cv_scaled = s.scale_cv(cv_raw)
        cv_back = s.unscale_cv(cv_scaled)
        assert abs(cv_back[0] - 350.0) < 1e-10
        assert abs(cv_scaled[0] - 0.5) < 1e-10

        mv_raw = np.array([50.0])
        mv_scaled = s.scale_mv(mv_raw)
        mv_back = s.unscale_mv(mv_scaled)
        assert abs(mv_back[0] - 50.0) < 1e-10
