# MPCTools Documentation

**Nonlinear Model Predictive Control Tools for CasADi (Python Interface)**

Version 2.4.2 | Copyright (C) 2017, Michael J. Risbeck and James B. Rawlings

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Architecture](#architecture)
- [Core Modules](#core-modules)
  - [tools.py -- Problem Formulation](#toolspy----problem-formulation)
  - [solvers.py -- Optimization Interface](#solverspy----optimization-interface)
  - [util.py -- Utilities](#utilpy----utilities)
  - [colloc.py -- Collocation Methods](#collocpy----collocation-methods)
  - [plots.py -- Visualization](#plotspy----visualization)
  - [mpcsim.py -- Interactive Simulation GUI](#mpcsimpy----interactive-simulation-gui)
- [MPC Methods](#mpc-methods)
- [API Reference](#api-reference)
  - [nmpc()](#nmpc)
  - [nmhe()](#nmhe)
  - [sstarg()](#sstarg)
  - [getCasadiFunc()](#getcasadifunc)
  - [getCasadiIntegrator()](#getcasadiintegrator)
  - [DiscreteSimulator](#discretesimulator)
  - [ControlSolver](#controlsolver)
  - [Utility Functions](#utility-functions)
- [Variable Dictionary (N)](#variable-dictionary-n)
- [CasADi Integration](#casadi-integration)
- [Examples](#examples)
- [Citation](#citation)

---

## Overview

MPCTools is a Python library that provides a high-level interface for solving nonlinear Model Predictive Control (MPC) and Moving Horizon Estimation (MHE) problems using [CasADi](https://casadi.org). It abstracts the complexity of formulating and solving optimal control problems via numerical optimization.

**Key capabilities:**

- Nonlinear MPC (NMPC) with collocation or RK4 discretization
- Linear MPC (LMPC) via quadratic programming
- Moving Horizon Estimation (MHE) for state estimation
- Steady-state target identification (sstarg) for two-layer MPC
- Economic MPC with arbitrary cost functions
- Mixed-integer optimal control (via BONMIN)
- Interactive simulation GUI (Tkinter-based)

**Maintained by:** Rawlings Group, University of California-Santa Barbara

---

## Installation

### Dependencies

| Package    | Version   | Required For              |
|------------|-----------|---------------------------|
| Python     | 3.5+      | Core                      |
| NumPy      | any       | Core                      |
| SciPy      | any       | Core                      |
| Matplotlib | any       | Plotting                  |
| CasADi     | >= 3.0    | Core (solver backend)     |
| Tkinter    | any       | `*_mpcsim.py` GUI examples |

### Install

```bash
pip install -e .
```

Or manually place the `mpctools/` folder in your Python path.

### Solver Backends (via CasADi)

| Solver  | Type            | Notes                  |
|---------|-----------------|------------------------|
| IPOPT   | NLP (default)   | General nonlinear      |
| qpOASES | QP              | Linear/quadratic only  |
| BONMIN  | MINLP           | Mixed-integer problems |
| Gurobi  | MIQP (optional) | Mixed-integer QP       |

---

## Architecture

```
User Script (e.g., cstr.py)
    |
    v
getCasadiFunc()          -- Convert Python functions to CasADi symbolic expressions
    |
    v
nmpc() / nmhe() / sstarg()  -- Build optimization problem (tools.py)
    |
    |--- colloc.weights()    -- Collocation points (if needed)
    |--- __optimalControlProblem()  -- Internal problem assembly
    |
    v
ControlSolver            -- Holds NLP and manages solve cycles (solvers.py)
    |
    v
casadi.nlpsol()          -- IPOPT / qpOASES / BONMIN
    |
    v
solver.var["x"], solver.var["u"]  -- Optimal trajectories
```

### Typical Closed-Loop MPC Pattern

```python
import mpctools as mpc
import numpy as np

# 1. Define model and cost
def ode(x, u):
    return A @ x + B @ u

def stagecost(x, u):
    return x.T @ Q @ x + u.T @ R @ u

# 2. Wrap as CasADi functions
f = mpc.getCasadiFunc(ode, [Nx, Nu], ["x", "u"], funcname="f")
l = mpc.getCasadiFunc(stagecost, [Nx, Nu], ["x", "u"], funcname="l")

# 3. Create solver
N = {"x": Nx, "u": Nu, "t": Nt}
solver = mpc.nmpc(f, l, N, x0, lb, ub)

# 4. Closed-loop simulation
for t in range(Nsim):
    solver.fixvar("x", 0, x_current)   # Set current state
    solver.solve()                       # Solve OCP
    u_apply = np.array(solver.var["u", 0]).flatten()
    x_current = plant_sim(x_current, u_apply)
    solver.saveguess()                   # Warm-start next solve
```

---

## Core Modules

### tools.py -- Problem Formulation

The main entry point for building MPC/MHE problems. Contains:

- **`nmpc()`** -- Nonlinear Model Predictive Control problem builder
- **`nmhe()`** -- Nonlinear Moving Horizon Estimation problem builder
- **`sstarg()`** -- Steady-state target identification
- **`getCasadiFunc()`** -- Python-to-CasADi function converter
- **`getCasadiIntegrator()`** -- ODE integrator builder
- **`DiscreteSimulator`** -- Continuous-to-discrete simulation wrapper

Internal helpers:
- `__optimalControlProblem()` -- Assembles NLP from components
- `__generalConstraints()` -- Builds constraint expressions

### solvers.py -- Optimization Interface

- **`ControlSolver`** -- Main class that holds the NLP and provides `solve()`, `saveguess()`, `fixvar()`, and `addconstraints()` methods
- **`callSolver()`** -- Backward-compatible wrapper that returns a flat dictionary of results

### util.py -- Utilities

Control-theory functions and linear algebra helpers:

- `getLinearizedModel()` -- Jacobian-based linearization at an operating point
- `c2d()` / `c2dObjective()` -- Continuous-to-discrete conversion
- `dlqr()` / `dlqe()` -- Discrete LQR and LQE (Kalman) design
- `ekf()` -- Extended Kalman Filter update step
- `mtimes()` -- CasADi-aware matrix multiplication
- `rk4()` -- Runge-Kutta 4th-order integration

Data structures:
- `ArrayDict` -- Dictionary with automatic numpy array conversion
- `ReadOnlyDict` -- Immutable dictionary wrapper

### colloc.py -- Collocation Methods

Computes collocation points and quadrature weights using Jacobi polynomials.

- **`weights(n, method)`** -- Returns roots `r`, derivative matrices `A`/`B`, and quadrature weights `q`
- Supported methods: `"gauss"`, `"radau"`

### plots.py -- Visualization

- **`mpcplot()`** -- Plot state and input trajectories with optional setpoints
- `showandsave()` -- Display and optionally save figures
- `savemat()` / `loadmat()` -- MATLAB `.mat` file I/O

### mpcsim.py -- Interactive Simulation GUI

- **`makegui()`** -- Creates a Tkinter window for interactive MPC simulation with real-time parameter tuning, trend plots, and step/run/reset controls

---

## MPC Methods

### Nonlinear MPC (NMPC)

Solves a finite-horizon optimal control problem at each time step:

```
min   sum_{t=0}^{N-1} l(x[t], u[t], ...) + Pf(x[N], ...)
s.t.  x[t+1] = f(x[t], u[t], ...)    (dynamics)
      lb <= x, u <= ub                 (box constraints)
      e(x[t], u[t], ...) <= 0         (custom constraints)
```

**Discretization options:**
- Explicit RK4 with integrated stage cost (`Delta` parameter)
- Collocation with Gauss or Radau points (`N["c"]` parameter)

**Features:**
- Input rate constraints via `uprev`
- Time-varying parameters via `p`
- Soft constraints via slack variables (`N["s"]`, `N["sf"]`)
- Discrete/integer inputs via BONMIN solver

### Linear MPC (LMPC)

Uses the same `nmpc()` function with linear dynamics and quadratic cost. Set `isQP=True` in solver options to use qpOASES for faster solves.

### Moving Horizon Estimation (MHE)

Estimates states from noisy measurements over a sliding window:

```
min   sum_{t=0}^{N-1} [ ||w[t]||_Q^2 + ||v[t]||_R^2 ] + prior(x[0])
s.t.  x[t+1] = f(x[t], u[t]) + w[t]     (dynamics + process noise)
      y[t]   = h(x[t]) + v[t]            (measurements)
```

### Steady-State Target (sstarg)

Finds optimal steady-state operating point for two-layer MPC:

```
min   phi(x_s, u_s)
s.t.  x_s = f(x_s, u_s)     (steady-state condition)
      y_s = h(x_s)           (output map)
      bounds on x_s, u_s, y_s
```

### Economic MPC

Supports non-quadratic, economic objective functions. See `econmpc.py` for an example.

### Periodic MPC

Handles time-varying setpoint tracking. See `periodicmpcexample.py`.

---

## API Reference

### nmpc()

```python
mpc.nmpc(f, l, N, x0, lb, ub, guess=None, Pf=None, sp=None,
         uprev=None, funcargs=None, extrapar=None, Delta=None,
         verbosity=5, casaditype="SX", discretel=True, **kwargs)
```

**Parameters:**

| Parameter     | Type          | Description                                          |
|---------------|---------------|------------------------------------------------------|
| `f`           | casadi.Function | Discrete dynamics: `x+ = f(x, u, ...)` or continuous ODE |
| `l`           | casadi.Function | Stage cost: `l(x, u, ...)`                          |
| `N`           | dict          | Dimensions: `{"x", "u", "t", "c", "e", ...}`        |
| `x0`          | array         | Initial state                                        |
| `lb` / `ub`   | dict          | Lower/upper bounds for each variable                 |
| `guess`       | dict          | Initial guess for optimization                       |
| `Pf`          | casadi.Function | Terminal cost: `Pf(x_N, ...)`                       |
| `sp`          | dict          | Setpoints: `{"x": ..., "u": ...}`                   |
| `uprev`       | array         | Previous input (for rate constraints)                |
| `Delta`       | float         | Sampling time (for continuous-time models with RK4)  |
| `verbosity`   | int           | Solver output level (0=silent, 5=default)            |

**Returns:** `ControlSolver` instance

---

### nmhe()

```python
mpc.nmhe(f, h, u, y, l, N, lx=None, x0bar=None, lb=None, ub=None,
         guess=None, wAdditive=True, verbosity=5, **kwargs)
```

**Parameters:**

| Parameter      | Type           | Description                                    |
|----------------|----------------|------------------------------------------------|
| `f`            | casadi.Function | Dynamics: `x+ = f(x, u, ...)`                |
| `h`            | casadi.Function | Measurement model: `y = h(x, ...)`           |
| `u`            | array          | Known input data over window                   |
| `y`            | array          | Measurement data over window                   |
| `l`            | casadi.Function | Stage cost on `(w, v)` noise terms            |
| `N`            | dict           | Dimensions: `{"x", "u", "y", "t", ...}`      |
| `lx`           | casadi.Function | Prior penalty on `x[0]`                       |
| `x0bar`        | array          | Prior state estimate                           |
| `wAdditive`    | bool           | Whether process noise is additive (default True)|

**Returns:** `ControlSolver` instance

---

### sstarg()

```python
mpc.sstarg(f, h, N, phi=None, lb=None, ub=None, guess=None,
           extrapar=None, verbosity=5, **kwargs)
```

**Parameters:**

| Parameter | Type            | Description                               |
|-----------|-----------------|-------------------------------------------|
| `f`       | casadi.Function | Dynamics (steady-state: `x = f(x, u)`)   |
| `h`       | casadi.Function | Output model: `y = h(x)`                 |
| `N`       | dict            | Dimensions: `{"x", "u", "y", ...}`       |
| `phi`     | casadi.Function | Economic cost (optional)                  |

**Returns:** `ControlSolver` instance

---

### getCasadiFunc()

```python
mpc.getCasadiFunc(f, varsizes, varnames, funcname="f",
                  casaditype="SX", Delta=None, M=1, rk4=False, **kwargs)
```

Converts a Python function into a CasADi `Function` object with symbolic evaluation.

| Parameter    | Type    | Description                                      |
|--------------|---------|--------------------------------------------------|
| `f`          | callable | Python function to convert                      |
| `varsizes`   | list    | Sizes of each input argument, e.g. `[Nx, Nu]`   |
| `varnames`   | list    | Names for each input, e.g. `["x", "u"]`         |
| `funcname`   | str     | Name of the CasADi function                      |
| `casaditype` | str     | `"SX"` (scalar) or `"MX"` (matrix expressions)  |
| `Delta`      | float   | Sampling time (enables RK4 discretization)       |
| `M`          | int     | Number of RK4 steps per interval                 |
| `rk4`        | bool    | Force RK4 integration                            |

**Returns:** `casadi.Function`

---

### getCasadiIntegrator()

```python
mpc.getCasadiIntegrator(f, Delta, varsizes, varnames, funcname="F",
                        intargs=None, **kwargs)
```

Creates a CasADi integrator for continuous-time ODE discretization.

| Parameter  | Type   | Description                                            |
|------------|--------|--------------------------------------------------------|
| `f`        | callable | ODE right-hand side function                         |
| `Delta`    | float  | Integration timestep                                   |
| `varsizes` | list   | Sizes of function arguments                            |
| `varnames` | list   | Names of function arguments                            |
| `intargs`  | dict   | Integrator options (solver type, tolerances, etc.)     |

**Returns:** `casadi.Function`

---

### DiscreteSimulator

```python
sim = mpc.DiscreteSimulator(f, Delta, varsizes, varnames, **kwargs)
x_next = sim.sim(x_k, u_k, ...)
```

Wraps continuous-time dynamics into a discrete-time one-step simulator.

---

### ControlSolver

The main optimization object returned by `nmpc()`, `nmhe()`, and `sstarg()`.

**Properties:**

| Property | Description                                    |
|----------|------------------------------------------------|
| `var`    | Optimal solution (nested dict, indexed by time)|
| `par`    | Parameters (can update between solves)         |
| `guess`  | Initial guess for optimization                 |
| `lb`/`ub`| Variable bounds                               |
| `stats`  | Solver statistics (status, time, iterations)   |

**Methods:**

| Method                        | Description                                    |
|-------------------------------|------------------------------------------------|
| `solve()`                     | Execute the optimization                       |
| `saveguess()`                 | Store current solution as initial guess         |
| `fixvar(name, time, value)`   | Fix a variable at a specific time index        |
| `addconstraints(constraints)` | Add custom inequality/equality constraints      |

**Settings:**

| Setting      | Description                              |
|--------------|------------------------------------------|
| `verbosity`  | Solver output level (0-12)               |
| `timelimit`  | Maximum solver time in seconds           |
| `solver`     | Backend: `"ipopt"`, `"qpoases"`, `"bonmin"` |
| `isQP`       | Treat as quadratic program               |

---

### Utility Functions

```python
# Linearization
A, B = mpc.util.getLinearizedModel(f, [xs, us])

# Continuous to discrete conversion
Ad, Bd = mpc.util.c2d(Ac, Bc, Delta)

# LQR/LQE design
K = mpc.util.dlqr(A, B, Q, R)
L = mpc.util.dlqe(A, C, Qw, Rv)

# Extended Kalman Filter
xhat, P = mpc.util.ekf(f, h, x_prev, P_prev, u, y, Q, R)

# Matrix multiplication (CasADi-aware)
result = mpc.util.mtimes(A, B, C)

# RK4 integration
x_next = mpc.util.rk4(f, x, args, Delta, M)
```

---

## Variable Dictionary (N)

The `N` dictionary defines problem dimensions:

| Key   | Description                                | Required |
|-------|--------------------------------------------|----------|
| `"x"` | State dimension                            | Yes      |
| `"u"` | Input dimension                            | Yes      |
| `"t"` | Horizon length (number of time steps)      | Yes      |
| `"y"` | Output dimension (MHE/sstarg)              | Depends  |
| `"p"` | Time-varying parameter dimension           | No       |
| `"z"` | Algebraic state dimension (DAE systems)    | No       |
| `"c"` | Collocation points per interval            | No       |
| `"e"` | Path constraint dimension                  | No       |
| `"s"` | Slack variables for soft constraints       | No       |
| `"sf"`| Slack variables for soft terminal constraints | No   |
| `"w"` | Process noise dimension (MHE, default = x) | No      |
| `"v"` | Measurement noise dimension (MHE, default = y) | No  |

---

## CasADi Integration

MPCTools uses CasADi for:

1. **Symbolic expressions** -- User-defined functions are converted to CasADi symbolic graphs via `getCasadiFunc()`, enabling automatic differentiation
2. **Structured variables** -- `casadi.struct_symMX` organizes decision variables (`x[t]`, `u[t]`, etc.) with named, time-indexed access
3. **NLP solvers** -- `casadi.nlpsol()` wraps IPOPT, qpOASES, and BONMIN with auto-generated gradients and Hessians
4. **Integrators** -- `casadi.integrator()` provides ODE/DAE solvers (cvodes, idas, rk, collocation)

**Symbolic types:**

- **SX** (default) -- Scalar symbolic expressions. Faster for small-to-medium problems.
- **MX** -- Matrix symbolic expressions. Better for problems with shared subexpressions or large sparse structures.

---

## Examples

### Beginner

| File                     | Description                                   |
|--------------------------|-----------------------------------------------|
| `nmpcexample.py`         | Basic NMPC vs LMPC on a 2D nonlinear system  |
| `periodicmpcexample.py`  | MPC with time-varying periodic setpoints      |
| `sstargexample.py`       | Steady-state target with constraints           |
| `template.py`            | Minimal MPC template                           |

### Intermediate

| File                     | Description                                   |
|--------------------------|-----------------------------------------------|
| `nmheexample.py`         | MHE for state estimation with noise           |
| `collocationexample.py`  | Collocation discretization                     |
| `customconstraints.py`   | Adding custom nonlinear constraints             |
| `softconstraints.py`     | Slack variables for constraint softening       |
| `daeexample.py`          | Differential-algebraic equation systems        |
| `solveroptions.py`       | Configuring solver options                     |

### Advanced

| File                     | Description                                   |
|--------------------------|-----------------------------------------------|
| `cstr_nmpc_nmhe.py`      | Integrated NMPC + MHE for CSTR control        |
| `cstr_startup.py`        | CSTR startup with nonlinear trajectory         |
| `econmpc.py`             | Economic MPC with non-quadratic cost           |
| `comparison_casadi.py`   | Direct CasADi implementation for comparison    |
| `comparison_mtc.py`      | Comparison with MPCTools conventions            |

### Application Domains

| File                  | Domain          | Description                      |
|-----------------------|-----------------|----------------------------------|
| `cstr.py`             | Chemical        | Continuous stirred-tank reactor  |
| `airplane.py`         | Mechanical      | Aircraft trajectory control      |
| `ballmaze.py`         | Mechanical      | Ball-in-maze path planning       |
| `icyhill.py`          | Mechanical      | Vehicle on slippery terrain      |
| `fishing.py`          | Economic        | Optimal harvesting               |
| `predatorprey.py`     | Biological      | Population dynamics control      |
| `vdposcillator.py`    | Control theory  | Van der Pol oscillator           |
| `cargears.py`         | Mechanical      | Gear shifting optimization       |

### Interactive GUI Simulations

| File                     | Description                                |
|--------------------------|--------------------------------------------|
| `cstr_nmpc_mpcsim.py`   | CSTR NMPC with interactive parameter tuning|
| `cstr_lqg_mpcsim.py`    | CSTR LQG control dashboard                 |
| `hab_nmpc_mpcsim.py`    | Hot air balloon NMPC simulation            |
| `htr_nmpc_mpcsim.py`    | Heater NMPC simulation                     |
| `siso_lmpc_mpcsim.py`   | SISO linear MPC dashboard                  |
| `heater_pid_mpcsim.py`  | Heater PID control comparison              |

---

## Citation

When using MPCTools, cite both CasADi and MPCTools:

> Risbeck, M.J., Rawlings, J.B., 2015. MPCTools: Nonlinear model predictive
> control tools for CasADi (Python interface).
> `https://bitbucket.org/rawlings-group/mpc-tools-casadi`

For CasADi citation information, see [casadi.org/publications](https://github.com/casadi/casadi/wiki/Publications).

---

## License

MPCTools is free software distributed under the GNU General Public License v3.
