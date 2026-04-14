"""Simulation engine: connects plant model to MPC controller."""
import numpy as np
import sys
import os

# Try to import C++ core bindings.
# __file__ is packages/azeoapc/sim_engine.py -- climb three levels to the
# repo root, then into build/bindings/Release.
_HAS_CORE = False
try:
    _CORE_PATH = os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..", "build", "bindings", "Release"))
    if _CORE_PATH not in sys.path:
        sys.path.insert(0, _CORE_PATH)
    import _azeoapc_core as core
    _HAS_CORE = True
except ImportError:
    pass

from .models.config_loader import SimConfig
from .models.variables import (
    mv_lp_cost, mv_effective_move_suppress,
    cv_lp_cost, cv_effective_weight, cv_effective_setpoint,
)
from .calculations import CalculationRunner

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

        # User calculations runtime (input/output Python scripts)
        self.calc_runner = CalculationRunner(self)

        if _HAS_CORE and config.plant is not None:
            self._build_controller()
        elif config.plant is None:
            print("[SimEngine] WARNING: No plant model loaded. Running open-loop only.")
        else:
            print("[SimEngine] WARNING: C++ core not available. Running open-loop only.")

        # Try to build Layer 3 if config has it enabled and plant is nonlinear
        if _HAS_LAYER3:
            self.layer3 = build_layer3(config)

        # Load any calculations from the YAML config
        for raw in getattr(config, "calculations", []) or []:
            from .calculations import Calculation
            calc = Calculation(
                name=raw.get("name", "calc"),
                description=raw.get("description", ""),
                code=raw.get("code", ""),
                is_input=(raw.get("type", "input") == "input"),
                sequence=raw.get("sequence", 0),
                enabled=raw.get("enabled", True),
            )
            if calc.is_input:
                self.calc_runner.add_input(calc)
            else:
                self.calc_runner.add_output(calc)
            self.calc_runner.compile(calc)

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
        if plant is None:
            print("[SimEngine] WARNING: No plant model -- controller not built.")
            return
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

    def compute_ss_target(self, use_engineering_limits: bool = False):
        """Run Layer 2 LP at the current operating point and return the SS target.

        This is the offline "what would the steady state be?" calculator.
        It does NOT advance the plant or modify the prediction engine state.

        Args:
            use_engineering_limits: if True, temporarily widen all CV/MV bounds
                to engineering limits to compute the "ideal" SS target
                (no operator tightening).

        Returns:
            dict with keys:
                status:    "OPTIMAL" / "INFEASIBLE" / etc.
                u_ss:      np.array of MV steady-state values (engineering units)
                y_ss:      np.array of CV steady-state values (engineering units)
                u_active:  list of bound-active strings ("LO LIM", "HI LIM", "FREE")
                y_active:  list of bound-active strings
                solve_time_ms
                objective
                violations: list of (var_idx, amount) for infeasible CVs
        """
        if self.controller is None:
            return None

        nu = len(self.cfg.mvs)
        ny = len(self.cfg.cvs)

        # Optionally swap to engineering limits for the "ideal SS" calc
        original_bounds = []
        if use_engineering_limits:
            for i, mv in enumerate(self.cfg.mvs):
                original_bounds.append(("mv", i,
                    mv.limits.operating_lo, mv.limits.operating_hi))
                self.controller.set_mv_bounds(
                    i,
                    mv.limits.engineering_lo - mv.steady_state,
                    mv.limits.engineering_hi - mv.steady_state)
            for i, cv in enumerate(self.cfg.cvs):
                original_bounds.append(("cv", i,
                    cv.limits.operating_lo, cv.limits.operating_hi))
                self.controller.set_cv_bounds(
                    i,
                    cv.limits.engineering_lo - cv.steady_state,
                    cv.limits.engineering_hi - cv.steady_state)

        try:
            # Snapshot prediction engine state
            # (controller.execute mutates internal state; we save y_predicted)
            saved_y_pred = self.last_y_predicted
            saved_du = self.du.copy()
            saved_du_full = (self.last_du_full.copy()
                             if self.last_du_full is not None else None)

            # Run one execute cycle WITHOUT updating self.u or self.y
            y_dev = self.y - np.array([cv.steady_state for cv in self.cfg.cvs])
            u_dev = self.u - np.array([mv.steady_state for mv in self.cfg.mvs])
            out = self.controller.execute(y_dev, u_dev)

            # Restore state we don't want to modify
            self.last_y_predicted = saved_y_pred
            self.du = saved_du
            if saved_du_full is not None:
                self.last_du_full = saved_du_full

            # Convert deviation results back to engineering units
            u_ss_eng = (np.array(out.u_ss_target)
                        + np.array([mv.steady_state for mv in self.cfg.mvs]))
            y_ss_eng = (np.array(out.y_ss_target)
                        + np.array([cv.steady_state for cv in self.cfg.cvs]))

            # Determine which bounds are active
            tol = 1e-3
            u_active = []
            for i, mv in enumerate(self.cfg.mvs):
                lo = mv.limits.operating_lo
                hi = mv.limits.operating_hi
                if abs(u_ss_eng[i] - lo) < tol:
                    u_active.append("LO LIM")
                elif abs(u_ss_eng[i] - hi) < tol:
                    u_active.append("HI LIM")
                else:
                    u_active.append("FREE")

            y_active = []
            violations = []
            for i, cv in enumerate(self.cfg.cvs):
                lo = cv.limits.operating_lo
                hi = cv.limits.operating_hi
                if y_ss_eng[i] < lo - tol:
                    y_active.append("VIOL LO")
                    violations.append((i, lo - y_ss_eng[i]))
                elif y_ss_eng[i] > hi + tol:
                    y_active.append("VIOL HI")
                    violations.append((i, y_ss_eng[i] - hi))
                elif abs(y_ss_eng[i] - lo) < tol:
                    y_active.append("AT LO")
                elif abs(y_ss_eng[i] - hi) < tol:
                    y_active.append("AT HI")
                else:
                    y_active.append("FREE")

            status_map = {
                core.SolverStatus.OPTIMAL: "OPTIMAL",
                core.SolverStatus.INFEASIBLE: "INFEASIBLE",
                core.SolverStatus.MAX_ITER: "MAX_ITER",
                core.SolverStatus.NUMERICAL_ERROR: "NUMERICAL_ERROR",
                core.SolverStatus.NOT_SOLVED: "NOT_SOLVED",
            }
            status_str = status_map.get(out.layer2_status, "UNKNOWN")

            return {
                "status": status_str,
                "u_ss": u_ss_eng,
                "y_ss": y_ss_eng,
                "u_active": u_active,
                "y_active": y_active,
                "solve_time_ms": out.diagnostics.layer2_solve_ms,
                "objective": 0.0,  # Layer 2 obj not exposed in ControlOutput
                "violations": violations,
                "feasible": (out.layer2_status == core.SolverStatus.OPTIMAL
                             and len(violations) == 0),
            }

        finally:
            # Restore original bounds if we swapped
            if use_engineering_limits:
                for kind, i, lo, hi in original_bounds:
                    if kind == "mv":
                        mv = self.cfg.mvs[i]
                        self.controller.set_mv_bounds(
                            i, lo - mv.steady_state, hi - mv.steady_state)
                    else:
                        cv = self.cfg.cvs[i]
                        self.controller.set_cv_bounds(
                            i, lo - cv.steady_state, hi - cv.steady_state)

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

        # 0a. Run input calculations (BEFORE plant step / MPC)
        self.calc_runner.run_inputs()

        # 1. Advance plant (skip if no plant model loaded)
        if self.plant is not None:
            self.y = self.plant.step(self.u, self.d)
        # else: y stays at its current value (open-loop / no model)

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

        # 5. Run output calculations (AFTER MPC, before next cycle)
        self.calc_runner.run_outputs()

        # Output calcs may have modified mv.value -- sync back to self.u
        for i, mv in enumerate(self.cfg.mvs):
            self.u[i] = mv.value

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
