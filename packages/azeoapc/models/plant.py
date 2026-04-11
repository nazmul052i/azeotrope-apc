"""Plant model implementations for simulation."""
import numpy as np
from scipy.linalg import expm


class StateSpacePlant:
    """Linear discrete state-space plant (deviation variable form).

    x[k+1] = A*dx[k] + Bu*du[k] + Bd*dd[k]
    dy[k]  = C*dx[k] + D*du[k]

    where dx = x - x0, du = u - u0, dd = d - d0, dy = y - y0
    """

    def __init__(self, A, Bu, Bd, C, D, x0, u0, d0, y0,
                 sample_time, continuous=False):
        if continuous:
            A, Bu, Bd = self._c2d(A, Bu, Bd, sample_time)

        self.A = np.array(A, dtype=np.float64)
        self.Bu = np.array(Bu, dtype=np.float64)
        self.Bd = np.array(Bd, dtype=np.float64)
        self.C = np.array(C, dtype=np.float64)
        self.D = np.array(D, dtype=np.float64)
        self.x0 = np.array(x0, dtype=np.float64)
        self.u0 = np.array(u0, dtype=np.float64)
        self.d0 = np.array(d0, dtype=np.float64) if len(d0) > 0 else np.zeros(Bd.shape[1])
        self.y0 = np.array(y0, dtype=np.float64)
        self.dt = sample_time

        self.nx = A.shape[0]
        self.nu = Bu.shape[1]
        self.nd = Bd.shape[1]
        self.ny = C.shape[0]

        # Runtime state (deviation)
        self.dx = np.zeros(self.nx)

    def _c2d(self, Ac, Bc, Bdc, dt):
        """Continuous to discrete via matrix exponential."""
        nx = Ac.shape[0]
        nu = Bc.shape[1]
        nd = Bdc.shape[1]
        # Build augmented matrix [A, [B, Bd]; 0, 0]
        n_aug = nx + nu + nd
        M = np.zeros((n_aug, n_aug))
        M[:nx, :nx] = Ac * dt
        M[:nx, nx:nx+nu] = Bc * dt
        M[:nx, nx+nu:] = Bdc * dt
        eM = expm(M)
        Ad = eM[:nx, :nx]
        Bd_disc = eM[:nx, nx:nx+nu]
        Bdd_disc = eM[:nx, nx+nu:]
        return Ad, Bd_disc, Bdd_disc

    def reset(self):
        self.dx = np.zeros(self.nx)

    def step(self, u: np.ndarray, d: np.ndarray) -> np.ndarray:
        """Advance one step. Returns measured output y (engineering units)."""
        du = u - self.u0
        dd = d - self.d0 if d.size > 0 else np.zeros(self.nd)
        self.dx = self.A @ self.dx + self.Bu @ du + self.Bd @ dd
        dy = self.C @ self.dx + self.D @ du
        return self.y0 + dy

    def get_output(self) -> np.ndarray:
        """Current output without advancing."""
        dy = self.C @ self.dx
        return self.y0 + dy


class FOPTDPlant:
    """MIMO plant from First-Order Plus Dead Time transfer function matrix.

    Each (cv, mv) pair is an independent FOPTD channel simulated via
    discrete first-order dynamics + delay buffer.
    """

    def __init__(self, gains, time_constants, dead_times, sample_time):
        self.gains = np.array(gains, dtype=np.float64)
        self.taus = np.array(time_constants, dtype=np.float64)
        self.Ls = np.array(dead_times, dtype=np.float64)
        self.dt = sample_time
        self.ny, self.nu = self.gains.shape
        self.nd = 0

        # Per-channel state and delay buffers
        self._states = np.zeros((self.ny, self.nu))
        self._delays = {}
        for i in range(self.ny):
            for j in range(self.nu):
                ndelay = max(0, int(round(self.Ls[i, j] / self.dt)))
                self._delays[(i, j)] = [0.0] * ndelay if ndelay > 0 else None

        self.u0 = np.zeros(self.nu)
        self.y0 = np.zeros(self.ny)

    def reset(self):
        self._states = np.zeros((self.ny, self.nu))
        for key in self._delays:
            if self._delays[key] is not None:
                self._delays[key] = [0.0] * len(self._delays[key])

    def step(self, u: np.ndarray, d: np.ndarray) -> np.ndarray:
        y = np.zeros(self.ny)
        for i in range(self.ny):
            for j in range(self.nu):
                u_in = u[j] - self.u0[j]
                # Apply delay
                buf = self._delays[(i, j)]
                if buf is not None:
                    u_delayed = buf[0]
                    buf.pop(0)
                    buf.append(u_in)
                else:
                    u_delayed = u_in
                # First-order dynamics
                tau = self.taus[i, j]
                K = self.gains[i, j]
                if tau > 0:
                    a = np.exp(-self.dt / tau)
                    self._states[i, j] = a * self._states[i, j] + K * (1 - a) * u_delayed
                else:
                    self._states[i, j] = K * u_delayed
                y[i] += self._states[i, j]
        return self.y0 + y

    def get_output(self) -> np.ndarray:
        y = np.zeros(self.ny)
        for i in range(self.ny):
            for j in range(self.nu):
                y[i] += self._states[i, j]
        return self.y0 + y


class NonlinearPlant:
    """Nonlinear ODE plant simulated via RK4 integration.

    The user provides:
      - ode(x, u, d) -> dx/dt   (Python callable using numpy)
      - Optional: a CasADi symbolic version for Layer 3 NLP
        Set via set_casadi_model() after construction.

    Linearization at the current operating point happens via finite
    differences (works without CasADi) or via CasADi auto-diff if a
    symbolic model is provided.
    """

    def __init__(self, ode, nx, nu, nd, ny,
                 x0, u0, d0, y0,
                 sample_time, output_indices=None,
                 casadi_ode=None):
        self.ode = ode                # Python f(x,u,d) -> dx/dt
        self.casadi_ode = casadi_ode  # CasADi function (optional, for NLP)
        self.nx = nx
        self.nu = nu
        self.nd = nd
        self.ny = ny
        self.x0 = np.array(x0, dtype=np.float64)
        self.u0 = np.array(u0, dtype=np.float64)
        self.d0 = np.array(d0, dtype=np.float64) if nd > 0 else np.zeros(0)
        self.y0 = np.array(y0, dtype=np.float64)
        self.dt = sample_time
        # Default: output is identity on first ny states
        if output_indices is None:
            output_indices = list(range(ny))
        self.output_indices = output_indices

        # Runtime state
        self.x = self.x0.copy()

        # For compatibility with StateSpacePlant interface (used by SimEngine)
        # Build a linearized state-space at the steady state for the
        # MPC controller's step response model. This is the "internal model".
        self._build_linearized_ss()

    def _build_linearized_ss(self):
        """Compute discrete A, Bu, Bd, C via finite differences at (x0, u0, d0)."""
        nx, nu, nd, ny = self.nx, self.nu, self.nd, self.ny
        x0, u0, d0 = self.x0, self.u0, self.d0

        # Continuous Jacobians via central differences
        eps = 1e-5
        Ac = np.zeros((nx, nx))
        Bc = np.zeros((nx, nu))
        Bdc = np.zeros((nx, max(nd, 1)))

        for j in range(nx):
            xp = x0.copy(); xm = x0.copy()
            xp[j] += eps; xm[j] -= eps
            fp = np.asarray(self.ode(xp, u0, d0))
            fm = np.asarray(self.ode(xm, u0, d0))
            Ac[:, j] = (fp - fm) / (2 * eps)

        for j in range(nu):
            up = u0.copy(); um = u0.copy()
            up[j] += eps; um[j] -= eps
            fp = np.asarray(self.ode(x0, up, d0))
            fm = np.asarray(self.ode(x0, um, d0))
            Bc[:, j] = (fp - fm) / (2 * eps)

        if nd > 0:
            for j in range(nd):
                dp = d0.copy(); dm = d0.copy()
                dp[j] += eps; dm[j] -= eps
                fp = np.asarray(self.ode(x0, u0, dp))
                fm = np.asarray(self.ode(x0, u0, dm))
                Bdc[:, j] = (fp - fm) / (2 * eps)

        # Discretize via matrix exponential (zero-order hold)
        Ad, Bud, Bdd = self._c2d_discrete(Ac, Bc, Bdc, self.dt)

        # Output matrix C (deviation y = C * dx)
        C = np.zeros((ny, nx))
        for i, idx in enumerate(self.output_indices):
            C[i, idx] = 1.0

        D = np.zeros((ny, nu))

        # Expose for SimEngine compatibility (mimics StateSpacePlant)
        self.A = Ad
        self.Bu = Bud
        self.Bd = Bdd
        self.C = C
        self.D = D

    @staticmethod
    def _c2d_discrete(Ac, Bc, Bdc, dt):
        from scipy.linalg import expm
        nx = Ac.shape[0]
        nu = Bc.shape[1]
        nd = Bdc.shape[1]
        n_aug = nx + nu + nd
        M = np.zeros((n_aug, n_aug))
        M[:nx, :nx] = Ac * dt
        M[:nx, nx:nx + nu] = Bc * dt
        M[:nx, nx + nu:] = Bdc * dt
        eM = expm(M)
        Ad = eM[:nx, :nx]
        Bud = eM[:nx, nx:nx + nu]
        Bdd = eM[:nx, nx + nu:]
        return Ad, Bud, Bdd

    def reset(self):
        self.x = self.x0.copy()

    def step(self, u, d):
        """Advance one sample period via RK4 integration of the nonlinear ODE."""
        h = self.dt
        x = self.x
        if self.nd == 0:
            d = np.zeros(0)

        k1 = np.asarray(self.ode(x, u, d))
        k2 = np.asarray(self.ode(x + 0.5 * h * k1, u, d))
        k3 = np.asarray(self.ode(x + 0.5 * h * k2, u, d))
        k4 = np.asarray(self.ode(x + h * k3, u, d))

        self.x = x + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

        # Output is selected states
        y = np.zeros(self.ny)
        for i, idx in enumerate(self.output_indices):
            y[i] = self.x[idx]
        return y

    def get_output(self):
        y = np.zeros(self.ny)
        for i, idx in enumerate(self.output_indices):
            y[i] = self.x[idx]
        return y

    def linearize_at(self, x_op, u_op, d_op=None):
        """Recompute discrete (A, Bu, Bd, C) at a new operating point.

        Returns: (Ad, Bud, Bdd, C, D) using finite differences.
        Used by Layer 3 RTO to update the gain matrix.
        """
        if d_op is None:
            d_op = self.d0

        nx, nu, nd = self.nx, self.nu, self.nd
        eps = 1e-5

        Ac = np.zeros((nx, nx))
        Bc = np.zeros((nx, nu))
        Bdc = np.zeros((nx, max(nd, 1)))

        for j in range(nx):
            xp = x_op.copy(); xm = x_op.copy()
            xp[j] += eps; xm[j] -= eps
            fp = np.asarray(self.ode(xp, u_op, d_op))
            fm = np.asarray(self.ode(xm, u_op, d_op))
            Ac[:, j] = (fp - fm) / (2 * eps)

        for j in range(nu):
            up = u_op.copy(); um = u_op.copy()
            up[j] += eps; um[j] -= eps
            fp = np.asarray(self.ode(x_op, up, d_op))
            fm = np.asarray(self.ode(x_op, um, d_op))
            Bc[:, j] = (fp - fm) / (2 * eps)

        if nd > 0:
            for j in range(nd):
                dp = d_op.copy(); dm = d_op.copy()
                dp[j] += eps; dm[j] -= eps
                fp = np.asarray(self.ode(x_op, u_op, dp))
                fm = np.asarray(self.ode(x_op, u_op, dm))
                Bdc[:, j] = (fp - fm) / (2 * eps)

        Ad, Bud, Bdd = self._c2d_discrete(Ac, Bc, Bdc, self.dt)

        ny = self.ny
        C = np.zeros((ny, nx))
        for i, idx in enumerate(self.output_indices):
            C[i, idx] = 1.0
        D = np.zeros((ny, nu))

        return Ad, Bud, Bdd, C, D
