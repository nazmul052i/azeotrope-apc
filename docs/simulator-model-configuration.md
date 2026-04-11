# Simulator Model Configuration Guide

**Azeotrope APC -- Simulation Framework**

This document describes how plant models (CSTR, Fired Heater, Wood-Berry, custom) are configured for the standalone MPC simulator.

---

## 1. Configuration Architecture

Every simulation is defined by a single Python file that declares:

```
SimulationConfig
  |
  +-- PlantModel           (nonlinear ODE or discrete state-space)
  |     +-- states          (x: concentration, temperature, level, ...)
  |     +-- steady_state    (x0, u0, d0, y0)
  |     +-- ode / ss        (function or matrices)
  |
  +-- ControllerConfig      (MPC tuning)
  |     +-- sample_time
  |     +-- prediction_horizon (P)
  |     +-- control_horizon    (M)
  |     +-- model_horizon      (N)
  |
  +-- VariableConfig        (MV / CV / DV lists)
  |     +-- MVs[]           (name, units, limits, rate limits, weights)
  |     +-- CVs[]           (name, units, setpoint, limits, weights)
  |     +-- DVs[]           (name, units, initial value)
  |
  +-- DisplayConfig         (plot layout, colors, ranges)
        +-- window_title
        +-- history_length
        +-- refresh_ms
```

---

## 2. Variable Definitions

### 2.1 Manipulated Variable (MV)

```python
from azeoapc.simulator import MV

MV(
    name       = "Coolant_Temp",          # Tag name (short, code-safe)
    desc       = "Coolant Temperature",   # Description (shown in plot title)
    units      = "K",                     # Engineering units
    value      = 300.0,                   # Initial / current value
    lo_limit   = 250.0,                   # Hard low constraint (P1)
    hi_limit   = 350.0,                   # Hard high constraint (P1)
    rate_limit = 10.0,                    # Max |du| per sample (P2)
    cost       = 0.0,                     # Economic cost for Layer 2 LP
    weight     = 1.0,                     # Move suppression (R diagonal)
    plot_lo    = 240.0,                   # Y-axis plot minimum
    plot_hi    = 360.0,                   # Y-axis plot maximum
    color      = "#0055AA",              # Trend line color
)
```

### 2.2 Controlled Variable (CV)

```python
from azeoapc.simulator import CV

CV(
    name       = "Reactor_Temp",
    desc       = "Reactor Temperature",
    units      = "K",
    value      = 324.5,                  # Initial measured value
    setpoint   = 324.5,                  # Target setpoint
    lo_limit   = 310.0,                  # Operating low (P4)
    hi_limit   = 340.0,                  # Operating high (P4)
    safety_lo  = 290.0,                  # Safety low (P3)
    safety_hi  = 360.0,                  # Safety high (P3)
    weight     = 10.0,                   # Tracking weight (Q diagonal)
    plot_lo    = 280.0,
    plot_hi    = 370.0,
    color      = "#0055AA",
    noise      = 0.1,                    # Measurement noise std dev
)
```

### 2.3 Disturbance Variable (DV)

```python
from azeoapc.simulator import DV

DV(
    name    = "Feed_Temp",
    desc    = "Feed Temperature",
    units   = "K",
    value   = 350.0,                     # Initial / nominal value
    plot_lo = 340.0,
    plot_hi = 360.0,
    color   = "#FF8800",
)
```

---

## 3. Plant Model Definition

Three ways to define a plant model, from simplest to most flexible:

### 3.1 FOPTD Transfer Function Matrix (simplest)

For systems where each CV-MV pair can be described by gain, time constant, and dead time:

```python
from azeoapc.simulator import FOPTDPlant

plant = FOPTDPlant(
    gains = [
        [2.0, -1.0],      # G(cv0,mv0), G(cv0,mv1)
        [1.0,  3.0],      # G(cv1,mv0), G(cv1,mv1)
    ],
    time_constants = [
        [10.0, 15.0],
        [ 8.0, 12.0],
    ],
    dead_times = [
        [3.0, 5.0],
        [1.0, 2.0],
    ],
    sample_time = 1.0,
)
```

The simulator automatically generates the step response model and simulates the plant using superposition of FOPTD responses.

### 3.2 Discrete State-Space Model (linear)

For linearized models (like the fired heater):

```python
from azeoapc.simulator import StateSpacePlant
import numpy as np

plant = StateSpacePlant(
    A  = np.array([...]),     # nx x nx  discrete dynamics
    Bu = np.array([...]),     # nx x nu  input matrix
    Bd = np.array([...]),     # nx x nd  disturbance matrix
    C  = np.array([...]),     # ny x nx  output matrix
    D  = np.zeros((ny, nu)),  # ny x nu  feedthrough (usually zero)

    # Steady-state operating point (model is in deviation variables)
    x0 = np.array([0.0] * nx),
    u0 = np.array([100.0, 100.0, 100.0]),
    d0 = np.array([540.0, 540.0]),
    y0 = np.array([750.0, 200.0, 0.0, 900.0, 900.0]),

    sample_time = 1.0,   # minutes
)
```

### 3.3 Nonlinear ODE (most flexible)

For first-principles models like the CSTR:

```python
from azeoapc.simulator import NonlinearPlant
import numpy as np

def cstr_ode(x, u, d):
    """
    CSTR ODE: dx/dt = f(x, u, d)

    States:  x = [c, T, h]         (concentration, temperature, level)
    Inputs:  u = [Tc, F]           (coolant temp, outlet flow)
    Disturb: d = [F0]              (inlet flow)
    """
    c, T, h = x[0], x[1], x[2]
    Tc, F   = u[0], u[1]
    F0      = d[0]

    # Parameters
    T0, c0, r = 350.0, 1.0, 0.219
    k0, E     = 7.2e10, 8750.0
    U, rho, Cp, dH = 54.94, 1000.0, 0.239, -5.0e4
    A_cross = np.pi * r**2

    rate = k0 * c * np.exp(-E / T)

    dc = F0 * (c0 - c) / (A_cross * h) - rate
    dT = (F0 * (T0 - T) / (A_cross * h)
          - (dH / (rho * Cp)) * rate
          + (2 * U / (r * rho * Cp)) * (Tc - T))
    dh = (F0 - F) / A_cross

    return np.array([dc, dT, dh])


plant = NonlinearPlant(
    ode         = cstr_ode,
    nx          = 3,
    nu          = 2,
    nd          = 1,
    sample_time = 0.5,            # minutes

    # Steady-state operating point
    x0 = np.array([0.878, 324.5, 0.659]),
    u0 = np.array([300.0, 0.1]),
    d0 = np.array([0.1]),

    # Output map: which states are measured (indices or C matrix)
    output_indices = [0, 2],      # measure c and h (not T)
    # OR:
    # C = np.array([[1,0,0], [0,0,1]]),
)
```

---

## 4. Complete Simulation Configuration

### 4.1 CSTR Example

```python
# examples/sim_cstr.py
from azeoapc.simulator import (
    SimulationConfig, MV, CV, DV, NonlinearPlant,
    run_simulator
)
import numpy as np


# ---- Plant Model ----
def cstr_ode(x, u, d):
    c, T, h = x
    Tc, F = u
    F0 = d[0]
    T0, c0, r = 350.0, 1.0, 0.219
    k0, E = 7.2e10, 8750.0
    U, rho, Cp, dH = 54.94, 1000.0, 0.239, -5.0e4
    A = np.pi * r**2
    rate = k0 * c * np.exp(-E / T)
    dc = F0 * (c0 - c) / (A * h) - rate
    dT = (F0 * (T0 - T) / (A * h)
          - (dH / (rho * Cp)) * rate
          + (2 * U / (r * rho * Cp)) * (Tc - T))
    dh = (F0 - F) / A
    return np.array([dc, dT, dh])


plant = NonlinearPlant(
    ode=cstr_ode, nx=3, nu=2, nd=1, sample_time=0.5,
    x0=np.array([0.878, 324.5, 0.659]),
    u0=np.array([300.0, 0.1]),
    d0=np.array([0.1]),
    output_indices=[0, 2],
)

# ---- Variables ----
mvs = [
    MV(name="Tc", desc="Coolant Temperature", units="K",
       value=300.0, lo_limit=250.0, hi_limit=350.0,
       rate_limit=5.0, weight=1.0,
       plot_lo=240.0, plot_hi=360.0),

    MV(name="F", desc="Outlet Flow", units="kL/min",
       value=0.1, lo_limit=0.01, hi_limit=0.5,
       rate_limit=0.03, weight=1.0,
       plot_lo=0.0, plot_hi=0.6),
]

cvs = [
    CV(name="c", desc="Concentration A", units="mol/L",
       value=0.878, setpoint=0.878,
       lo_limit=0.5, hi_limit=1.2,
       safety_lo=0.1, safety_hi=1.4,
       weight=10.0,
       plot_lo=0.0, plot_hi=1.5),

    CV(name="h", desc="Liquid Level", units="m",
       value=0.659, setpoint=0.659,
       lo_limit=0.3, hi_limit=0.9,
       safety_lo=0.1, safety_hi=1.0,
       weight=5.0,
       plot_lo=0.0, plot_hi=1.1),
]

dvs = [
    DV(name="F0", desc="Inlet Flow", units="kL/min",
       value=0.1, plot_lo=0.0, plot_hi=0.3),
]


# ---- Simulation Config ----
config = SimulationConfig(
    name            = "CSTR NMPC Simulation",
    plant           = plant,
    mvs             = mvs,
    cvs             = cvs,
    dvs             = dvs,
    sample_time     = 0.5,          # minutes
    model_horizon   = 120,          # steps
    prediction_horizon = 30,        # steps
    control_horizon = 5,            # steps
    history_length  = 200,          # steps shown in trend
    refresh_ms      = 100,          # GUI update rate
)

if __name__ == "__main__":
    run_simulator(config)
```

### 4.2 Fired Heater Example

```python
# examples/sim_fired_heater.py
from azeoapc.simulator import (
    SimulationConfig, MV, CV, DV, StateSpacePlant,
    run_simulator
)
import numpy as np


# ---- State-Space Matrices (continuous-time, linearized) ----
Ac = np.array([...])   # 10x10, from system identification
Bu = np.array([...])   # 10x3
Bd = np.array([...])   # 10x2
Cx = np.array([...])   # 5x10

plant = StateSpacePlant(
    A=Ac, Bu=Bu, Bd=Bd, C=Cx, D=np.zeros((5, 3)),
    x0=np.zeros(10),
    u0=np.array([100.0, 100.0, 100.0]),
    d0=np.array([540.0, 540.0]),
    y0=np.array([750.0, 200.0, 0.0, 900.0, 900.0]),
    sample_time=1.0,
    continuous=True,     # auto-discretize via matrix exponential
)

# ---- Variables ----
mvs = [
    MV(name="f1sp", desc="Pass 1 Flow Setpoint", units="BPH",
       value=100.0, lo_limit=81.0, hi_limit=119.0,
       rate_limit=5.0, weight=0.001,
       plot_lo=80.0, plot_hi=120.0),

    MV(name="f2sp", desc="Pass 2 Flow Setpoint", units="BPH",
       value=100.0, lo_limit=81.0, hi_limit=119.0,
       rate_limit=5.0, weight=0.001,
       plot_lo=80.0, plot_hi=120.0),

    MV(name="fgsp", desc="Fuel Gas Flow Setpoint", units="SCFH",
       value=100.0, lo_limit=81.0, hi_limit=119.0,
       rate_limit=5.0, weight=5.0,
       plot_lo=80.0, plot_hi=120.0),
]

cvs = [
    CV(name="toc", desc="Combined Outlet Temp", units="degF",
       value=750.0, setpoint=750.0,
       lo_limit=705.0, hi_limit=795.0,
       weight=1.0, noise=1.0,
       plot_lo=700.0, plot_hi=800.0),

    CV(name="foc", desc="Combined Outlet Flow", units="BPH",
       value=200.0, setpoint=200.0,
       lo_limit=155.0, hi_limit=245.0,
       weight=1.0, noise=1.0,
       plot_lo=150.0, plot_hi=250.0),

    CV(name="dpt", desc="Delta Pass Temp", units="degF",
       value=0.0, setpoint=0.0,
       lo_limit=-9.5, hi_limit=9.5,
       weight=0.1, noise=0.1,
       plot_lo=-10.0, plot_hi=10.0),

    CV(name="t1s", desc="Pass 1 Tubeskin Temp", units="degF",
       value=900.0, setpoint=900.0,
       lo_limit=800.0, hi_limit=920.0,
       weight=0.0, noise=0.5,
       plot_lo=870.0, plot_hi=930.0),

    CV(name="t2s", desc="Pass 2 Tubeskin Temp", units="degF",
       value=900.0, setpoint=900.0,
       lo_limit=800.0, hi_limit=920.0,
       weight=0.0, noise=0.5,
       plot_lo=870.0, plot_hi=930.0),
]

dvs = [
    DV(name="t1in", desc="Pass 1 Inlet Temp", units="degF",
       value=540.0, plot_lo=520.0, plot_hi=560.0),

    DV(name="t2in", desc="Pass 2 Inlet Temp", units="degF",
       value=540.0, plot_lo=520.0, plot_hi=560.0),
]

config = SimulationConfig(
    name="Fired Heater NMPC Example",
    plant=plant, mvs=mvs, cvs=cvs, dvs=dvs,
    sample_time=1.0,
    model_horizon=60,
    prediction_horizon=60,
    control_horizon=5,
    history_length=120,
    refresh_ms=100,
)

if __name__ == "__main__":
    run_simulator(config)
```

### 4.3 Wood-Berry Distillation Column

```python
# examples/sim_wood_berry.py
from azeoapc.simulator import (
    SimulationConfig, MV, CV, DV, FOPTDPlant, run_simulator
)

# Classic 2x2 Wood-Berry transfer function matrix
# G(s) = [12.8*exp(-s)/(16.7s+1)    -18.9*exp(-3s)/(21.0s+1)]
#         [6.6*exp(-7s)/(10.9s+1)    -19.4*exp(-3s)/(14.4s+1)]

plant = FOPTDPlant(
    gains           = [[12.8, -18.9], [6.6, -19.4]],
    time_constants  = [[16.7, 21.0],  [10.9, 14.4]],
    dead_times      = [[1.0,  3.0],   [7.0,  3.0]],
    sample_time     = 1.0,
)

mvs = [
    MV(name="R", desc="Reflux Flow", units="%",
       value=50.0, lo_limit=0.0, hi_limit=100.0,
       rate_limit=5.0, weight=0.5,
       plot_lo=0.0, plot_hi=100.0),

    MV(name="S", desc="Steam Flow", units="%",
       value=50.0, lo_limit=0.0, hi_limit=100.0,
       rate_limit=5.0, weight=0.5,
       plot_lo=0.0, plot_hi=100.0),
]

cvs = [
    CV(name="xd", desc="Distillate Composition", units="mol%",
       value=96.0, setpoint=96.0,
       lo_limit=94.0, hi_limit=98.0,
       weight=10.0,
       plot_lo=92.0, plot_hi=100.0),

    CV(name="xb", desc="Bottoms Composition", units="mol%",
       value=0.5, setpoint=0.5,
       lo_limit=0.0, hi_limit=2.0,
       weight=10.0,
       plot_lo=-1.0, plot_hi=3.0),
]

config = SimulationConfig(
    name="Wood-Berry Distillation Column",
    plant=plant, mvs=mvs, cvs=cvs, dvs=[],
    sample_time=1.0,
    model_horizon=60,
    prediction_horizon=20,
    control_horizon=5,
    history_length=150,
    refresh_ms=100,
)

if __name__ == "__main__":
    run_simulator(config)
```

---

## 5. Custom Model Registration

Users can register their own plant models by implementing the `PlantInterface`:

```python
from azeoapc.simulator import PlantInterface
import numpy as np


class MyBoiler(PlantInterface):
    """Custom boiler model with nonlinear steam table lookups."""

    def __init__(self):
        super().__init__(nx=4, nu=2, nd=1, ny=3, sample_time=5.0)
        # ... initialize model parameters ...

    def step(self, x: np.ndarray, u: np.ndarray, d: np.ndarray) -> np.ndarray:
        """Advance state by one sample period. Returns x_next."""
        # ... your dynamics here ...
        return x_next

    def output(self, x: np.ndarray) -> np.ndarray:
        """Compute outputs from states. Returns y."""
        # ... your output map here ...
        return y

    def steady_state(self) -> tuple:
        """Return (x0, u0, d0, y0) at nominal operating point."""
        return self.x0, self.u0, self.d0, self.y0

    def linearize(self, x_op, u_op, d_op) -> dict:
        """Optional: return {A, Bu, Bd, C, D} at operating point."""
        # If not provided, the simulator uses numerical Jacobians
        # via Layer3NLP.linearize_at()
        return {"A": A, "Bu": Bu, "Bd": Bd, "C": C, "D": D}
```

Usage:

```python
plant = MyBoiler()

config = SimulationConfig(
    name="Industrial Boiler MPC",
    plant=plant,
    mvs=[...], cvs=[...], dvs=[...],
    ...
)
```

---

## 6. Scenario / Disturbance Profiles

Predefined disturbance scenarios can be attached to the simulation:

```python
from azeoapc.simulator import Scenario, StepChange, RampChange, NoiseInjection

scenario = Scenario(
    name="Load Change Test",
    events=[
        StepChange(variable="F0", time=50, value=0.11),       # +10% inlet flow at t=50
        StepChange(variable="F0", time=150, value=0.1),       # return to normal
        RampChange(variable="Feed_Temp", time=80, end_time=100,
                   start_value=350.0, end_value=360.0),        # ramp over 20 steps
        NoiseInjection(variable="c", std_dev=0.01,
                       start_time=0, end_time=None),           # continuous noise
    ],
)

config = SimulationConfig(
    ...
    scenario=scenario,   # auto-applies disturbances during simulation
)
```

---

## 7. GUI Interaction Model

The simulator GUI allows runtime changes through variable faceplates:

| Action | How | Effect |
|--------|-----|--------|
| Change setpoint | Click CV faceplate, edit SP field | Updates `MPCController.set_setpoint()` |
| Change MV limits | Click MV faceplate, edit Hi/Lo | Updates `MPCController.set_mv_bounds()` |
| Change CV limits | Click CV faceplate, edit Hi/Lo | Updates `MPCController.set_cv_bounds()` |
| Change DV value | Click DV faceplate, edit value | Modifies plant disturbance input |
| Change MV weight | Right-click MV trend | Updates `MPCController.set_mv_weight()` |
| Pause / Resume | Control bar button | Stops/starts QTimer simulation loop |
| Open / Closed loop | Control bar toggle | `MANUAL` mode returns du=0 |
| Step | Control bar button | Runs exactly one sample period |
| Reset | Control bar button | Restores all values to initial config |

---

## 8. Configuration Summary Table

| Feature | FOPTD | State-Space | Nonlinear ODE |
|---------|-------|-------------|---------------|
| Complexity | Low | Medium | High |
| Model Definition | Gain/tau/deadtime matrices | A, Bu, Bd, C, D matrices | Python function |
| Linearization | Built-in (from parameters) | Already linear | Numerical Jacobians |
| Nonlinear simulation | No (superposition) | No (deviation variables) | Yes (RK4 integration) |
| Disturbance model | Gain + deadtime | Bd matrix | Part of ODE |
| State estimation | Not needed | Kalman (optional) | Disturbance observer |
| Best for | Quick prototyping | Identified/linearized models | First-principles |
| Examples | Wood-Berry | Fired Heater | CSTR |

---

## 9. File Organization

```
simulator/
├── models/
│   ├── __init__.py
│   ├── base.py              # PlantInterface, MV, CV, DV, SimulationConfig
│   ├── foptd_plant.py       # FOPTDPlant
│   ├── statespace_plant.py  # StateSpacePlant (linear, supports c2d)
│   └── nonlinear_plant.py   # NonlinearPlant (ODE + RK4)
├── examples/
│   ├── sim_cstr.py           # CSTR nonlinear
│   ├── sim_fired_heater.py   # Fired heater linear SS
│   ├── sim_wood_berry.py     # Wood-Berry FOPTD
│   └── sim_boiler.py         # Custom model example
└── presets/
    ├── cstr.yaml             # Optional YAML-based config (Phase 7+)
    ├── fired_heater.yaml
    └── wood_berry.yaml
```
