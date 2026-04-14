# Aspen DMC3 Builder -- Curve Operations & Model Manipulation Reference

Extracted from AspenTech DMC3 Builder V14 and DMCplus Model help documentation. This document captures every feature related to step-response curve manipulation for implementation in the Azeotrope APC stack.

---

## 1. Curve Operation Types

The Curve Operations dialog is accessed from the Master Model view via **Curve Operations > Add / Edit** in the ribbon, or via the right-click menu item **Curve Operations**. Operations are applied sequentially in a user-defined order (reorderable via Move Up / Move Down). A Preview pane shows both the Original and Result curves in real time.

### Operations on existing curves

| Operation | Parameters | What it does |
|-----------|-----------|--------------|
| **Add** | Source Model, Source Input, Source Output | Adds a source curve to the current curve |
| **Subtract** | Source Model, Source Input, Source Output | Subtracts a source curve from the current curve |
| **Gain** | Time to response (min), Steady-state gain | Draws a line from (time_to_response, 0) to (end, gain). Last 2 coefficients set equal to gain. Not for ramp variables. |
| **Gain Scale (GSCALE)** | Target gain | Multiplies all coefficients by (target_gain / existing_gain). Last 2 coeffs set to target. Not for ramps. |
| **Shift** | Time to shift (min) | Positive = shift right (insert leading zeros). Negative = shift left (repeat last coeff; for ramps, extrapolate slope). |
| **Multiplier (MULTIPLY)** | Factor | Multiplies all coefficients by a constant. Response always starts at 0. |
| **Rate** | Time to response (min), Slope (1/min) | From time_to_response, modifies remaining coefficients to produce a line with the specified slope. Works with ramp and steady-state. Tip: combine Zero + Rate + Shift to create a ramp. |
| **Rate Scale (RSCALE)** | Target slope | Scales all coefficients so the curve ends with the specified slope. Each coeff multiplied by (target_slope / existing_slope). |
| **First Order** | Delay (dead time), Time Constant, Gain | Replaces curve with K * exp(-theta*s) / (tau*s + 1). Not for ramps. |
| **Second Order** | Delay, Time Constant, Damping, Gain | Replaces with second-order response. Supports underdamped (oscillatory) and overdamped. Not for ramps. |
| **Lead Lag** | Lead-Lag Ratio (R), Lag time constant (T) | Applies (R*T*s + 1) / (T*s + 1) filter. Can only be applied to existing models. |
| **Rotate** | Target gain | Rotates entire curve around (0,0) to achieve specified steady-state gain. Calculates delta between current and desired gain, constructs a ramp from zero to that delta, adds to curve. Recommended for closed-level (AUTO/CASCADE) controllers. |
| **Smoothing** | Iterations (1-100), Dead time | Filters noisy curves. More iterations = more smoothing. Dead time can be auto-estimated or manually specified. |
| **Conversion** | Target order | Converts curve to a low-order parametric model. |

### Operations on blank cells (no existing curve)

| Operation | Parameters | What it does |
|-----------|-----------|--------------|
| **Replace** | Source Model, Source Input, Source Output | Copies a source curve into the empty cell |
| **Zero** | (none) | Sets all coefficients to 0.0 |
| **Unity** | (none) | Sets all coefficients to 1.0 |
| **First Order** | Delay, Time Constant, Gain | Generates a first-order step response |
| **Second Order** | Delay, Time Constant, Damping, Gain | Generates a second-order step response |
| **Convolute** | Source Model 1 (input→intermediate), Source Model 2 (intermediate→output) | Combines two related models. Result: TTSS = sum, Gain = product, Dead time = sum. |

---

## 2. Right-Click Context Menu

### ID Case Models view (on curve cells)

- Zoom In / Zoom Out / Reset Zoom
- Graphic Properties (customize line colors, styles, legend fonts)
- Identify (re-run identification)
- Show > Show Grid Lines
- Show > Show Scale Labels
- Copy Gains (clipboard, Excel-compatible format)
- Calculate Typical Moves
- Mask Selection / Unmask Selection

### Master Model view (on curve cells)

- Zoom In / Zoom Out / Reset Zoom
- Graphic Properties
- Identify
- Show: Grid Lines / Scale Labels
- **Copy** / **Paste** (curves to clipboard, paste into other locations)
- **Clear Contents** (sets selected curves to no model)
- **Get Curve...** (copy a curve from a source case model into the master)
- **Curve Operations** (opens the full Curve Operations dialog)
- Copy Gains (clipboard for Excel)
- Calculate Typical Moves
- Remove Collinearity Repairs

### MIMO (State Space) Model view

- Create Library Model
- Zoom In / Zoom Out
- Graphic Properties
- **Use Typical Moves** (toggle typical move scaling)
- **Initialize Typical Moves** (auto-calculate from dataset)
- **Transpose** (swap input/output axis orientation)

### MISO (Nonlinear) Model view

- Zoom In / Zoom Out
- Graphic Properties
- Show/Hide Gridlines
- Show/Hide Scale Labels
- **View Details...** (detailed model dialog for single cell)

---

## 3. Mask / Unmask

| Action | Effect |
|--------|--------|
| **Mask** | Shaded background; NOT transferred to master during Update Master |
| **Mask All** | Masks all curves in the case |
| **Unmask** | Removes mask from selected curves |
| **Mask Blanks** | Masks all empty cells (when a Grade filter is active) |
| **Include masked in prediction** | Checkbox -- when set, masked curves ARE included in predictions |

---

## 4. Lock / Unlock

- **Lock** (case model) -- makes read-only. Viewing, predictions, comparisons, sending to master, and reports are allowed. Editing, re-identifying, changing constraints/deadtimes/masking, transforms, and curve operations are NOT allowed.
- **Unlock** -- restores edit capability.
- **Lock** (master model individual cells) -- prevents gain changes during model update. Locked cells display camel-colored background.

---

## 5. Gain Constraints

| Constraint | Effect |
|-----------|--------|
| **(0) Zero** | Sets gain constraint to 0 |
| **(+1) Plus One** | Sets gain constraint to +1 |
| **(-1) Negative One** | Sets gain constraint to -1 |
| **Clear** | Removes gain constraint from selected curves |

These constrain the identification algorithm, not the runtime controller.

---

## 6. Typical Move / Unit Move

The **Typical Move** column appears in every model matrix view:

- **Set Typical Move Sizes** dialog: select tag, view current, enter new, or Calculate / Calculate All
- **Calculate Typical Moves** (right-click/ribbon): pick alternative dataset vectors for auto-computation
- **Initialize Typical Moves** (MIMO): select dataset to auto-set all at once
- **Use Typical Moves** toggle: switches plot display between unit-step and typical-move scaling

---

## 7. Library Curves (MIMO/State Space only)

Five parametric SISO model types via **State Space Library** or **Create Library Model**:

| Type | Parameters | Transfer Function |
|------|-----------|------------------|
| **First Order** | Gain, Time Constant, Delay | K * exp(-theta*s) / (tau*s + 1) |
| **Second Order** | Gain, Time Constant, Damping, Delay | Second-order with damping |
| **Lead Lag** | Lag time, Lead-Lag Ratio | (R*T*s + 1) / (T*s + 1) |
| **Pure Gain** | Gain, Dead time | K * exp(-theta*s) |
| **Pure Ramp** | Slope, Dead time | Integrating response |

---

## 8. Collinearity Analysis and RGA

- **Collinearity** (Case Models) -- Case Collinearity dialog with RGA for every 2x2 submatrix
- **Collinearity** (Master Model) -- Collinearity Repair Wizard (guided) or self-directed Collinearity Analysis dialog
- **Gain Matrix Analysis** (legacy Model tool) -- configurable 2x2, 3x3, 4x4. Scaling: LP/QP/Typical Moves/None. Condition threshold up to 1e10. Color-decorated results (up to 30 unique, 6 per cell).
- **Remove Collinearity Repairs** -- batch removes all curve ops flagged as collinearity results

---

## 9. Model Editing

| Feature | Description |
|---------|-------------|
| **Edit Gains** (FIR) | View/edit gain relationships between all I/O pairs |
| **Edit Gains** (MIMO) | View calculated and SS gains; Change Model Stability and Gain dialog |
| **Edit Nonlinear Gain** (MISO/BDN) | Edit SS gains for BDN nonlinear models |
| **Model Parameters** | Gain Multipliers, Time Constant Multipliers, Variable Deadtimes |
| **Coefficients** | Directly edit number of model coefficients |
| **Resample** | Rebuild model with a different sample period |
| **Ramp / Pseudo-Ramp** | Mark output variables as ramp (never reaches SS) or pseudo-ramp |

---

## 10. Curve Overrides

Via **Overrides > Model Curves**:

| Override | Background color | Effect |
|----------|-----------------|--------|
| **Ignore for MV Test** | Orange | Excluded from MV test calculations |
| **Ignore for App Test** | Light olive | Excluded from application test |
| **Prediction Only** | Cyan | Used for prediction only, not control |

Via **Overrides > Interlock**: configure interlock relationships for MV/CV pairs.

---

## 11. Model Import/Export

**Export formats:**
- DMC3/APC Model File (.dmc3model / .apcmodel)
- FIR Model File (.mdl / .mdl3)
- LSS Model File (state-space matrices)

**Import sources:**
- DMCplus models, ACES models, RMPCT (Honeywell) models
- Master model copies
- Linear state-space matrices
- DPA files (imported via curve operations)

---

## 12. Visual Features

| Feature | Description |
|---------|-------------|
| **Zoom In** | Double-click any cell for quick zoom |
| **Grade filter** | Show All / A Only / A+B / A+B+C |
| **Type filter** | Show All / FIR / Subspace |
| **Show Master Model** | Overlay master curves on case model for comparison |
| **Highlight Cases** | Select case in nav tree to highlight its curves |
| **Hide DVs** | Toggle disturbance variable columns |
| **Compare Models** | Side-by-side comparison dialog |
| **Compare Predictions** | Prediction comparison dialog |
| **Color coding** | Camel=locked, Green=nonlinear, Orange=Ignore MV, Olive=Ignore App, Cyan=Pred Only |
| **Tooltip on hover** | Shows gain, dead time, time constant, multiplier details |
| **Set Model Curve Range** | Define start/stop variables for display range |

---

*Extracted from AspenTech DMC3 Builder V14 and DMCplus Model V14.2 help documentation, April 2026.*
