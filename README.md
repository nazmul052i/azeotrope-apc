# Azeotrope APC

**Open-Source Advanced Process Control Platform**

An industrial-grade Model Predictive Control (MPC) platform inspired by AspenTech DMC3 Builder, with a C++ three-layer optimization core and a complete Python application stack covering model identification, controller configuration, simulation, deployment, runtime execution, historical data management, and operator console.

---

## Quick Start

```bash
# Clone and install dependencies
git clone https://github.com/your-org/azeotrope-apc.git
cd azeotrope-apc
pip install numpy scipy matplotlib pyyaml h5py PySide6 pyqtgraph pandas asyncua fastapi uvicorn jinja2

# Launch the app suite
python launcher.py
```

This opens the **APC Launcher** hub. Click any card to open an app:

| Order | App | What it does |
|-------|-----|-------------|
| 1 | **APC Ident** | Load step-test CSV, identify FIR models, export `.apcmodel` bundles |
| 2 | **APC Architect** | Configure controller, tune optimizer, run what-if simulations |
| 3 | **APC Runtime** | Run controllers against a plant (desktop manager + REST + historian) |
| 4 | **APC Historian** | Centralized timeseries store + KPI service |
| 5 | **APC Manager** | Operator web console with live trends and tuning forms |

Or launch any app directly:

```bash
python ident.py                                    # Identification studio
python architect.py controller.yaml                # Architect studio
python runtime.py controller.apcproj               # Runtime manager
python runtime.py controller.apcproj --headless     # Headless production mode
python historian.py --port 8770                     # Historian service
python manager.py --port 8780                       # Web console
```

---

## Architecture

```
                          ┌───────────────────────────────────────┐
                          │         APC Launcher (Hub)            │
                          └──────┬──────┬──────┬──────┬──────────┘
                                 │      │      │      │
              ┌──────────────────┘      │      │      └──────────────────┐
              │                         │      │                         │
      ┌───────▼───────┐    ┌────────────▼──┐  ┌▼──────────────┐  ┌──────▼───────┐
      │  APC Ident    │    │ APC Architect  │  │  APC Runtime  │  │ APC Manager  │
      │  (PySide6)    │    │  (PySide6)     │  │  (PySide6 +   │  │ (FastAPI +   │
      │               │    │                │  │   REST/Prom)  │  │  Jinja HTML) │
      │ CSV → FIR →   │    │ Configure →    │  │               │  │              │
      │ .apcmodel     │───▶│ Tune → Sim →   │──│ Start/Stop    │  │ Dashboard    │
      │ bundle        │    │ .apcproj       │  │ Pause/Resume  │  │ Live View    │
      └───────────────┘    └────────────────┘  │ Reload Tuning │  │ Trends       │
                                               └───────┬───────┘  │ Tuning       │
                                                       │          └──────▲───────┘
                                              ┌────────▼────────┐        │
                                              │  APC Historian   │────────┘
                                              │  (FastAPI)       │
                                              │                  │
                                              │  SQLite + KPIs   │
                                              │  + Retention     │
                                              └──────────────────┘
```

### Three-Layer Optimization Engine (C++ core)

```
Layer 3: Nonlinear Optimizer  (CasADi / IPOPT)     — runs periodically
    │  re-linearizes plant model, updates gain matrix
    ▼
Layer 2: Steady-State Target  (HiGHS LP/QP)         — runs every cycle
    │  finds optimal steady-state within constraints
    ▼
Layer 1: Dynamic Controller   (OSQP QP)             — runs every cycle
    │  computes optimal MV moves to track targets
    ▼
Plant (via OPC UA)
```

---

## Project Structure

```
azeotrope-apc/
├── launcher.py                     App suite launcher
├── architect.py                    APC Architect launcher
├── ident.py                        APC Ident launcher
├── runtime.py                      APC Runtime launcher
├── historian.py                    APC Historian launcher
├── manager.py                      APC Manager launcher
│
├── packages/azeoapc/               Shared Python library
│   ├── theme/                      DeltaV Live Silver palette + stylesheet
│   ├── models/                     Variable definitions, plant models, YAML config
│   ├── calculations.py             User Python script runner (input/output calcs)
│   ├── sim_engine.py               Per-cycle plant + MPC orchestrator
│   ├── layer3_nlp.py               Layer 3 NLP (CasADi/IPOPT)
│   ├── deployment/                 IO tags, OPC UA client/server, cycle engine
│   └── identification/             FIR ident, ControlModel, DataConditioner,
│                                   model bundles, validation, ident project
│
├── apps/
│   ├── apc_launcher/               Hub window (workflow-ordered cards)
│   ├── apc_architect/              5-tab studio (Config/Optimize/Calc/Sim/Deploy)
│   ├── apc_ident/                  5-tab studio (Data/Tags/Ident/Results/Validate)
│   ├── apc_runtime/                Desktop manager + headless mode + REST + Prometheus
│   ├── apc_historian/              Centralized SQLite + KPI + REST + retention
│   └── apc_manager/                Operator web console (FastAPI + Jinja + Plotly)
│
├── core/                           C++ optimization engine
│   ├── include/azeoapc/            Headers (StepResponseModel, DynamicMatrix, etc.)
│   ├── src/                        Implementations
│   └── tests/                      Google Test suites
│
├── bindings/                       pybind11 Python ↔ C++ bridge
├── docs/                           Architecture diagrams, reference docs
└── pyproject.toml                  Build config, script entry points
```

---

## Application Details

### APC Ident — Model Identification Studio

Identifies dynamic process models from plant step-test data. Replaces the model-identification workflow of AspenTech DMCplus Model or Honeywell Profit Design Studio.

**Tabs:**
- **Data** — Load CSV/Parquet, view trends with linked axes, mark data segments, define excluded ranges
- **Tags** — Bind CSV columns to MV/CV/DV roles and controller tag names
- **Identification** — Choose method (DLS/COR/Ridge), model length, smoothing, run in background thread
- **Results** — Step-response matrix grid (MV cols × CV rows) with 95% confidence bands, gain matrix, channel-fit diagnostics (R²/RMSE/Ljung-Box), Export Model Bundle (.apcmodel)
- **Validation** — Dual-mode: open-loop multi-step + one-step-ahead prediction, actual vs. predicted trends, per-CV metrics, excitation warning banner

**Identification methods:**
- **Direct Least Squares (DLS)** — standard for open-loop step tests
- **Correlation-based (COR)** — robust to closed-loop data
- **Ridge regression (L2)** — handles collinear inputs

**Model bundle (.apcmodel):** Single HDF5 file containing FIR coefficients, confidence bands, cumulative step response, gain matrix, settling indices, and a low-order state-space realization (ERA). Self-describing with metadata, tag names, and per-channel fit summaries.

### APC Architect — Controller Configuration Studio

The DMC3 Builder equivalent. Configures, tunes, and simulates an MPC controller.

**Tabs:**
- **Configuration** — Summary, feedback filter types (Full Feedback / First Order / Moving Average), subcontroller groups
- **Optimization** — Layer 3 NLP settings, Layer 2 LP wizard (6-step: CV ranks → preferences → MV priority → evaluate → init tuning → SS calculator), Layer 1 QP weights
- **Calculations** — Full Python scripts that run pre/post-MPC each cycle (classes, methods, imports, persistent state)
- **Simulation** — Closed-loop what-if simulator with live plots, noise injection, DMC3-style MV/CV tables with limit columns
- **Deployment** — IO Tags (OPC UA NodeId mapping), Online Settings (watchdog, validation limits), Tag Generator, embedded OPC UA test server

**Project file (.apcproj):** YAML with all controller settings, optimizer tuning, calculations, deployment config. Round-trips through Save/Open with path rebasing for Save As.

### APC Runtime — Production Controller Manager

Runs MPC controllers against a plant. Desktop window (Aspen Watch Maker style) by default; `--headless` for production servers.

**Desktop mode features:**
- Controller table: Name, Status, Model Type, Last Run, Cycle, Cycle Time, Available, Reason
- Toolbar: New, Open, Add, Remove, Start, Stop, Pause, Resume, Refresh
- Filter radio buttons: All / Running / Paused / Stopped / Errors
- Auto-refresh at 1 Hz
- Menu: File (workspace management), Actions (start/stop/reload), Tools (open REST/historian in browser), Help

**Headless mode:** `python runtime.py controller.apcproj --headless` — runs without a window, same REST + Prometheus surface.

**REST surface** (http://localhost:8765):
- `GET /` — HTML landing page with controller table + endpoint reference
- `GET /controllers/{key}/status` — full snapshot
- `GET /controllers/{key}/latest` — last cycle record
- `GET /controllers/{key}/cv/{tag}` — CV trend from local SQLite
- `POST /controllers/{key}/pause|resume|reload|stop`
- `POST /controllers/{key}/cv/{tag}/setpoint` — push setpoint change
- `POST /controllers/{key}/mv/{tag}/limits` — push limit change
- `GET /metrics` — Prometheus text format

**SIGHUP** (Unix): graceful tuning reload from the .apcproj file.

### APC Historian — Centralized Data Service

Centralized SQLite timeseries store that aggregates cycle data from multiple runtimes. Schema mirrors `core/include/azeoapc/storage.h`.

**Features:**
- Multi-controller schema (one DB for all controllers on the box)
- KPI calculator: CV-on-control %, MV at-limit %, solver stats, cycles/min
- Retention thread with configurable purge policy
- REST API for queries (cv/mv trends, controller list, KPI summary)
- HTML landing page

### APC Manager — Operator Web Console

Browser-based operator interface (the PCWS equivalent). Server-side rendered (FastAPI + Jinja2) with client-side Plotly for trends.

**Pages:**
- **Dashboard** — Controller card grid with status badges, auto-refresh
- **Controller** — Live CV/MV/DV table with on-control %, KPI tiles
- **Trends** — Interactive Plotly charts from historian, configurable time window
- **Tuning** — Push setpoint, limit, and move-suppress changes to the running controller

---

## End-to-End Workflow

```
1. Generate step-test data     (run plant, collect MV/CV historian CSV)
2. APC Ident                   (CSV → condition → identify → validate → .apcmodel)
3. APC Architect               (import .apcmodel → configure → tune → simulate → .apcproj)
4. APC Runtime                 (load .apcproj → start → OPC UA cycle loop → historian)
5. APC Historian               (ingest cycles → KPIs → retention → REST queries)
6. APC Manager                 (dashboard → live view → trends → push tuning)
```

Tested end-to-end with a 36-state nonlinear cumene hot-oil heater simulator:
- 721-sample step test (3 MVs, 5 CVs, 12-hour simulated sequence)
- FIR identification: R² = 0.9998 across all 15 channels
- Bundle export: 46 KB HDF5 with ERA(10) state-space realization
- Architect closed-loop simulation tracking setpoints within controller limits
- Runtime forwarding cycles to historian at 17 ms/cycle
- Manager showing live trends and accepting operator tuning pushes

---

## Installation

### Requirements

- Python 3.10+
- C++ compiler (MSVC 2022 / GCC 12+ / Clang 15+) for the core engine
- CMake 3.20+

### Python dependencies

```bash
# Core (always needed)
pip install numpy scipy matplotlib h5py pyyaml

# Desktop apps (architect, ident, runtime, launcher)
pip install PySide6 pyqtgraph

# Identification
pip install pandas

# Services (runtime REST, historian, manager)
pip install fastapi uvicorn jinja2 python-multipart

# OPC UA (deployment, embedded plant server)
pip install asyncua
```

Or install everything at once:

```bash
pip install -e ".[architect,ident,runtime,historian,manager,launcher,dev]"
```

### Building the C++ core

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
ctest --output-on-failure
```

---

## Configuration Format

### Controller config (.apcproj / .yaml)

```yaml
controller:
  name: "Fired Heater MPC"
  sample_time: 1.0            # minutes

model:
  type: bundle                 # or state_space, foptd, nonlinear
  source: my_model.apcmodel   # HDF5 from apc_ident

optimizer:
  prediction_horizon: 30
  control_horizon: 5
  model_horizon: 60

manipulated_variables:
  - tag: "FCV-410.SP"
    name: "Fuel Gas Valve"
    units: "frac"
    steady_state: 0.65
    limits:
      engineering: [0.3, 0.95]
      operating: [0.50, 0.85]
    rate_limit: 0.02
    move_suppress: 1.0

controlled_variables:
  - tag: "TIT-400.PV"
    name: "Supply Header Temp"
    units: "degF"
    steady_state: 600.0
    setpoint: 610.0
    limits:
      engineering: [500, 700]
      operating: [580, 650]
    weight: 10.0
```

### Identification project (.apcident)

```yaml
project:
  name: "Cumene Heater ID"
  author: "N. Hasan"

data_source:
  path: cumene_step_test.csv

tag_assignments:
  - column: FCV-410.SP
    role: MV
    controller_tag: FCV-410.SP
  - column: TIT-400.PV
    role: CV
    controller_tag: TIT-400.PV

identification:
  n_coeff: 60
  dt_seconds: 60.0
  method: dls
  smooth: pipeline
```

---

## Examples

### Fired Heater (bundled)

```bash
python architect.py apps/apc_architect/examples/fired_heater.yaml
```

A 10-state linearized fired heater with 3 MVs (pass flows, fuel gas), 5 CVs (outlet temp, flow, delta-T, tube skin temps), and 2 DVs (inlet temps).

### Cumene Hot Oil Heater (from simulator)

```bash
# Generate step test from the cumene simulator
python apps/apc_ident/examples/cumene/generate_step_test.py

# Load into APC Ident
python ident.py
# -> Load cumene_step_test.csv, identify, export .apcmodel

# Configure controller
python architect.py cumene_controller.yaml
```

36-state nonlinear cumene hot-oil heater with combustion, radiant/convection heat transfer, surge drum, and 8 parallel heat exchanger branches.

---

## Testing

```bash
# Identification library tests (54 tests)
python -m pytest packages/azeoapc/identification/tests -v

# C++ core tests (requires built core)
cd build && ctest --output-on-failure
```

---

## Theory

### Model Predictive Control (MPC)

The controller solves a constrained quadratic program each cycle:

```
minimize:
    J = ‖y_pred − y_target‖²_Q  +  ‖Δu‖²_R

subject to:
    y_pred = y_free + A_dyn · Δu          (prediction equation)
    Δu_min ≤ Δu ≤ Δu_max                  (move size limits)
    u_min ≤ u_current + C · Δu ≤ u_max    (absolute MV limits)
    y_min ≤ y_pred ≤ y_max                 (CV limits, soft)
```

### FIR Identification

The identification engine solves a regression problem to recover the plant's impulse response (Markov parameters):

```
Y = Φ · θ + ε

where Φ is a block-Toeplitz matrix of lagged inputs,
      θ contains the FIR coefficients,
      ε is the residual noise.
```

Three methods are available: Direct Least Squares (open-loop), Correlation (closed-loop tolerant), and Ridge regression (collinear inputs). Post-identification smoothing applies exponential tail decay, Savitzky-Golay filtering, and asymptotic projection.

### Constraint Prioritization

Five priority levels (P1 highest → P5 lowest):
- **P1**: MV hard limits (engineering range)
- **P2**: MV rate-of-change limits
- **P3**: CV safety limits
- **P4**: CV operating limits
- **P5**: Setpoint tracking / economic optimization

Lower priorities are relaxed first when the QP is infeasible.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Credits

Developed by **Nazmul Hasan** with AI assistance from Claude (Anthropic).

Reference implementations consulted:
- [mpc-tools-casadi](https://github.com/rawlings-group/mpc-tools-casadi) (Rawlings Group, UW-Madison)
- [APMonitor Fired Heater Simulation](https://apmonitor.com/dde/index.php/Main/FiredHeaterSimulation)
- AspenTech DMC3 Builder help documentation

---

*Azeotrope Process Control — v0.1.0*
