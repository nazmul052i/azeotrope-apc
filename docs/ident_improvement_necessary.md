# APC Ident -- Improvement Roadmap

Gap analysis between Aspen DMC3 Model and our apc_ident application.
Reference: `D:\office_documents02162026\dev\AspenTechAPC\Model\HtmlHelp`

---

## What We Have (Fully or Partially Implemented)

| Feature | DMC3 Equivalent | apc_ident Status |
|---|---|---|
| CSV/Parquet import | CSV/Excel/historian | Done |
| Datetime auto-parse | Yes | Done |
| Trend visualization (stacked, linked X) | Vector Plot View | Done |
| Segment marking (good slices) | Good/Bad slices | Done |
| Excluded ranges (bad slices) | Bad slice marking | Done |
| FIR identification (DLS) | FIR algorithm | Done (DLS/COR/Ridge) |
| Step response matrix plot | Model Plot View | Done |
| Gain matrix display | Gain matrix | Done |
| Confidence bands (95% CI) | Uncertainty bands | Done |
| Holdout validation | Prediction view | Done |
| R², RMSE, NRMSE metrics | Model quality | Done |
| Ljung-Box residual test | — | Done (we have more) |
| Model export (.apcmodel HDF5) | .mdl/.mdlx export | Done |
| Project save/load (.apcident YAML) | Project files | Done |
| Cutoff detection | Data conditioning | Done (Tier 1) |
| Flatline detection | Data conditioning | Done (Tier 1) |
| Spike detection | Data conditioning | Done (Tier 1) |
| Bad data replacement (interp/hold/mean) | Interpolated slices | Done (Tier 1) |
| Steady-state detection | SSD | Done (Tier 1) |
| Resampling with analysis | Resampling | Done (Tier 1) |
| Tag-based exclusion rules | Slice rules | Done (Tier 2) |
| Dynamic input filtering | Data filtering | Done (Tier 2) |
| Output transforms (log, Box-Cox, etc.) | 8 transform types | Done (Tier 2) |
| Ribbon toolbar for conditioning | Toolbar | Done |
| Right-click context menu on trends | Pop-up menus | Done |
| Visual overlays (bad data, cutoffs, SSD) | Plot overlays | Done |

---

## What We're Missing

### P1 — Core Identification (Must Have)

#### 1. Subspace Identification (N4SID)
- **DMC3**: State-space MIMO, automatic model order selection, CV grouping (related / one-per-group / all-in-one), handles integrating CVs, inverse response, non-minimum phase, stiff dynamics, deadtime handling, GC data, oversampling ratio
- **Complexity**: High
- **Why it matters**: Flagship feature that differentiates DMC3 from old DMCplus. Handles simultaneous MV moves and MIMO dynamics that FIR cannot

#### 2. Curve Operations (18 operations)
- **DMC3 operations on existing curves**:
  - `ADD` — add another curve
  - `SUBTRACT` — subtract another curve
  - `GAIN` — apply gain multiplier
  - `GSCALE` — gain scaling
  - `SHIFT` — time shift (deadtime adjustment)
  - `MULTIPLY` — multiply by scalar
  - `RATE` — rate of change
  - `RSCALE` — rate scaling
  - `FIRSTORDER` — first-order dynamics
  - `SECONDORDER` — second-order dynamics
  - `LEADLAG` — lead-lag compensation
  - `ROTATE` — rotation operation
- **DMC3 operations for creating curves**:
  - `REPLACE` — replace with another curve
  - `ZERO` — zero gain curve
  - `UNITY` — unity gain curve
  - `FIRSTORDER` — first-order response
  - `SECONDORDER` — second-order response
  - `CONVOLUTE` — convolute two curves
- **Complexity**: Medium
- **Why it matters**: Every DMC3 engineer uses SHIFT, GAIN, FIRSTORDER to manually shape step response curves. Without this, model assembly is impossible

#### 3. Model Assembly
- **DMC3**: Select best curve for each MV-CV pair from multiple identification runs into a final assembled model. Convoluted model assembly. Model matrix definition (MV x CV grid)
- **Complexity**: Medium
- **Why it matters**: The final step before deploying a controller — picking the best identified response for each channel

#### 4. Calculated Vectors (Formula Editor)
- **DMC3**: Create derived tags from algebraic expressions (e.g. `TI101 + 15*(P_ref - pressure)`), built-in math/stats/timeseries functions, formula test mode, multiple vector creation from single formula, formula sharing/reuse
- **Complexity**: Medium
- **Why it matters**: Engineers need derived variables — pressure-compensated temperatures, ratios, rates of change, delta-T across trays

#### 5. Cross-Correlation Analysis
- **DMC3**: MV auto-correlation, MV-MV cross-correlation, time lag analysis (-100 to +100 shifts), quality zones (<30% ideal, 30-50% acceptable, >80% poor), periodic signal detection, feed-forward signal drift identification, PRBS/GBN quality assessment
- **Complexity**: Medium
- **Why it matters**: Essential for evaluating step test quality before running identification. Tells the engineer if the test data is good enough

---

### P2 — Model Quality & Analysis

#### 6. Model Uncertainty Analysis
- **DMC3**: Frequency-domain Bode magnitude plots with uncertainty bands, time-domain uncertainty estimation, ±2σ (95%) and ±1σ (68%) confidence bounds, A/B/C/D uncertainty grading, steady-state gain uncertainty, dynamic uncertainty, model significance plotting, signal-to-noise ratio analysis
- **Complexity**: High
- **Why it matters**: Tells the engineer which models are trustworthy and which need more test data

#### 7. Gain Matrix Analysis
- **DMC3**: Condition number analysis, colinearity detection, 2x2/3x3/4x4 sub-matrix analysis, LP/QP/Typical Moves scaling algorithms, graphical decoration highlighting problematic pairs
- **Complexity**: Medium
- **Why it matters**: Identifies which MV-CV pairs create controllability problems before deploying to the controller

#### 8. Multiple Trials per Case
- **DMC3**: Run FIR with different parameters (TTSS, smoothing, n_coeff) in one case, compare trials side-by-side in model plot
- **Complexity**: Low
- **Why it matters**: Engineers routinely try 3-5 parameter sets per case to find the best fit

#### 9. Bad Interpolated Slices
- **DMC3**: Mark bad ranges that get linearly interpolated rather than excluded (different from exclude which removes rows entirely)
- **Complexity**: Low
- **Why it matters**: Preserves data continuity for the FIR regression while removing bad measurements

---

### P3 — Data Management & Workflow

#### 10. Vector Lists / Case Lists / Model Lists
- **DMC3**: Organize vectors, cases, and models into named lists for batch operations and project organization
- **Complexity**: Medium
- **Why it matters**: Large projects (50+ MVs, 30+ CVs) need organizational structure

#### 11. Batch Case Execution
- **DMC3**: Run a list of identification cases sequentially with progress monitoring and error handling
- **Complexity**: Low
- **Why it matters**: Running 30+ MISO cases one-at-a-time is tedious

#### 12. Piece-Wise Linear Transform (PWLN)
- **DMC3**: Multi-segment linear transform for valve nonlinearities (breakpoints + slopes)
- **Complexity**: Low
- **Why it matters**: Common for equal-percentage valves where the gain changes with operating point

#### 13. Ramp / Pseudoramp CV Types
- **DMC3**: CV integrator handling — Ramp removes linear trend, Pseudoramp for slow integrators
- **Complexity**: Medium
- **Why it matters**: Level controllers, tank inventories, and slow temperature integrators are everywhere in refineries

#### 14. Typical Move Sizes
- **DMC3**: Per-MV "typical move" value used to scale step response display and normalize the gain matrix
- **Complexity**: Low
- **Why it matters**: Makes step response plots physically meaningful ("what happens when I move this valve 5%")

---

### P4 — Visualization & Reporting

#### 15. Model Plot View (Multi-Model Overlay)
- **DMC3**: Compare multiple models on same axes, tab-based model navigation, curve operation indicators (white/blue triangles), page navigation for large models
- **Complexity**: Medium
- **Why it matters**: Comparing FIR vs subspace, or different trial parameters, on the same plot

#### 16. Report View
- **DMC3**: Tabular text reports with filtering, searching, custom columns, print-ready formatting
- **Complexity**: Low
- **Why it matters**: Documentation and audit trail for the identification work

#### 17. Print / Export Plots
- **DMC3**: Print preview, header/footer customization, margins, page numbering, plot export to image
- **Complexity**: Low
- **Why it matters**: Engineers need to put plots in reports for management review

#### 18. Project Documentation Generator
- **DMC3**: Auto-generate complete project history document — full record of how the final model was produced
- **Complexity**: Low
- **Why it matters**: Regulatory and audit requirements in refining/petrochemical

---

### P5 — Import/Export Interop

#### 19. DMC .vec/.dep/.ind Import
- **DMC3**: Read AspenTech single-tag vector files (one tag per file with metadata header)
- **Complexity**: Low
- **Why it matters**: Existing DMC3 users have years of test data in these formats

#### 20. .mdl / .mdlx / .mdl3 Export
- **DMC3**: Export models in DMC3-compatible formats for direct deployment to DMCplus/DMC3 controllers
- **Complexity**: Medium
- **Why it matters**: Interoperability with existing AspenTech infrastructure

#### 21. DMCplus Project Conversion
- **DMC3**: Import legacy DMCplus projects and convert to DMC3 format
- **Complexity**: Medium
- **Why it matters**: Migration path for existing installations

#### 22. Collect File / Vector Import List
- **DMC3**: Batch vector import from historian using tag list files
- **Complexity**: Low
- **Why it matters**: Automating data collection for large tag counts

---

### P6 — Advanced

#### 23. Linear / Parabolic Valve Transforms
- **DMC3**: Valve-specific nonlinearity compensation (linear valve %, parabolic valve %)
- **Complexity**: Low
- **Why it matters**: Common valve characteristic compensation

#### 24. Subspace Expert Mode
- **DMC3**: Advanced preprocessing — Differencing, DoubleDiff, zero-meaning, oversampling ratio control, advanced parameter tuning
- **Complexity**: Medium
- **Why it matters**: Power users tuning difficult identifications (e.g. noisy GC data, slow integrators)

#### 25. UPID (Univariate Parameter ID)
- **DMC3**: Simplified single-variable parametric identification (FOPDT, SOPDT curve fitting)
- **Complexity**: Medium
- **Why it matters**: Quick first-pass identification for simple loops before running full MIMO

---

## Recommended Implementation Order

### Phase A — Make Model Assembly Work (P1 #2, #3, #8, #14)
Curve operations + model assembly + multiple trials + typical moves.
This completes the core workflow: identify → shape curves → assemble final model.

### Phase B — Step Test Quality (P1 #5, P2 #7)
Cross-correlation analysis + gain matrix analysis.
Engineers can evaluate test data quality and model controllability.

### Phase C — Calculated Vectors & Integrators (P1 #4, P3 #13)
Formula editor + ramp/pseudoramp CV handling.
Handles derived variables and integrating processes.

### Phase D — Model Quality (P2 #6, P2 #9)
Model uncertainty analysis + bad interpolated slices.
Full confidence assessment of identified models.

### Phase E — Subspace Identification (P1 #1, P6 #24)
N4SID + expert mode.
The flagship MIMO identification capability.

### Phase F — Workflow & Interop (P3 #10-12, P4 #15-18, P5 #19-22)
Batch execution, reporting, DMC format import/export.
Production workflow for large projects.
