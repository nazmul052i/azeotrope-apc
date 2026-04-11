# MPC Step-Test Identification Suite

**Azeotrope Process Control — Technical Reference**

---

## Overview

The MPC Step-Test Identification Suite is a three-module Python toolkit for identifying dynamic process models from plant step-test data and visualising them as step-response matrices — the standard representation used by DMC3, RMPCT, and other industrial Model Predictive Controllers.

The suite replaces the model-identification workflow typically performed inside AspenTech DMCplus Model, Honeywell Profit Design Studio, or similar proprietary platforms, providing full transparency into the mathematics and complete control over preprocessing, regularisation, and smoothing decisions.

```
┌──────────────────────────────────────────────────────────────┐
│                    step_ident_app.py                         │
│              PySide6 / pyqtgraph Desktop GUI                 │
│                                                              │
│   CSV Load → Tag Assignment → Data Conditioning → Identify   │
│                  → Step Response Matrix Plot                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────┐         ┌──────────────────────┐       │
│   │  fir_ident.py   │         │  control_model.py    │       │
│   │                 │         │                      │       │
│   │  DLS / COR /    │────────▶│  TF ⇌ SS ⇌ FIR      │       │
│   │  Ridge ident    │         │  Dead time, gain,    │       │
│   │  + smoothing    │         │  stability, ERA      │       │
│   └─────────────────┘         └──────────────────────┘       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Module 1 — `control_model.py`

### Purpose

A unified container for discrete-time process models in three canonical representations used across the APC industry:

| Representation | Symbol | Description |
|---|---|---|
| Transfer Function | `(num, den)` | Discrete polynomial ratio — compact for SISO |
| State-Space | `(A, B, C, D)` | Matrix quadruple — natural for MIMO, simulation, and observer design |
| Finite Impulse Response | `[G₀, G₁, …, G_{N-1}]` | Markov parameter sequence — the native format of DMC-family controllers |

### Conversion Graph

Every conversion returns a new immutable `ControlModel` instance. No in-place mutation.

```
          tf_to_ss (exact)
    TF ◄─────────────────────► SS
    │    ss_to_tf (exact)       │
    │                           │
    │  tf_to_fir               │  ss_to_fir (exact)
    │  (dimpulse)              │  (Markov expansion)
    │                           │
    ▼                           ▼
    FIR ◄──────────────────────
          fir_to_ss
          • shift (exact, high-order)
          • ERA   (reduced, balanced)
```

### Key Design Decisions

**Dimension tracking.** On first representation set, `(ny, nu)` is recorded. All subsequent conversions cross-check against these dimensions, catching shape mismatches at assignment time rather than deep inside a matrix multiply.

**D-matrix consistency.** The shift realisation correctly separates `D = G[0]` (direct feedthrough) from the delay chain stored in C. The original code folded `G[0]` into C and zeroed D, which produced correct simulations but broke any downstream code that expected the standard `y = Cx + Du` partition.

**ERA bounds enforcement.** The Eigensystem Realisation Algorithm requires `order ≤ (N-1) / 2` Markov parameters to fill both the H(0) and H(1) block-Hankel matrices. This is now validated before SVD, with an energy-retention warning when the truncation drops below 99%.

### APC-Specific Features

**`from_step_response(S, dt)`** — Converts DMC-style cumulative step-response coefficients into FIR Markov parameters via first-differencing. This is the bridge for importing `.mdl` or DMC3 RTE step-response data directly.

**`steady_state_gain()`** — Computes the DC gain matrix from whichever representation is available, preferring SS (via `C(I−A)⁻¹B + D`) for numerical accuracy, falling back to FIR summation or TF evaluation at `z = 1`.

**`fir_settling_index(tol)`** — Scans the cumulative FIR sum and returns the last index where the response has not yet settled within `tol` of the final gain. Directly useful for selecting DMC3 model length N.

**`is_stable()`** — Checks whether all eigenvalues of A lie inside the unit circle. Integrating or unstable models are flagged before they reach the controller design stage.

### Usage

```python
from control_model import ControlModel, from_fir, from_step_response

# From identified FIR coefficients
model = from_fir(result.fir, dt=60.0, name="CDU_TPA_MV2")

# From DMC3 step-response vector
model = from_step_response(s_coefficients, dt=60.0)

# Convert to state-space for simulation
model_ss = model.to_ss_from_fir(method="era", order=8)

# Check properties
print(model.steady_state_gain())
print(model.is_stable())
print(model.fir_settling_index(tol=0.01))
```

---

## Module 2 — `fir_ident.py`

### Purpose

MIMO FIR model identification from raw plant step-test data. This is the computational core — it takes historian-exported `u` (MV) and `y` (CV) arrays and returns a complete set of Markov parameters with diagnostics.

### Identification Methods

#### Direct Least Squares (DLS)

The standard approach for open-loop step tests. Constructs a block-Toeplitz regression matrix Φ from lagged input vectors and solves `Y = Φθ` via SVD-based least squares.

```
Φ[t,:] = [ u(t),  u(t−1),  …,  u(t−N+1) ]   (flattened across nu inputs)
Y[t,:]  = y(t)

θ = (Φ'Φ)⁻¹ Φ'Y    →    FIR coefficients
```

Best for clean, open-loop data with well-separated input moves. Sensitive to feedback — if the controller was active during the test, DLS estimates will be biased.

#### Correlation-Based (COR)

Solves `Ruu · θ = Ruy` where Ruu and Ruy are the auto-correlation and cross-correlation matrices. More tolerant of closed-loop data because the correlation structure partially decouples the feedback path.

Auto-regularises when Ruu is ill-conditioned (condition number > 10⁸) by adding a scaled identity term.

#### Ridge Regression (L2)

Adds Tikhonov regularisation to DLS: `θ = (Φ'Φ + αI)⁻¹ Φ'Y`. Essential when inputs are collinear — common in multi-MV simultaneous step tests where several MVs move together due to process constraints.

The regularisation parameter α is exposed in the GUI and defaults to 1.0. Higher values produce smoother but potentially biased estimates.

### Smoothing Pipeline

Raw FIR coefficients from regression are noisy, especially in the tail where the signal-to-noise ratio degrades. Three smoothing stages can be applied individually or as a sequential pipeline:

#### Stage 1 — Exponential Tail Decay

Beyond a configurable start fraction (default 60% of model length), coefficients are multiplied by a decaying exponential window. The time constant τ is estimated automatically by fitting a log-linear decay to the tail amplitudes, or can be set manually.

This enforces the physical expectation that impulse response coefficients of a stable process must decay to zero.

#### Stage 2 — Savitzky-Golay Filter

A local polynomial filter (default: window 11, order 3) applied per channel. Preserves the shape of genuine dynamics — peaks, inflections, inverse response — while removing high-frequency noise that the regression picks up from measurement noise.

#### Stage 3 — Asymptotic Projection

Beyond 75% of model length, coefficients are blended toward zero using a cosine taper. This ensures the identified model has a clean steady-state and prevents numerical artefacts from accumulating in the step-response tail.

The default "pipeline" mode applies all three in sequence: exponential → Savitzky-Golay → asymptotic.

### Diagnostics

Every identification produces a full `IdentResult` containing:

| Metric | Description |
|---|---|
| R² | Coefficient of determination per CV (fraction of variance explained) |
| RMSE | Root mean square error of one-step-ahead prediction |
| NRMSE | RMSE normalised by the range of the actual output |
| Ljung-Box Q | Portmanteau test for residual autocorrelation — a p-value below 0.05 indicates the residuals are not white, suggesting model structure is missing |
| Condition number | Of the regression matrix Φ — values above 10⁶ trigger a collinearity warning |
| Confidence intervals | Analytic ±z·SE bands on every FIR coefficient, derived from the residual variance and (Φ'Φ)⁻¹ diagonal |
| Settling index | Per-channel index where the step response reaches within 1% of its final value |

### Usage

```python
from fir_ident import identify_fir

# One-call identification
result = identify_fir(
    u, y,
    n_coeff=60,
    dt=60.0,
    method="dls",
    smooth="pipeline",
)

print(result.summary())
print(result.gain_matrix())
print(result.settling_index())

# Access raw and smoothed FIR
fir_raw = result.fir_raw    # before smoothing
fir     = result.fir         # after smoothing
step    = result.step        # cumulative step response
```

---

## Module 3 — `step_ident_app.py`

### Purpose

A PySide6 desktop application that wraps the identification engine in a visual workflow: load data, assign tags, configure parameters, run identification, and inspect the step-response matrix — all without writing code.

### Application Layout

```
┌────────────────────┬──────────────────────────────────────────┐
│                    │                                          │
│   DATA SOURCE      │   ┌──────────────────────────────────┐   │
│   [Load CSV]       │   │   Step Response Matrix           │   │
│   [Auto-Assign]    │   │                                  │   │
│                    │   │     MV0        MV1        MV2    │   │
│   ┌────────────┐   │   │  ┌────────┐ ┌────────┐ ┌──────┐ │   │
│   │ Tag  │Role │   │   │CV│        │ │        │ │      │ │   │
│   │──────│─────│   │   │0 │ S(k)   │ │ S(k)   │ │S(k)  │ │   │
│   │ TPA  │ MV  │   │   │  └────────┘ └────────┘ └──────┘ │   │
│   │ COT  │ MV  │   │   │  ┌────────┐ ┌────────┐ ┌──────┐ │   │
│   │ T301 │ CV  │   │   │CV│        │ │        │ │      │ │   │
│   │ P401 │ CV  │   │   │1 │ S(k)   │ │ S(k)   │ │S(k)  │ │   │
│   └────────────┘   │   │  └────────┘ └────────┘ └──────┘ │   │
│                    │   └──────────────────────────────────┘   │
│   IDENTIFICATION   │                                          │
│   Model Length: 60 │   ┌──────────────────────────────────┐   │
│   Sample: 60s      │   │   Raw Data   │  Diagnostics      │   │
│   Method: DLS      │   └──────────────────────────────────┘   │
│   Smooth: pipeline │                                          │
│                    │                                          │
│   [▶ IDENTIFY]     │                                          │
│                    │                                          │
└────────────────────┴──────────────────────────────────────────┘
```

### Workflow

#### 1. Load CSV

Accepts any CSV file exported from a process historian (IP.21, PHD, OSIsoft PI, DeltaV Continuous Historian). The loader auto-detects a datetime column in the first position and parses it as the index. All remaining columns are cast to numeric, with non-numeric values converted to NaN.

The tag table displays per-column statistics immediately: mean, standard deviation, and NaN percentage — giving a quick data-quality read before identification.

#### 2. Assign Tags

Each column is assigned a role via dropdown: MV, CV, DV, or Ignore. The "Auto-Assign" button provides a starting point by splitting columns into MVs (first half) and CVs (second half), which the user can then adjust.

The raw data tab shows time-series plots for up to 12 tags with linked x-axes for visual inspection of step-test quality.

#### 3. Configure Identification

All `IdentConfig` parameters are exposed in the left panel:

- **Model Length** — number of FIR coefficients (typically 30–120 depending on process dynamics and sample rate)
- **Sample Period** — must match the data's actual sample rate
- **Method** — DLS for open-loop, COR for closed-loop, Ridge for collinear inputs
- **Smoothing** — pipeline (recommended), or individual stages, or none
- **Ridge α** — regularisation strength (only relevant for Ridge method)
- **Detrend** — removes linear drift from each signal
- **Prewhiten** — applies first-difference filtering to suppress low-frequency disturbances
- **Outlier Clip** — threshold in standard deviations for outlier removal (default 4σ)

#### 4. Data Conditioning

Before identification, the `DataConditioner` automatically:

1. Forward-fills NaN gaps (common in historian-compressed data)
2. Back-fills any leading NaN values
3. Clips outliers beyond the configured σ threshold and interpolates the gaps
4. Verifies no NaN values remain

This replicates the data conditioning that AspenTech DMCplus Model performs internally, but with full visibility into what was changed and why (logged to the diagnostics tab).

#### 5. Identification

Runs in a background `QThread` to keep the GUI responsive during large identifications. The progress bar indicates activity, and the status bar shows phase messages from the worker.

#### 6. Results

**Step Response Matrix** — the primary output. Each cell in the MV-column × CV-row grid shows:

- The cumulative step response `S(k) = Σ G(i)` as a solid trace
- 95% confidence bands as a shaded fill region
- A horizontal zero-reference dashed line
- The steady-state gain `K` annotated at the final coefficient

**Diagnostics tab** — shows the full text summary including the gain matrix, per-channel R²/RMSE/NRMSE, Ljung-Box test results, and settling indices in both samples and seconds.

### Visual Design

The application uses a DeltaV Live Silver-inspired dark theme with the ISA-101 colour philosophy: dark backgrounds for extended operator use, blue accents for interactive elements, green for confirmations, and muted tones for secondary information. Plot backgrounds are near-black for maximum trace contrast.

---

## Data Flow Summary

```
Historian CSV
     │
     ▼
 ┌──────────────────────┐
 │  step_ident_app.py   │
 │                      │
 │  DataConditioner     │──── ffill, outlier clip, interpolate
 │       │              │
 │       ▼              │
 │  FIRIdentifier       │──── DLS / COR / Ridge regression
 │  (fir_ident.py)      │     + exponential / savgol / asymptotic smoothing
 │       │              │
 │       ▼              │
 │  IdentResult         │──── FIR, step response, CI, R², RMSE, Ljung-Box
 │       │              │
 │       ▼              │
 │  StepResponseMatrix  │──── pyqtgraph grid: MV cols × CV rows
 │                      │
 │       │              │
 │       ▼ (optional)   │
 │  ControlModel        │──── convert to SS / TF for simulation or export
 │  (control_model.py)  │
 └──────────────────────┘
```

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| Python | ≥ 3.10 | Runtime |
| NumPy | ≥ 1.24 | Array operations, linear algebra |
| SciPy | ≥ 1.10 | Signal processing, SVD, statistics |
| pandas | ≥ 2.0 | CSV loading, data conditioning |
| PySide6 | ≥ 6.5 | Qt GUI framework |
| pyqtgraph | ≥ 0.13 | High-performance plotting |

No dependency on statsmodels, scikit-learn, or AspenTech/Honeywell SDKs. The Ljung-Box test is implemented natively to keep the dependency footprint minimal.

---

## File Manifest

| File | Lines | Description |
|---|---|---|
| `control_model.py` | ~450 | Model representation container with TF/SS/FIR conversions |
| `fir_ident.py` | ~600 | MIMO FIR identification engine with smoothing and diagnostics |
| `step_ident_app.py` | ~700 | PySide6 desktop application |

---

## Roadmap

Planned extensions for MPC Studio integration:

- **DMC3 `.mdl` import** — parse binary model files and load directly into `ControlModel`
- **IP.21 / OPC-UA live data pull** — replace CSV loading with direct historian queries
- **Multi-experiment merging** — combine step-test windows with different MV excitations
- **Subspace identification (N4SID)** — alternative to FIR for state-space models directly
- **Export to DMC3 / RMPCT format** — write identified models back to controller-native formats
- **Batch mode** — command-line interface for automated identification in CI/CD pipelines

---

*Azeotrope Process Control — Proprietary and Confidential*
