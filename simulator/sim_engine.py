"""Simulation engine: connects plant model to MPC controller."""
import numpy as np
import sys
import os

# Try to import C++ core bindings
_HAS_CORE = False
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "build", "bindings", "Release"))
    import _azeoapc_core as core
    _HAS_CORE = True
except ImportError:
    pass

from .models.config_loader import SimConfig
from .models.variables import (
    mv_lp_cost, mv_effective_move_suppress,
    cv_lp_cost, cv_effective_weight, cv_effective_setpoint,
)

try:
    from .layer3_nlp import Layer3NLP, build_layer3
    _HAS_LAYER3 = True
except ImportError:
    _HAS_LAYER3 = False


class SimEngine:
    """Simulation engine that runs plant + MPC each cycle."""

    def __init__(self, config: SimConfig):
        self.cfg = config
        self.plant = config.plant
        self.cycle = 0
        self.closed_loop = True

        nu = len(config.mvs)
        ny = len(config.cvs)
        nd = len(config.dvs)

        # Current values (engineering units)
        self.u = np.array([mv.steady_state for mv in config.mvs])
        self.y = np.array([cv.steady_state for cv in config.cvs])
        self.d = np.array([dv.steady_state for dv in config.dvs]) if nd > 0 else np.zeros(0)
        self.du = np.zeros(nu)

        # Build MPC controller from C++ core
        self.controller = None
        self.last_l1_ms = 0.0
        self.last_l2_ms = 0.0
        self.last_total_ms = 0.0
        self.last_ok = True
        self.last_y_predicted = None   # [P*ny] predicted CV trajectory (deviation)
        self.last_du_full = None       # [M*nu] full planned move sequence

        # Noise injection (controlled from GUI)
        self.noise_enabled = False
        self.noise_factor = 1.0

        # Layer 3 RTO
        self.layer3 = None
        self.last_rto_result = None
        self.last_rto_time_ms = 0.0
        self._cycles_since_rto = 0

        if _HAS_CORE:
            self._build_controller()
        else:
            print("[SimEngine] WARNING: C++ core not available. Running open-loop only.")

        # Try to build Layer 3 if config has it enabled and plant is nonlinear
        if _HAS_LAYER3:
            self.layer3 = build_layer3(config)

    def _build_controller(self):
        """Build MPCController from config using C++ bindings."""
        cfg = self.cfg
        nu = len(cfg.mvs)
        ny = len(cfg.cvs)
        P = cfg.optimizer.prediction_horizon
        M = cfg.optimizer.control_horizon
        N = cfg.optimizer.model_horizon
        dt = cfg.sample_time

        # Build step response model from plant's state-space
        plant = cfg.plant
        if hasattr(plant, 'A'):
            model = core.StepResponseModel.from_state_space(
                plant.A, plant.Bu, plant.C, plant.D, N, dt)
        else:
            # FOPTD: build from gains/taus/deadtimes
            model = core.StepResponseModel.from_foptd_matrix(
                plant.gains, plant.taus, plant.Ls, dt, N)

        # Build MPCConfig
        mpc_cfg = core.MPCConfig()
        mpc_cfg.sample_time = dt

        # Layer 1 -- use opt_type-derived weights
        mpc_cfg.layer1 = core.Layer1Config()
        mpc_cfg.layer1.prediction_horizon = P
        mpc_cfg.layer1.control_horizon = M
        mpc_cfg.layer1.cv_weights = np.array([cv_effective_weight(cv) for cv in cfg.cvs])
        mpc_cfg.layer1.mv_weights = np.array([mv_effective_move_suppress(mv) for mv in cfg.mvs])

        # Layer 2 -- use opt_type-derived costs
        mpc_cfg.layer2 = core.Layer2Config()
        mpc_cfg.layer2.ss_cv_weights = np.array([cv_effective_weight(cv) for cv in cfg.cvs])
        mpc_cfg.layer2.ss_mv_costs = np.array([mv_lp_cost(mv) for mv in cfg.mvs])
        mpc_cfg.layer2.use_lp = False

        mpc_cfg.enable_layer3 = False
        mpc_cfg.enable_storage = False

        self.controller = core.MPCController(mpc_cfg, model)

        # Set constraints in DEVIATION variables (controller works in deviations
        # from steady-state operating point)
        for i, mv in enumerate(cfg.mvs):
            self.controller.set_mv_bounds(
                i,
                mv.limits.operating_lo - mv.steady_state,
                mv.limits.operating_hi - mv.steady_state)
            self.controller.set_mv_rate_limit(i, mv.rate_limit)

        for i, cv in enumerate(cfg.cvs):
            self.controller.set_cv_bounds(
                i,
                cv.limits.operating_lo - cv.steady_state,
                cv.limits.operating_hi - cv.steady_state)
            # Set DMC3 concerns and ranks
            self.controller.set_cv_concern(i, cv.concern_lo, cv.concern_hi)
            self.controller.set_cv_rank(i, cv.rank_lo, cv.rank_hi)

        # Apply MV cost ranks
        for i, mv in enumerate(cfg.mvs):
            self.controller.set_mv_cost_rank(i, mv.cost_rank)

        # Set setpoints (deviation from steady state for QP mode)
        # For Maximize/Minimize opt types, use the bound as the target
        sp = np.array([cv_effective_setpoint(cv) - cv.steady_state for cv in cfg.cvs])
        self.controller.set_setpoints(sp)

    def set_closed_loop(self, closed: bool):
        self.closed_loop = closed
        if self.controller:
            mode = core.ControllerMode.AUTO if closed else core.ControllerMode.MANUAL
            self.controller.set_mode(mode)

    def set_setpoint(self, cv_idx: int, sp: float):
        self.cfg.cvs[cv_idx].setpoint = sp
        if self.controller:
            sp_dev = np.array([cv_effective_setpoint(cv) - cv.steady_state for cv in self.cfg.cvs])
            self.controller.set_setpoints(sp_dev)

    def apply_opt_type(self):
        """Re-apply opt_type-derived costs/weights/setpoints to the running controller.
        Call this after changing any MV/CV opt_type from the GUI."""
        if not self.controller:
            return

        # Update Layer 1 weights
        for i, mv in enumerate(self.cfg.mvs):
            self.controller.set_mv_weight(i, mv_effective_move_suppress(mv))
            self.controller.set_mv_cost(i, mv_lp_cost(mv))
            self.controller.set_mv_cost_rank(i, mv.cost_rank)
        for i, cv in enumerate(self.cfg.cvs):
            self.controller.set_cv_weight(i, cv_effective_weight(cv))
            self.controller.set_cv_concern(i, cv.concern_lo, cv.concern_hi)
            self.controller.set_cv_rank(i, cv.rank_lo, cv.rank_hi)

        # Update setpoints (effective)
        sp_dev = np.array([cv_effective_setpoint(cv) - cv.steady_state
                           for cv in self.cfg.cvs])
        self.controller.set_setpoints(sp_dev)

    def apply_concern(self, cv_idx: int):
        """Apply concern values from the config to the controller."""
        if not self.controller:
            return
        cv = self.cfg.cvs[cv_idx]
        self.controller.set_cv_concern(cv_idx, cv.concern_lo, cv.concern_hi)

    def apply_rank(self, cv_idx: int):
        if not self.controller:
            return
        cv = self.cfg.cvs[cv_idx]
        self.controller.set_cv_rank(cv_idx, cv.rank_lo, cv.rank_hi)

    def apply_mv_cost_rank(self, mv_idx: int):
        if not self.controller:
            return
        mv = self.cfg.mvs[mv_idx]
        self.controller.set_mv_cost_rank(mv_idx, mv.cost_rank)

    def set_dv_value(self, dv_idx: int, val: float):
        self.cfg.dvs[dv_idx].value = val
        self.d[dv_idx] = val

    def set_noise(self, enabled: bool, factor: float = 1.0):
        """Enable/disable measurement noise injection on all CVs."""
        self.noise_enabled = enabled
        self.noise_factor = factor

    def execute_rto(self):
        """Run Layer 3 NLP/RTO once: solve economic NLP, push new gain to Layer 2,
        push new operating point to setpoints. Returns Layer3RTOResult or None.
        """
        if self.layer3 is None or self.controller is None:
            return None
        plant = self.cfg.plant
        if not hasattr(plant, "linearize_at"):
            return None

        # Snapshot current state
        x_now = plant.x.copy() if hasattr(plant, "x") else plant.x0.copy()
        u_now = self.u.copy()
        d_now = self.d.copy() if self.d.size > 0 else np.zeros(0)

        result = self.layer3.solve(x_now, u_now, d_now)
        self.last_rto_result = result
        self.last_rto_time_ms = result.solve_time_ms

        if result.success and result.gain_matrix is not None:
            # Push new gain matrix to Layer 2
            self.controller.update_gain_matrix(result.gain_matrix)
            # Optionally update CV setpoints to the optimal y_ss
            sp_dev = result.y_ss - np.array([cv.steady_state for cv in self.cfg.cvs])
            self.controller.set_setpoints(sp_dev)

        self._cycles_since_rto = 0
        return result

    def step(self):
        """Run one simulation cycle. Returns (y, u, d, du)."""
        # 0. Layer 3 RTO (periodic, slow)
        if self.layer3 is not None and self.cfg.layer3.enabled:
            interval_cycles = max(1, int(self.cfg.layer3.execution_interval_sec
                                          / self.cfg.sample_time))
            if self._cycles_since_rto >= interval_cycles:
                self.execute_rto()
            else:
                self._cycles_since_rto += 1

        # 1. Advance plant
        self.y = self.plant.step(self.u, self.d)

        # Add measurement noise (gated by noise_enabled)
        if self.noise_enabled and self.noise_factor > 0:
            for i, cv in enumerate(self.cfg.cvs):
                if cv.noise > 0:
                    self.y[i] += np.random.normal(0, cv.noise * self.noise_factor)

        # 2. Run controller
        self.du = np.zeros(len(self.cfg.mvs))
        self.last_ok = True

        if self.controller and self.closed_loop:
            # Controller works in deviation variables
            y_dev = self.y - np.array([cv.steady_state for cv in self.cfg.cvs])
            u_dev = self.u - np.array([mv.steady_state for mv in self.cfg.mvs])

            out = self.controller.execute(y_dev, u_dev)
            self.du = np.array(out.du)

            self.last_l1_ms = out.diagnostics.layer1_solve_ms
            self.last_l2_ms = out.diagnostics.layer2_solve_ms
            self.last_total_ms = out.total_solve_time_ms
            self.last_ok = (out.layer1_status == core.SolverStatus.OPTIMAL)
            self.last_y_predicted = np.array(out.y_predicted)
            # Store full du vector for MV forecast
            # out.du is only first move; we need the full M*nu vector
            # For now use the single move repeated
            self.last_du_full = np.array(out.du)

        # 3. Apply moves (with engineering limit clamping)
        for i, mv in enumerate(self.cfg.mvs):
            self.u[i] += self.du[i]
            self.u[i] = np.clip(self.u[i], mv.limits.operating_lo, mv.limits.operating_hi)

        # 4. Update variable current values
        for i, mv in enumerate(self.cfg.mvs):
            mv.value = self.u[i]
        for i, cv in enumerate(self.cfg.cvs):
            cv.value = self.y[i]

        self.cycle += 1
        return self.y, self.u, self.d, self.du

    def reset(self):
        """Reset to initial conditions."""
        self.cycle = 0
        self.plant.reset()
        self.u = np.array([mv.steady_state for mv in self.cfg.mvs])
        self.y = np.array([cv.steady_state for cv in self.cfg.cvs])
        self.d = np.array([dv.steady_state for dv in self.cfg.dvs]) if self.cfg.dvs else np.zeros(0)
        self.du = np.zeros(len(self.cfg.mvs))
        for mv in self.cfg.mvs:
            mv.value = mv.steady_state
        for cv in self.cfg.cvs:
            cv.value = cv.steady_state
        for dv in self.cfg.dvs:
            dv.value = dv.steady_state
        if self.controller:
            self._build_controller()
