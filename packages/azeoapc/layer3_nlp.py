"""Layer 3 NLP -- Real-Time Optimization (RTO) using CasADi + IPOPT.

This module implements the slow outer loop of MPC: economic optimization
of the steady-state operating point using the FULL nonlinear plant model
(not the linearized model used by Layer 1/2).

Workflow each RTO cycle:
  1. Snapshot current operating point (x_now, u_now, d_now)
  2. Build NLP:    minimize  c' * u_ss
                   subject to f(x_ss, u_ss, d_now) = 0  (steady state)
                              MV bounds, CV bounds (from operator limits)
  3. Solve with IPOPT
  4. Linearize plant at the new (x_ss*, u_ss*) operating point
  5. Push the new gain matrix back to Layer 2 SS Target
  6. Push the new operating point to the controller setpoints

Layer 3 runs at a slow rate (e.g., once per hour) compared to Layer 1/2
(every cycle).
"""
from __future__ import annotations

import time
import numpy as np
from typing import Optional, Callable

try:
    import casadi as ca
    _HAS_CASADI = True
except ImportError:
    _HAS_CASADI = False


class Layer3RTOResult:
    """Result of one RTO solve."""
    def __init__(self):
        self.success: bool = False
        self.message: str = ""
        self.x_ss: np.ndarray = None      # optimal steady state
        self.u_ss: np.ndarray = None      # optimal MV values
        self.y_ss: np.ndarray = None      # corresponding outputs
        self.objective: float = 0.0
        self.solve_time_ms: float = 0.0
        self.iterations: int = 0
        # Linearized model at the optimum
        self.A: np.ndarray = None
        self.Bu: np.ndarray = None
        self.Bd: np.ndarray = None
        self.C: np.ndarray = None
        self.gain_matrix: np.ndarray = None  # G = -C * inv(A-I) * Bu  (discrete)


class Layer3NLP:
    """Layer 3 Nonlinear Optimizer using CasADi + IPOPT.

    Builds the steady-state economic optimization problem from the
    nonlinear plant ODE and solves it with IPOPT.
    """

    def __init__(self, plant, mvs, cvs, dvs,
                 sample_time: float,
                 max_iter: int = 500,
                 tolerance: float = 1e-6,
                 verbose: bool = False):
        if not _HAS_CASADI:
            raise RuntimeError(
                "Layer 3 NLP requires CasADi. Install via: pip install casadi")

        self.plant = plant
        self.mvs = mvs
        self.cvs = cvs
        self.dvs = dvs
        self.dt = sample_time
        self.max_iter = max_iter
        self.tolerance = tolerance
        self.verbose = verbose

        self.nx = plant.nx
        self.nu = plant.nu
        self.nd = plant.nd
        self.ny = plant.ny

        # Build a CasADi symbolic version of the ODE if not already provided
        self._cas_ode = self._build_casadi_ode()

        # Build the NLP solver once (reused on each solve)
        self._solver = self._build_nlp_solver()

    # ------------------------------------------------------------------
    def _build_casadi_ode(self):
        """Build a CasADi Function from the user's ODE.

        Approach: directly call the user's ODE function with CasADi symbolic
        variables. This requires the ODE to use CasADi-compatible math
        operators (ca.exp, ca.sin, etc.) rather than numpy. Most physical
        models work transparently because + - * / are operator-overloaded.

        If the user wrote the ODE with np.exp it will fail symbolically and
        we'll fall back to a Callback (which doesn't support derivatives).
        """
        plant = self.plant
        nx, nu, nd = self.nx, self.nu, self.nd

        # If the plant has a pre-built CasADi function, use it
        if hasattr(plant, 'casadi_ode') and plant.casadi_ode is not None:
            return plant.casadi_ode

        # Try direct symbolic evaluation
        x_sym = ca.MX.sym('x', nx)
        u_sym = ca.MX.sym('u', nu)
        d_sym = ca.MX.sym('d', max(nd, 1))

        try:
            dx_sym = plant.ode(x_sym, u_sym, d_sym)
            # Convert to CasADi vertcat if returned as list/array
            if not isinstance(dx_sym, (ca.MX, ca.SX, ca.DM)):
                dx_sym = ca.vertcat(*dx_sym)
            return ca.Function('plant_ode_sym',
                               [x_sym, u_sym, d_sym], [dx_sym])
        except Exception as e:
            raise RuntimeError(
                f"Failed to build symbolic ODE for Layer 3. "
                f"The plant ODE must use CasADi-compatible math (ca.exp, "
                f"ca.sin, etc.) not numpy equivalents. Error: {e}")

    # ------------------------------------------------------------------
    def _build_nlp_solver(self):
        """Build the IPOPT NLP solver.

        Decision variables: z = [x_ss; u_ss]
        Objective:          c' * u_ss + small reg on x
        Constraints:
            f(x_ss, u_ss, d) == 0     (nx equations: steady state)
            y_lo <= C * x_ss <= y_hi  (CV operating bounds)
        Bounds on z handle MV bounds and absolute x bounds.
        """
        nx, nu, nd, ny = self.nx, self.nu, self.nd, self.ny

        x = ca.MX.sym('x', nx)
        u = ca.MX.sym('u', nu)
        d = ca.MX.sym('d', max(nd, 1))   # parameter
        c = ca.MX.sym('c', nu)             # MV cost vector (parameter)

        z = ca.vertcat(x, u)
        p = ca.vertcat(d, c)               # all parameters

        # ODE residual = 0 at steady state
        dx = self._cas_ode(x, u, d)
        steady_state_constraint = dx     # nx equations

        # CV equation: y = C * x  (uses output indices from plant)
        C_np = np.zeros((ny, nx))
        for i, idx in enumerate(self.plant.output_indices):
            C_np[i, idx] = 1.0
        C_dm = ca.DM(C_np)
        y_pred = C_dm @ x                  # ny CV predictions

        # Objective: economic cost on MVs + tiny regularization
        # The regularization keeps the problem well-conditioned
        obj = ca.dot(c, u) + 1e-6 * ca.dot(u - 0, u - 0)

        # Combine constraints (only the steady-state ODE)
        g_list = [steady_state_constraint, y_pred]
        g = ca.vertcat(*g_list)

        nlp = {'x': z, 'p': p, 'f': obj, 'g': g}

        opts = {
            'ipopt.max_iter': self.max_iter,
            'ipopt.tol': self.tolerance,
            'ipopt.print_level': 5 if self.verbose else 0,
            'print_time': 1 if self.verbose else 0,
            'ipopt.sb': 'yes',
            'ipopt.mu_strategy': 'adaptive',
        }

        solver = ca.nlpsol('layer3_solver', 'ipopt', nlp, opts)
        return solver

    # ------------------------------------------------------------------
    def solve(self, x_init: np.ndarray, u_init: np.ndarray,
              d_now: np.ndarray) -> Layer3RTOResult:
        """Solve the steady-state economic NLP.

        Args:
            x_init: warm-start state estimate
            u_init: warm-start MV values
            d_now:  current measured disturbances

        Returns:
            Layer3RTOResult with optimal (x_ss, u_ss) and updated linearization.
        """
        result = Layer3RTOResult()
        t0 = time.time()

        nx, nu, nd, ny = self.nx, self.nu, self.nd, self.ny

        # Build cost vector from MV opt_type / cost
        cost = np.zeros(nu)
        for i, mv in enumerate(self.mvs):
            t = mv.opt_type
            if t == "Maximize":
                cost[i] = -abs(mv.cost) if mv.cost else -1.0
            elif t == "Minimize":
                cost[i] = abs(mv.cost) if mv.cost else 1.0
            else:
                cost[i] = mv.cost  # No Preference: use raw cost

        # Bounds on z = [x; u]
        # x bounds: use plant validity range or wide if not set
        x_lb = np.full(nx, -1e10)
        x_ub = np.full(nx, 1e10)

        # u bounds: from MV operating limits
        u_lb = np.array([mv.limits.operating_lo for mv in self.mvs])
        u_ub = np.array([mv.limits.operating_hi for mv in self.mvs])

        z_lb = np.concatenate([x_lb, u_lb])
        z_ub = np.concatenate([x_ub, u_ub])

        # Constraint bounds:
        # First nx are steady-state equations: g = 0
        # Next ny are CV predictions: cv_lo <= y <= cv_hi
        cv_lo = np.array([cv.limits.operating_lo for cv in self.cvs])
        cv_hi = np.array([cv.limits.operating_hi for cv in self.cvs])

        g_lb = np.concatenate([np.zeros(nx), cv_lo])
        g_ub = np.concatenate([np.zeros(nx), cv_hi])

        # Initial guess
        z0 = np.concatenate([x_init, u_init])

        # Parameter vector
        if nd > 0:
            p_val = np.concatenate([d_now, cost])
        else:
            p_val = np.concatenate([np.zeros(1), cost])

        try:
            sol = self._solver(
                x0=z0, p=p_val,
                lbx=z_lb, ubx=z_ub,
                lbg=g_lb, ubg=g_ub)

            stats = self._solver.stats()
            success = stats['success']

            z_opt = np.asarray(sol['x']).flatten()
            x_ss = z_opt[:nx]
            u_ss = z_opt[nx:]

            result.success = success
            result.message = stats.get('return_status', 'unknown')
            result.x_ss = x_ss
            result.u_ss = u_ss
            result.objective = float(sol['f'])
            result.iterations = stats.get('iter_count', 0)

            # Compute outputs y = C * x
            C_np = np.zeros((ny, nx))
            for i, idx in enumerate(self.plant.output_indices):
                C_np[i, idx] = 1.0
            result.y_ss = C_np @ x_ss

            if success:
                # Linearize plant at the new operating point
                Ad, Bud, Bdd, Cmat, Dmat = self.plant.linearize_at(
                    x_ss, u_ss, d_now if nd > 0 else None)
                result.A = Ad
                result.Bu = Bud
                result.Bd = Bdd
                result.C = Cmat
                # Discrete steady-state gain G = -C * inv(A - I) * Bu
                I = np.eye(nx)
                try:
                    result.gain_matrix = -Cmat @ np.linalg.solve(Ad - I, Bud)
                except np.linalg.LinAlgError:
                    result.gain_matrix = None

        except Exception as e:
            result.success = False
            result.message = f"NLP exception: {e}"

        result.solve_time_ms = (time.time() - t0) * 1000.0
        return result


# ----------------------------------------------------------------------
# Convenience: build Layer 3 from a SimConfig (auto-detects if usable)
# ----------------------------------------------------------------------
def build_layer3(config) -> Optional['Layer3NLP']:
    """Try to build a Layer3NLP from the simulation config.
    Returns None if Layer 3 is not enabled or if the plant is linear-only.
    """
    if not _HAS_CASADI:
        return None

    # Layer 3 only makes sense for nonlinear plants
    plant = config.plant
    if not hasattr(plant, 'ode'):
        return None

    layer3_cfg = getattr(config, 'layer3', None)
    if layer3_cfg is None:
        return None
    if not getattr(layer3_cfg, 'enabled', False):
        return None

    return Layer3NLP(
        plant=plant,
        mvs=config.mvs,
        cvs=config.cvs,
        dvs=config.dvs,
        sample_time=config.sample_time,
        max_iter=getattr(layer3_cfg, 'max_iter', 500),
        tolerance=getattr(layer3_cfg, 'tolerance', 1e-6),
        verbose=False)
