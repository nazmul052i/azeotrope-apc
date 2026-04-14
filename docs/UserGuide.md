# Azeotrope APC -- User Guide

**Version 0.1.0**

This guide walks you through the complete Azeotrope APC platform, from identifying a process model to running a controller in production with operator oversight. Each section covers one app in the stack; read them in order for the full workflow, or jump to any section for reference.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [APC Launcher](#2-apc-launcher)
3. [APC Ident -- Model Identification](#3-apc-ident----model-identification)
4. [APC Architect -- Controller Configuration](#4-apc-architect----controller-configuration)
5. [APC Runtime -- Production Controller Manager](#5-apc-runtime----production-controller-manager)
6. [APC Historian -- Centralized Data Service](#6-apc-historian----centralized-data-service)
7. [APC Manager -- Operator Web Console](#7-apc-manager----operator-web-console)
8. [File Formats Reference](#8-file-formats-reference)
9. [Theory Reference](#9-theory-reference)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Getting Started

### Installation

```bash
pip install numpy scipy matplotlib h5py pyyaml PySide6 pyqtgraph pandas asyncua fastapi uvicorn jinja2
```

### Launching the platform

```bash
python launcher.py
```

This opens the **APC Launcher** hub. The five apps are shown in workflow order:

```
Ident → Architect → Runtime → Historian → Manager
```

You can also launch any app independently:

```bash
python ident.py                                      # Model identification
python architect.py controller.yaml                  # Controller configuration
python runtime.py controller.apcproj                 # Production runtime
python historian.py --port 8770                       # Data service
python manager.py --port 8780                         # Operator console
```

### Example data

The platform ships with two built-in examples:

- **Fired Heater** (`apps/apc_architect/examples/fired_heater.yaml`) -- 10-state linearized heater, ready to simulate
- **Cumene Hot Oil Heater** (`apps/apc_ident/examples/cumene/cumene_step_test.csv`) -- 721-sample step test from a 36-state nonlinear simulator, ready to identify

---

## 2. APC Launcher

The launcher is the front door. Each card represents one app:

| Card | Icon | Description |
|------|------|-------------|
| **APC Ident** | I (purple) | Identify process models from step-test data |
| **APC Architect** | B (blue) | Configure, tune, and simulate controllers |
| **APC Runtime** | R (orange) | Run controllers against a plant (desktop + REST) |
| **APC Historian** | H (teal) | Centralized cycle store + KPI service |
| **APC Manager** | M (green) | Operator web console with trends + tuning |

### Key behaviors

- **Runtime auto-starts the historian**: When you click Launch on the Runtime card, the launcher checks if the historian is already running. If not, it starts the historian first, waits for it to be ready, then launches the runtime with `--historian-url` so every cycle is forwarded automatically.
- **Services** (Historian, Manager) get Stop and Open in Browser buttons.
- **Desktop apps** (Ident, Architect, Runtime) are launched and forgotten -- close their windows directly.
- On **exit**, the launcher prompts to stop any still-running services.

### Menu

```
Help
  User Guide           (opens this document)
  README               (opens the project README)
  MPC Theory ▶         (submenu of theory topics)
  FIR Identification ▶ (submenu of identification theory)
  Check for Updates    (opens GitHub releases page)
  Report an Issue      (opens GitHub issues page)
  About APC Launcher   (version + credits)
```

---

## 3. APC Ident -- Model Identification

### Purpose

Identifies dynamic process models from plant step-test data. Replaces the model-identification workflow of AspenTech DMCplus Model or Honeywell Profit Design Studio.

### Workflow

#### Step 1: Data tab -- Load step-test data

- Click **Load CSV** to pick a historian-exported file
- The trend strip shows up to 8 columns with linked X axes
- Drag the orange bracket on the bottom trend to select a time window
- Click **Add from Selection** to create a named segment
- Click **Use Whole Range** to use all data
- To exclude operator interventions, select the segment in the table, then drag a bracket and click **+ Excluded from Selection**
- The segment + excluded ranges save into the `.apcident` project file

**Tip**: On **File > New Project**, the bundled cumene heater CSV auto-loads with default tag bindings so you can run identification immediately.

#### Step 2: Tags tab -- Assign variable roles

Each CSV column gets a role:

| Role | Meaning |
|------|---------|
| **MV** | Manipulated variable (controller output, your step-test input) |
| **CV** | Controlled variable (measurement you want to predict) |
| **DV** | Disturbance variable (measured disturbance, not controlled) |
| **Ignore** | Not used in identification |

- Click **Auto-Assign** to set the first half as MV, second half as CV
- Edit the **Controller Tag** column to match your controller's tag names (e.g., `FCV-410.SP`, `TIT-400.PV`). These tag names propagate into the exported model bundle so the architect can bind them.

#### Step 3: Identification tab -- Configure and run

| Parameter | What it does | Typical value |
|-----------|-------------|---------------|
| **Model Length** | Number of FIR coefficients (how many past samples to regress over) | 40--120 |
| **Sample Period** | Must match your data's actual sample rate | 60s for 1-minute data |
| **Method** | DLS (open-loop), COR (closed-loop), Ridge (collinear) | DLS for step tests |
| **Smoothing** | Pipeline = exponential + Savitzky-Golay + asymptotic | Pipeline (recommended) |
| **Hold-out** | Fraction of data reserved for validation (0.15 = last 15%) | 0.15--0.25 |

Click **IDENTIFY MODEL**. The identification runs in a background thread; the progress bar shows activity. When done, the conditioning report and identification summary appear in the right panel.

#### Step 4: Results tab -- Inspect the model

- **Step-response matrix**: one cell per (CV, MV) pair, showing the cumulative step response with 95% confidence bands and the steady-state gain K
- **Gain matrix**: a compact table of all channel gains, color-coded by sign
- **Channel fits**: per-CV R², RMSE, Ljung-Box whiteness test
- **Export Model Bundle**: saves a `.apcmodel` HDF5 file containing the FIR, confidence bands, step response, and a state-space (ERA) realization -- everything the architect needs

#### Step 5: Validation tab -- Verify the model

The validation tab runs the identified model against data the identifier never saw:

| Column | Meaning |
|--------|---------|
| **Open R²** | Multi-step open-loop prediction (the honest score -- this is what the MPC internally does) |
| **One-Step R²** | FIR convolution (the loss the identifier minimised; always looks better) |

- **Test data source** dropdown: Hold-out tail (default), Full training set (overfit check), or Load CSV (external data)
- **Excitation warning**: if the test window has minimal MV movement, an orange banner warns that the metrics are dominated by noise

### File menu

```
File
  New Project           (auto-loads sample CSV + default tags)
  Open Project...       (.apcident YAML)
  Open Recent ▶
  Save                  (Ctrl+S)
  Save As...            (Ctrl+Shift+S)
  Reveal in File Manager
  Exit
```

---

## 4. APC Architect -- Controller Configuration

### Purpose

Configures, tunes, and simulates an MPC controller. The DMC3 Builder equivalent.

### Tabs

#### Configuration

- **Summary**: read-only overview of the loaded controller (name, sample time, CV/MV counts, optimizer horizons)
- **Feedback Filters**: per-CV filter type (Full Feedback / First Order / Moving Average) with time-constant and horizon settings
- **Subcontrollers**: organize MVs and CVs into logical groups (forward-compatible with multi-controller deployments)

#### Optimization

- **Layer 3 (NLP)**: enable/disable the nonlinear optimizer (CasADi/IPOPT), set execution interval, tolerance
- **Layer 2 (LP)**: 6-step Smart Tune Wizard:
  1. CV Ranks -- set hi/lo relaxation order
  2. CV Preferences -- Bounds Only / Minimize / Maximize / Setpoint Track
  3. MV Priority -- No Preference / Minimize / Maximize / Min Movement / Hold at SS
  4. Evaluate Strategy -- preview the LP solution
  5. Init Tuning -- set concern weights and move suppression
  6. SS Calculator -- compute the steady-state target offline
- **Layer 1 (QP)**: prediction/control/model horizons, observer gain

#### Calculations

Full Python scripts that run before (input) or after (output) the MPC each cycle. Features:
- Syntax highlighting, line numbers, Consolas font
- Variables browser: click to insert `cvs["TIT-400.PV"]` at cursor
- Live state panel: current values of all CVs, MVs, user state
- Activity log: timestamped run/error history
- `init()` / `run()` lifecycle: `init()` runs once on Apply, `run()` runs every cycle
- Persistent `user` dict survives across cycles (use for rolling averages, adaptive tuning, etc.)

#### Simulation

Closed-loop what-if simulator with:
- DMC3-style MV and CV tables with symmetric limit columns
- Live pyqtgraph trend strips with prediction overlays
- Noise injection toggle + configurable noise factor
- Step/Auto simulation modes
- Toolbar: Run, Stop, Reset, Noise, Speed

#### Deployment

- **Online Settings**: watchdog, cycle offset, setpoint extended validation, read/write failure limits
- **IO Tags**: Tag Browser (tree from OPC UA server), Tag Generator (template-driven NodeId generation), Variable Detail (per-parameter OPC tag mapping)
- **Activity**: live variable status + log during deployment runtime
- **Embedded OPC UA server**: click Connect to start an in-process OPC server that publishes the simulator's plant as real nodes

### File menu

```
File
  New Project           (Ctrl+N)
  Open Project...       (Ctrl+O)
  Open Recent ▶
  Save                  (Ctrl+S)
  Save As...            (Ctrl+Shift+S)
  Reveal in File Manager
  Exit
View
  Configuration Tab     (Ctrl+1)
  Optimization Tab      (Ctrl+2)
  Calculations Tab      (Ctrl+3)
  Simulation Tab        (Ctrl+4)
  Deployment Tab        (Ctrl+5)
Help
  User Guide / README / MPC Theory ▶ / About
```

---

## 5. APC Runtime -- Production Controller Manager

### Purpose

Runs MPC controllers against a real or simulated plant. Desktop window (Aspen Watch Maker style) by default; `--headless` flag for production servers.

### Desktop mode

The main window shows a table of loaded controllers:

| Column | Meaning |
|--------|---------|
| Name | Controller key (from filename) |
| Status | IDLE / RUNNING / PAUSED / STOPPED / ERROR |
| Model Type | SS / FOPTD / NL |
| Last Run | Timestamp when the controller was last started |
| Cycle | Current cycle number |
| Cycle Time | Duration of the most recent cycle (ms) |
| Avg Time | Exponential moving average of cycle duration |
| Available | YES if running, NO otherwise |
| Reason | OK / error message / current state |

**Toolbar**: New, Open, Add, Remove, Start, Stop, Pause, Resume, Refresh

**Filter radios**: All / Running / Paused / Stopped / Errors

### Adding a controller

File > Add Controller... → pick a `.apcproj` or `.yaml` file. The runner builds a SimEngine from the config, sets up OPC UA tags, and appears in the table as IDLE. Click Start to begin the cycle loop.

### REST surface

While the desktop window is open, a REST surface runs on a background thread (default port 8765). The landing page at `http://localhost:8765` shows a styled HTML page with the controller table and all available endpoints.

### Headless mode

```bash
python runtime.py controller.apcproj --headless --rest-port 8765
```

Runs without a window. SIGINT stops gracefully; SIGHUP reloads tuning.

### Menus

```
File     New Workspace / Add Controller / Remove / Exit
Actions  Start / Stop / Pause / Resume / Start All / Stop All / Refresh (F5)
Tools    Open REST in Browser / Open Historian in Browser / Reveal Run Folder
Help     User Guide / README / MPC Theory ▶ / About APC Runtime
```

---

## 6. APC Historian -- Centralized Data Service

### Purpose

Aggregates cycle data from one or more runtimes into a single SQLite database. Computes KPIs. Applies retention policies.

### Launching

```bash
python historian.py --port 8770 --retention-days 30
```

The runtime forwards every cycle via HTTP POST to `http://localhost:8770/ingest`. The historian stores it and makes it queryable.

### REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | HTML landing page |
| `/healthz` | GET | Liveness probe |
| `/controllers` | GET | List all stored controllers |
| `/controllers/{name}` | GET | Summary + tag list |
| `/controllers/{name}/cv/{tag}` | GET | CV trend (field, limit, since_ms) |
| `/controllers/{name}/mv/{tag}` | GET | MV trend |
| `/controllers/{name}/latest` | GET | Last cycle row |
| `/controllers/{name}/kpi` | GET | KPI summary (window_min, band%) |
| `/ingest` | POST | One cycle record |
| `/admin/purge` | POST | Delete old records |
| `/admin/compact` | POST | VACUUM database |

### KPIs

The `/kpi` endpoint computes (per CV and per MV):
- **CV on-control %**: fraction of cycles where |error| < 5% of operating range
- **CV at-limit %**: fraction touching operating limits
- **MV at-limit %**: fraction pinned to lo or hi limit
- **Solver health**: avg solve time, error %, last error string
- **Cycles/minute**: throughput metric

---

## 7. APC Manager -- Operator Web Console

### Purpose

Browser-based operator interface for monitoring and tuning running controllers. The PCWS (Process Control Web Server) equivalent.

### Launching

```bash
python manager.py --runtime-url http://localhost:8765 \
                  --historian-url http://localhost:8770 \
                  --port 8780
```

Open `http://localhost:8780` in any browser.

### Pages

#### Dashboard (`/`)

Grid of controller cards showing:
- Controller name + status badge (green RUNNING / orange PAUSED / red ERROR)
- Current cycle, cycle time, avg time
- CV/MV/DV counts
- Last error (if any)

Auto-refreshes every 5 seconds.

#### Controller detail (`/controllers/{key}`)

- **Metrics tiles**: cycle count, solve time, cycles/min, error %
- **CV table**: tag, value, setpoint, error, lo/hi limits, on-control %
- **MV table**: tag, value, du, limits, at-lo/at-hi badges
- **DV table**: tag, value
- **Action buttons**: Pause, Resume, Trends, Tuning

#### Trends (`/controllers/{key}/trends`)

Interactive Plotly time-series charts pulled from the historian. One panel per CV + one per MV, all with linked time axes.

Window selector: Last 15 min / 60 min / 4 hours / 24 hours. Auto-refreshes every 10 seconds.

#### Tuning (`/controllers/{key}/tuning`)

Push setpoint, limit, and move-suppress changes directly to the running controller:

- **CV forms**: setpoint, lo limit, hi limit → Apply
- **MV forms**: lo limit, hi limit, move suppress → Apply

Changes take effect within one cycle (the runtime's REST surface forwards them to the live SimEngine).

---

## 8. File Formats Reference

### .apcproj (Controller project)

YAML file containing: project metadata, controller settings, MVs, CVs, DVs, optimizer horizons, Layer 3 config, calculations, deployment IO tags, display preferences. Produced by APC Architect's File > Save.

### .apcmodel (Model bundle)

HDF5 file containing: FIR coefficients [ny, n_coeff, nu], confidence bands, cumulative step response, gain matrix, settling indices, ERA state-space realization (A, B, C, D), tag names, identification metadata. Produced by APC Ident's Export Model Bundle button.

### .apcident (Identification project)

YAML file containing: project metadata, data source path, timestamp column, segments + excluded ranges, tag assignments (column → role → controller_tag), conditioning config, identification config, last bundle path. Produced by APC Ident's File > Save.

### cycles.jsonl / latest.json / events.log

Per-controller runtime output in `runs/{controller}/`:
- **cycles.jsonl**: one JSON object per cycle (append-only)
- **latest.json**: atomically-replaced snapshot of the most recent cycle
- **events.log**: human-readable timestamped log (info/warn/error)

### history.db

SQLite database (local per-controller in `runs/{controller}/` + centralized in the historian). Schema matches `core/include/azeoapc/storage.h`.

---

## 9. Theory Reference

### Model Predictive Control (MPC)

MPC is a control strategy that uses a dynamic model of the process to predict future behavior over a finite horizon and optimizes the controller moves to minimize a cost function subject to constraints. At each sample time, the controller:

1. Reads current measurements from the plant
2. Predicts future outputs using the process model
3. Solves a constrained optimization (QP) to find the best sequence of future moves
4. Applies only the first move, then repeats at the next sample

### FIR Identification

Finite Impulse Response identification recovers the plant's Markov parameters (impulse response coefficients) from input/output data. The cumulative sum of FIR coefficients gives the step response -- the native format used by DMC-family controllers.

**Direct Least Squares**: construct a Toeplitz matrix of lagged inputs, solve Y = Phi * theta via SVD. Best for clean open-loop step tests.

**Correlation method**: solve Ruu * theta = Ruy using auto- and cross-correlation matrices. More robust to closed-loop data.

**Ridge regression**: add Tikhonov regularization (alpha * I) to handle collinear inputs. Essential when multiple MVs move together.

### Smoothing pipeline

1. **Exponential tail decay**: force late coefficients toward zero
2. **Savitzky-Golay filter**: preserve shape while removing noise
3. **Asymptotic projection**: cosine-blend the tail to zero

### ERA (Eigensystem Realization Algorithm)

Converts FIR Markov parameters to a balanced state-space (A, B, C, D) via SVD of block-Hankel matrices. The bundle exports a low-order ERA realization so the architect can build a SimEngine immediately.

### Validation modes

- **Open-loop (multi-step)**: state evolves freely from initial condition -- the honest score, matches what the MPC does internally
- **One-step-ahead**: each prediction uses only the past n_coeff real inputs -- always looks better but doesn't predict drift

---

## 10. Troubleshooting

### "No module named 'simulator'"

The cumene heater step-test generator needs the sibling simulator repo. Edit `_SIM_REPO` at the top of `generate_step_test.py` to point at your checkout.

### OPC UA server fails to start

Port 4840 is reserved on some Windows systems. The runtime allocates ports starting at 4842 automatically. If you see "PermissionError", check if another process is using that port.

### "asyncua not installed"

Install with `pip install asyncua`. Required only for the Deployment tab and embedded OPC server.

### Architect shows "C++ core not available"

The C++ optimization core (`_azeoapc_core`) needs to be built first. See README.md for build instructions. Without it, the simulator runs in open-loop mode only (plant advances but the MPC doesn't compute moves).

### Historian not receiving cycles

Check that the runtime was launched with `--historian-url http://localhost:8770`. The forwarder is best-effort; if the historian is down, records are dropped (they're still in the local SQLite under `runs/{controller}/history.db`).

### Manager shows "runtime unreachable"

Make sure the runtime is running and its REST surface is up on the expected port (default 8765). The manager polls `http://localhost:8765/healthz` to check connectivity.

---

*Azeotrope Process Control -- v0.1.0*
*User Guide last updated: 2026-04-11*
