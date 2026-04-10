# CLAUDE.md -- Azeotrope APC

This file is the source of truth for Claude Code when working on this repository.

## Status Tracking

**Always check `STATUS.md` at the start of each session.** It tracks:
- Current phase and what's done/not done
- Per-task status with file references
- Phase exit criteria (what must pass before moving on)
- Design decisions log with dates and rationale
- Blockers and open questions

**Update `STATUS.md` whenever you complete a task, make a design decision, or encounter a blocker.** Mark tasks as Done/In Progress/Not Started. Add new entries to the design decisions log when choices are made.

## Project Overview

**Azeotrope APC** is an open-source Advanced Process Control (MPC) platform inspired by AspenTech DMC3. It implements a three-layer optimization architecture with a C++ core engine and Python application layer.

The system is designed to control industrial processes (chemical reactors, distillation columns, boilers, etc.) using Model Predictive Control with real-time optimization.

## Architecture: Three-Layer Optimizer

```
Layer 3: Nonlinear Optimizer  (CasADi C++ / IPOPT)   -- runs periodically (minutes/hours)
    |  re-linearizes plant model, updates gain matrix
    v
Layer 2: Steady-State Target  (HiGHS LP/QP)           -- runs every sample period
    |  finds optimal steady-state within constraints
    v
Layer 1: Dynamic Controller   (OSQP QP)               -- runs every sample period
    |  computes optimal MV moves to track targets
    v
Plant (via OPC UA)
```

**State-space is the primary model representation.** CasADi uses state-space models (A, B, C, D). When the Layer 1 QP needs step response (FIR) coefficients, they are generated from the state-space model via `StepResponseModel::fromStateSpace()`. The flow is:

1. First-principles ODE model (CasADi) -> nonlinear state-space
2. Linearize at operating point -> discrete (A, B, C, D)
3. Generate FIR coefficients from (A, B, C, D) -> step response S[ny, N, nu]
4. Build dynamic matrix (Toeplitz) from step response -> QP formulation

## Reference Repository: mpc-tools-casadi

The sibling repository `C:\Users\nazmuh\Documents\dev\mpc-tools-casadi` (Rawlings Group, Python/CasADi) contains reference implementations. When implementing algorithms, consult these files:

| What to implement | Reference file in mpc-tools-casadi | What to look at |
|---|---|---|
| **State-space linearization** | `mpctools/util.py` lines 68+ | `getLinearizedModel()` -- Jacobian-based linearization using CasADi auto-diff |
| **Continuous to discrete** | `mpctools/util.py` | `c2d()` and `c2dObjective()` -- matrix exponential discretization |
| **Discrete LQR** | `mpctools/util.py` | `dlqr()` -- discrete linear quadratic regulator (DARE solver) |
| **Discrete LQE / Kalman** | `mpctools/util.py` | `dlqe()` -- Kalman filter gain computation |
| **Extended Kalman Filter** | `mpctools/util.py` lines 563+ | `ekf()` -- full EKF update step, reference for disturbance observer |
| **NMPC formulation** | `mpctools/tools.py` | `nmpc()` -- how NLP is built: objective, constraints, collocation, variable structure |
| **Steady-state target** | `mpctools/tools.py` | `sstarg()` -- reference for Layer 2 LP/QP formulation (soft constraints, slack variables) |
| **CasADi function wrapping** | `mpctools/tools.py` | `getCasadiFunc()` -- converting Python functions to CasADi symbolic expressions |
| **CasADi integrator** | `mpctools/tools.py` | `getCasadiIntegrator()` -- ODE integrator construction (cvodes, idas, rk, collocation) |
| **Discrete simulator** | `mpctools/tools.py` | `DiscreteSimulator` class -- wraps continuous ODE into discrete one-step simulator |
| **QP solver integration** | `mpctools/solvers.py` | `ControlSolver` class -- how OSQP/qpOASES/IPOPT are dispatched, warm-starting |
| **Collocation points** | `mpctools/colloc.py` | `weights()` -- Gauss/Radau collocation via Jacobi polynomials |
| **Matrix multiplication** | `mpctools/util.py` | `mtimes()` -- CasADi-aware matrix multiply |
| **RK4 integration** | `mpctools/util.py` | `rk4()` -- Runge-Kutta 4th order |
| **Plotting** | `mpctools/plots.py` | `mpcplot()` -- trajectory visualization patterns |
| **Closed-loop example** | `cstr_nmpc_nmhe.py` | Full NMPC+MHE closed-loop for CSTR -- pattern for integration tests |
| **CSTR model** | `cstr.py` | CSTR ODEs, experiment design -- use as test plant model |
| **GUI simulation** | `mpctools/mpcsim.py` | `makegui()` -- Tkinter simulation framework, reference for builder simulation view |

## External C++ References

### ETHZ Control Toolbox (ct)
https://ethz-adrl.github.io/ct/ct_doc/doc/html/optcon_tut_mpc.html

C++ control library similar to MATLAB Control Toolbox. Reference for:
- State-space model representation and conversion (SS <-> TF, continuous <-> discrete)
- LQR, iLQR, MPC implementations in C++
- System linearization patterns
- Integrator wrappers (RK4, ODE45 equivalents)
- How to structure a C++ control library with templates and Eigen

Use as design reference for our `core/` library -- particularly for model representation classes and the control-theoretic utilities that sit beneath the MPC layers.

### mpc-tools-casadi (sibling repo)
`C:\Users\nazmuh\Documents\dev\mpc-tools-casadi`

Python/CasADi reference for MPC algorithms. See the detailed reference table below.

## Key Design Decisions

- **C++ core, Python apps**: All optimization code (Layers 1-3, prediction, constraints) is C++. Python is for builder, service orchestration, model ID, plotting.
- **State-space primary**: Internal model representation is state-space (A,B,C,D). FIR/step response is derived when needed for the QP layer.
- **YAML + HDF5 storage**: YAML for human-readable config (CV/MV definitions, tuning). HDF5 for numerical data (step response matrices). Never store large numerical arrays in YAML/JSON.
- **SQLite for timeseries**: All optimizer variables, solver states, diagnostics, and logs are persisted to SQLite every cycle. Schema is defined in `core/include/azeoapc/storage.h`.
- **Constraint prioritization**: 5 levels (P1: MV hard limits, P2: MV rate limits, P3: CV safety, P4: CV operating, P5: setpoint tracking). Lower priorities are relaxed when infeasible.
- **Core-first development**: Complete and validate the entire C++ core engine (all 3 layers) before building Builder or Runtime Service.

## File Map

### C++ Core Engine (`core/`)

```
core/include/azeoapc/
  azeoapc.h              -- Master include
  types.h                -- SolverStatus, ControllerMode, CVConfig, MVConfig, DVConfig, DiagnosticsInfo, PerformanceMetrics
  step_response_model.h  -- FIR model: S[ny,N,nu], fromStateSpace(), fromHDF5(), fromFOPTD(), predict()
  dynamic_matrix.h       -- Toeplitz matrix A_dyn from step response, sparse format for QP
  prediction_engine.h    -- Rolling prediction: free response, forced response, past moves history
  disturbance_observer.h -- Output bias estimation (exponential filter or Kalman)
  constraint_handler.h   -- 5-level prioritized constraints, builds QP constraint matrices, relaxation
  scaling.h              -- Variable normalization to [0,1] by engineering range
  layer1_dynamic_qp.h    -- Layer 1: dynamic QP (OSQP), min ||y-y_target||Q + ||du||R s.t. constraints
  layer2_ss_target.h     -- Layer 2: steady-state LP/QP (HiGHS), optimal operating point
  layer3_nlp.h           -- Layer 3: nonlinear optimizer (CasADi C++ / IPOPT), RTO, code generation
  mpc_controller.h       -- MPCController: orchestrates all 3 layers, main API: execute(y,u,dv)->du
  storage.h              -- SQLite timeseries: cv_timeseries, mv_timeseries, solver_log, controller_state
  config.h               -- YAML config loader, validator

core/src/                -- Implementation files (.cpp stubs, to be filled)
core/tests/              -- Google Test files for each component
```

### Python Bindings (`bindings/`)

```
bindings/pybind_opendmc.cpp  -- pybind11 wrapper exposing MPCController, StepResponseModel, Storage to Python
```

### Python Layer (`python/azeoapc/`)

```
python/azeoapc/
  __init__.py                -- Package init, imports C++ bindings
  identification/            -- Model ID: step test, FIR least-squares, subspace (N4SID), ARX, SS-to-step conversion
  config/                    -- Controller config management, YAML schema validation
  simulation/                -- Closed-loop simulation engine (calls C++ core), scenario management
  connectivity/              -- OPC UA client, historian interface, REST API
  storage/                   -- Python interface to SQLite storage
  utils/                     -- Plotting (matplotlib/plotly), HDF5 I/O
```

### Builder Application (`builder/`)

```
builder/app.py               -- Entry point for builder (model ID -> config -> simulate -> deploy)
builder/ui/                  -- UI layer (Qt or web, later phase)
builder/controllers/         -- UI logic
```

### Runtime Service (`service/`)

```
service/main.py              -- Service entry point (scheduling, OPC UA, calls C++ core)
service/engine.py            -- Control loop (to be created)
service/scheduler.py         -- Execution timing (to be created)
service/monitor.py           -- Performance metrics (to be created)
service/server.py            -- gRPC/REST API (to be created)
```

### Examples (`examples/`)

```
examples/siso_foptd.cpp          -- C++ SISO first-order-plus-dead-time example
examples/mimo_wood_berry.cpp     -- C++ 2x2 MIMO Wood-Berry distillation
examples/cstr_three_layer.cpp    -- C++ full three-layer CSTR control
```

### Documentation (`docs/`)

```
docs/dmc-system-proposal.md     -- Full proposal with architecture, algorithms, phases, LLM prompt
docs/documentation.md           -- mpc-tools-casadi documentation (reference)
```

## Build System

- **C++**: CMake 3.20+, C++17. Top-level `CMakeLists.txt` orchestrates core, bindings, examples, tests.
- **Python**: `pyproject.toml` with scikit-build-core for building the pybind11 extension.
- **Dependencies**: Eigen (matrix), OSQP (QP), HiGHS (LP), yaml-cpp (config), HDF5 (models), CasADi+IPOPT (optional Layer 3), pybind11 (bindings), Google Test (C++ tests).
- Missing dependencies are fetched automatically via CMake FetchContent.

## Development Phases (Core First)

1. **Phase 1** (foundation): StepResponseModel, DynamicMatrix, PredictionEngine, DisturbanceObserver. Validate with SISO FOPTD.
2. **Phase 2** (Layer 1): Layer1DynamicQP + OSQP. Validate with constrained SISO, 2x2 MIMO, 4x4 MIMO.
3. **Phase 3** (Layer 2): Layer2SSTarget + HiGHS + ConstraintHandler. Validate two-layer CSTR, infeasibility.
4. **Phase 4** (Layer 3): Layer3NLP + CasADi C++ + IPOPT + code generation. Validate three-layer CSTR.
5. **Phase 5** (integration): MPCController orchestrator, Scaling, config loading, hardening. Benchmark 50x30 MIMO.
6. **Phase 6** (bindings): pybind11 Python bindings.
7. **Phase 7+** (apps): Model identification, Builder, Runtime Service.

**Do not start Phase 7+ until Phases 1-6 are complete and all tests pass.**

## SQLite Timeseries Schema

Every controller cycle logs to SQLite. Tables:

- `cv_timeseries` -- measured, setpoint, ss_target, predicted, limits, disturbance, error per CV per cycle
- `mv_timeseries` -- value, ss_target, du, limits, at_limit flags per MV per cycle
- `dv_timeseries` -- value per DV per cycle
- `solver_log` -- status, objective, solve_time_ms, iterations, relaxed_priorities per layer per cycle
- `controller_state` -- mode, total_solve_ms, diagnostics_json per cycle
- `prediction_log` (optional) -- full predicted trajectory per CV per cycle

Primary key: `(timestamp_ms, cycle)`. See `core/include/azeoapc/storage.h` for full schema.

## QP Formulation (Layer 1)

```
minimize:
    J = || y_pred - y_target ||^2_Q  +  || du ||^2_R

subject to:
    y_pred = y_free + A_dyn * du           (prediction equation)
    du_min <= du <= du_max                  (P2: move size limits)
    u_min <= u_current + C * du <= u_max   (P1: absolute MV limits)
    y_min <= y_pred <= y_max               (P3/P4: CV limits, soft)

where:
    A_dyn  = dynamic matrix (lower-triangular Toeplitz from step response)
    y_free = predicted output with zero future moves (from past data + disturbance)
    du     = [du[k], du[k+1], ..., du[k+M-1]]  (M = control horizon)
    Q      = CV error weight diagonal
    R      = move suppression weight diagonal
```

## SS Target Formulation (Layer 2)

```
minimize:
    J_ss = || y_ss - y_sp ||^2_Qs  +  c^T * u_ss   (tracking + economics)

subject to:
    y_ss = G * u_ss + d_ss        (steady-state gain model, G from step response or SS model)
    u_min <= u_ss <= u_max
    y_min <= y_ss <= y_max         (prioritized soft constraints)
```

## Naming Conventions

- Use **MPC** (not DMC) in class/function names -- this system supports multiple MPC formulations
- C++ namespace: `azeoapc`
- C++ classes: PascalCase (`MPCController`, `StepResponseModel`)
- C++ methods: camelCase (`predictFree`, `solveTime`)
- C++ members: trailing underscore (`model_`, `config_`)
- Python: snake_case for functions/methods, PascalCase for classes
- Header files match class name: `mpc_controller.h` for `MPCController`

## Testing

- C++ tests: Google Test, one test file per component in `core/tests/`
- Python tests: pytest in `python/tests/`
- Every new component must have corresponding tests before moving to the next phase
- Integration tests in `tests/integration/` test full closed-loop scenarios

## Controller Configuration Format

YAML for human-readable config, HDF5 for numerical model data:

```yaml
controller:
  name: "CSTR_MPC"
  sample_time: 60

  controlled_variables:
    - name: "Reactor_Temp"
      tag: "TI-101.PV"
      units: "degC"
      setpoint: 350.0
      hi_limit: 380.0
      lo_limit: 320.0
      safety_hi: 400.0
      safety_lo: 280.0
      priority: 3
      weight: 10.0
      engineering_range: [200, 500]

  manipulated_variables:
    - name: "Coolant_Flow"
      tag: "FV-101.OP"
      units: "%"
      hi_limit: 100.0
      lo_limit: 0.0
      rate_limit: 5.0
      move_suppress: 1.0
      cost: 0.0

  disturbance_variables:
    - name: "Feed_Temp"
      tag: "TI-100.PV"
      units: "degC"
```

HDF5 model file stores: `step_response` float64[ny, N, nu], `steady_state_gain` float64[ny, nu], `cv_names`, `mv_names`, sample_time, model_horizon as attributes.
