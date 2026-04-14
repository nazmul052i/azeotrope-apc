# APC Architect Tutorial: Controller Configuration and Deployment

**Cumene Hot Oil Heater -- From Identified Model to Running Controller**

This tutorial walks you through the complete APC Architect workflow:
importing an identified model from APC Ident, configuring the
controller, tuning the three optimization layers, writing custom
calculations, running simulations, and deploying to a live process via
OPC UA.

We continue with the cumene hot oil heater example from the
[APC Ident Tutorial](ident_tutorial.md). You should have a validated
model bundle (`.apcmodel` file) before starting this tutorial.

**Prerequisites:** Completion of the APC Ident tutorial (or an
equivalent model bundle). Basic understanding of MPC concepts (what
CVs, MVs, setpoints, and constraints mean). No prior APC Architect
experience required.

---

## Table of Contents

1. [Getting Started](#chapter-1-getting-started)
2. [Understanding the Layout](#chapter-2-understanding-the-layout)
3. [Configuration](#chapter-3-configuration)
4. [Importing a Model](#chapter-4-importing-a-model)
5. [Layer 1 Tuning](#chapter-5-layer-1-tuning)
6. [Layer 2 Optimization](#chapter-6-layer-2-optimization)
7. [Layer 3 NLP](#chapter-7-layer-3-nlp)
8. [Calculations](#chapter-8-calculations)
9. [Simulation](#chapter-9-simulation)
10. [Deployment](#chapter-10-deployment)
11. [Recipes and Version Control](#chapter-11-recipes-and-version-control)
12. [Troubleshooting](#chapter-12-troubleshooting)

---

## Chapter 1: Getting Started

### Launching APC Architect

APC Architect is launched from the APC Launcher or directly from the
command line:

```
python -m apps.apc_architect
```

Or, if you have the launcher running, click the **Architect** card.

When APC Architect starts with no project loaded, you see the
**Backstage Screen** -- a landing page with three main options:

### The Backstage Screen

The backstage screen is your starting point. It offers:

**Action Cards (top row):**

- **New Project** -- Creates a blank controller project with default
  settings. You will import a model and configure variables from
  scratch.
- **Import Model Bundle** -- Opens a file dialog to select an
  `.apcmodel` file exported from APC Ident. This creates a new project
  and auto-populates it with the model's variables. This is the most
  common starting path.
- **Open Project** -- Opens an existing `.apcproj` file.

**Process Templates (below action cards):**

Quick-start templates for common process units (CSTR, distillation
column, boiler, heater). Each template pre-configures sample time and
variable structure. Templates are useful for learning but most real
projects start from an imported model bundle.

**Recent Projects (right side):**

A list of recently opened projects. Click any card to re-open that
project.

> **Tip:** If you have just completed model identification in APC Ident,
> the fastest way to start is to click **Import Model Bundle** and
> select the `.apcmodel` file you exported. APC Architect will create
> the project, populate all MVs and CVs, and build the plant model
> automatically.

### Creating a New Project

For this tutorial, we will create a project by importing the cumene
heater model bundle.

1. Click **Import Model Bundle** on the backstage screen (or use
   File > Import Model Bundle, Ctrl+I).

2. Navigate to the directory where you saved the model bundle from APC
   Ident. Select `cumene_hotoil_heater.apcmodel`.

3. APC Architect reads the bundle and:
   - Creates MV entries for FCV-410.SP, SC-400.SP, and FCV-411.SP.
   - Creates CV entries for XI-490.PV, TIT-400.PV, TIT-402.PV,
     TIT-412.PV, XI-410.PV, and AIT-410.PV.
   - Builds the state-space plant model from the bundle's ERA
     realization.
   - Sets the controller name from the bundle name.

4. A confirmation dialog shows the imported model details:
   - Bundle name
   - MV and CV tag lists
   - State dimension (ERA order)

5. You are now in the main workspace with the sidebar showing the five
   workflow steps.

6. Save the project immediately: File > Save As (Ctrl+Shift+S), and
   choose a location like
   `examples/cumene_hotoil_heater_apc.apcproj`.

> **Tip:** Always save before making major configuration changes. APC
> Architect will prompt you to save unsaved changes when you close the
> window or open a different project.

---

## Chapter 2: Understanding the Layout

### The Main Window

The APC Architect main window has three regions:

**Sidebar (left, 200px wide):**

The sidebar shows the workflow steps and acts as the primary navigation.
At the top is the "APC ARCHITECT" branding with the subtitle "Controller
Configuration Studio." Below that is the WORKFLOW section with five
steps:

| Step | Icon | Label | Keyboard | Purpose |
|------|------|-------|----------|---------|
| 1 | &#x2630; | Configure | Ctrl+1 | Variables, limits, feedback filters, subcontrollers |
| 2 | &#x2699; | Optimize | Ctrl+2 | Layer 1 QP, Layer 2 LP/QP, Layer 3 NLP tuning |
| 3 | &#x0192; | Calculate | Ctrl+3 | Pre/post-MPC Python calculation scripts |
| 4 | &#x25B6; | Simulate | Ctrl+4 | Interactive closed-loop what-if simulation |
| 5 | &#x26A1; | Deploy | Ctrl+5 | OPC UA runtime, IO tags, online validation |

Click any step to navigate to it. The current step is highlighted with
a blue left border and bold text. Steps you have visited are marked with
a green dot; unvisited steps show a gray dot.

**Content Area (center/right):**

The main content area shows the panel for the currently selected
workflow step. Each panel has its own sub-tabs, tables, and controls.

**Status Bar (bottom):**

Shows the project name, unsaved changes indicator (*), and status
messages.

### Sidebar Context Menus

Right-click any sidebar step to access quick actions:

- **Configure (right-click):** Import Model Bundle, Add MV, Add CV.
- **Optimize (right-click):** Auto-Tune Layer 1, Apply to Simulator.
- **Simulate (right-click):** Step Simulation, Reset Simulation.
- **Deploy (right-click):** Connect OPC UA, Deploy Controller.

### File Menu

The File menu provides:

| Action | Shortcut | Description |
|---|---|---|
| New Project | Ctrl+N | Create a blank project |
| Open Project | Ctrl+O | Open an existing `.apcproj` file |
| Open Recent | -- | List of recently opened projects |
| Save | Ctrl+S | Save the current project |
| Save As | Ctrl+Shift+S | Save to a new file |
| Import Model Bundle | Ctrl+I | Import `.apcmodel` from APC Ident |
| Reveal in File Manager | -- | Open the project folder in Explorer |
| Exit | Ctrl+Q | Close the application |

### View Menu

The View menu provides keyboard shortcuts to jump directly to any
workflow step (Ctrl+1 through Ctrl+5).

---

## Chapter 3: Configuration

### Navigating to the Configure Tab

Click **Configure** in the sidebar (or press Ctrl+1). The Configuration
panel has three sub-tabs:

- **Summary** -- read-only dashboard of the controller configuration.
- **Feedback Filters** -- per-CV disturbance filter settings.
- **Subcontrollers** -- variable grouping configuration.

### Summary View

The Summary view shows a read-only overview of your controller:

**Application section:**

| Field | Value (example) |
|---|---|
| Application Name | Cumene Hotoil Heater |
| Description | -- |
| Plant Model Type | StateSpacePlant |
| Sample Time | 1 min |
| Prediction Horizon | 60 steps |
| Control Horizon | 5 steps |
| Model Horizon | 150 steps |
| Layer 3 RTO | Disabled |

**Variable Counts section:**

| Field | Value |
|---|---|
| Manipulated Variables | 3 |
| Disturbance Variables | 0 |
| Controlled Variables | 6 |
| Subcontrollers | 1 |

**Subcontrollers table:** Lists each subcontroller with its assigned
MV/DV/CV counts and criticality flag.

**Feedback Filters Summary table:** Lists each CV with its current
filter type and intermittent flag.

> **Tip:** The Summary view is the first place to look when opening a
> project you have not worked on recently. It tells you the current
> state of the controller at a glance.

### Variable Properties

Variable properties (tag name, description, units, limits, steady-state
value, weight, setpoint) are set during model import and can be
modified in the Simulation tab's variable tables. The Configuration tab
provides specialized views for feedback filters and subcontrollers.

To edit basic variable properties (limits, setpoint, weight):

1. Navigate to the Simulate tab (Ctrl+4).
2. Click on the cell you want to edit (editable cells have a cream
   background).
3. Type the new value and press Enter.

The following properties are commonly adjusted:

**For CVs:**

| Property | Column | Description |
|---|---|---|
| Operator Lo | Operator Lo | Lower operating limit |
| Operator Hi | Operator Hi | Upper operating limit |
| Control Weight | Control Weight | Q weight for Layer 1 |
| SS Lo Rank | SS Lo Rank | Priority for lower bound |
| SS Hi Rank | SS Hi Rank | Priority for upper bound |

**For MVs:**

| Property | Column | Description |
|---|---|---|
| Operator Lo | Operator Lo | Lower operating limit |
| Operator Hi | Operator Hi | Upper operating limit |
| Move Suppression | Move Suppression | R weight for Layer 1 |
| Max Move | Max Move | Hard limit on move size |
| LP Cost | LP Cost | Economic cost for Layer 2 |
| Cost Rank | Cost Rank | Priority for Layer 2 LP |

### Feedback Filters

Click the **Feedback Filters** sub-tab. This view shows a table with
one row per CV and the following columns:

| Column | Description | Editable |
|---|---|---|
| CV Tag | Tag name | No |
| Description | Variable name | No |
| Units | Engineering units | No |
| Full Feedback | Radio button for full feedback mode | Yes |
| First Order | Radio button for first-order filter | Yes |
| Moving Average | Radio button for moving average filter | Yes |
| Intermittent | Checkbox for intermittent measurements | Yes |
| Pred Error Lag | Filter time constant (minutes) | Yes |
| Pred Err Horizon | Moving average window (steps) | Yes |
| Rotation Factor | Ramp variable rotation (0--1) | Yes |

For each CV, select one filter type by clicking the corresponding radio
button. The three options are mutually exclusive.

**For the cumene heater, recommended settings:**

| CV | Filter | Pred Error Lag | Rationale |
|---|---|---|---|
| XI-490 (O2) | First Order | 5 min | Analyzer -- moderate noise |
| TIT-400 (outlet) | Full Feedback | -- | Clean temperature measurement |
| TIT-402 (bridgewall) | Full Feedback | -- | Clean temperature measurement |
| TIT-412 (coil) | Full Feedback | -- | Clean temperature measurement |
| XI-410 (draft) | First Order | 3 min | Pressure -- some noise |
| AIT-410 (CO) | First Order | 10 min | Analyzer -- noisy measurement |

> **Common Mistake:** Using Full Feedback on a noisy analyzer CV. The
> controller will chase the noise, causing MV oscillation. Always use a
> First Order filter with a prediction error lag of 5--10 minutes for
> analyzer measurements.

The **Apply Full Feedback to All** button at the bottom sets all CVs to
Full Feedback. This is a quick starting point for clean measurement
environments.

### Subcontrollers

Click the **Subcontrollers** sub-tab. By default, all variables are
assigned to a single subcontroller called "Main."

For a small controller like the cumene heater (3 MV, 6 CV), a single
subcontroller is sufficient. For larger controllers (>15 variables),
consider partitioning into subcontrollers based on physical plant
sections.

To create a subcontroller:

1. Click **Add Subcontroller**.
2. Enter a name (e.g., "Combustion") and description.
3. Set the **Critical** checkbox if this subcontroller must be running
   for the overall controller to operate.
4. Assign variables by selecting them in the Simulation tab and
   changing their Subcontroller column.

For now, leave the default single-subcontroller configuration.

> **Tip:** Subcontrollers are more relevant for large controllers (10+
> MVs, 20+ CVs). For the cumene heater example, a single subcontroller
> is the right choice.

---

## Chapter 4: Importing a Model

### Importing from APC Ident

If you did not import the model bundle during project creation (Chapter
1), you can import it at any time:

1. Navigate to any tab (Configuration or Simulation work well).
2. File > Import Model Bundle (Ctrl+I).
3. Select the `.apcmodel` file.
4. APC Architect reads the bundle and populates the configuration.

### What Gets Auto-Populated

When you import a model bundle, the following are automatically set:

| Setting | Source | Value |
|---|---|---|
| MV tags | Bundle `mv_tags` | FCV-410.SP, SC-400.SP, FCV-411.SP |
| CV tags | Bundle `cv_tags` | XI-490.PV, TIT-400.PV, ... |
| MV steady-state | Bundle `u0` | Operating point during step test |
| CV steady-state | Bundle `y0` | Operating point during step test |
| Plant model (A, B, C, D) | Bundle ERA realization | State-space matrices |
| Controller name | Bundle name | "Cumene Hotoil Heater" |
| Sample time | Project setting | Retained from project (not from bundle) |

### What Is NOT Auto-Populated

You still need to configure:

| Setting | Where | Action needed |
|---|---|---|
| Operating limits (lo/hi) | Simulation tab | Set from process knowledge |
| Engineering limits | Simulation tab | Set from instrument ranges |
| Validity limits | Deployment tab | Set from sensor specs |
| CV weights (Q) | Optimize tab, Layer 1 | Auto-tune or set manually |
| MV move suppression (R) | Optimize tab, Layer 1 | Auto-tune or set manually |
| MV rate limits | Simulation tab, Max Move col | Set from valve specs |
| CV setpoints | Simulation tab | Set from operating targets |
| Economic costs (LP Cost) | Simulation tab or Optimize tab | Set from economics |
| Preferences (opt type) | Simulation tab or Optimize tab | Set from strategy |
| Feedback filters | Configure tab, Feedback Filters | Set from measurement quality |

> **Common Mistake:** Assuming the model bundle provides operating
> limits. It does not. The model bundle contains the *operating point*
> during the step test (where the process was at steady state), not the
> *limits* on where the process should operate. You must set limits from
> your process knowledge.

### Verifying the Plant Model

After importing, verify the model is correct:

1. Go to the **Optimize** tab (Ctrl+2).
2. Click through to **Step 4 -- Evaluate Strategy** in the Layer 2
   Smart Tune sidebar.
3. Inspect the **Gain Matrix**. Each cell shows the steady-state gain
   $$G_{ij} = \partial CV_i / \partial MV_j$$. Green cells indicate
   positive gain; red cells indicate negative gain.

For the cumene heater, you should see:

| | FCV-410 (fuel) | SC-400 (damper) | FCV-411 (air) |
|---|---|---|---|
| XI-490 (O2) | Negative | Positive | Positive |
| TIT-400 (outlet) | Positive | Small | Small |
| TIT-402 (bridgewall) | Positive | Small | Small |
| TIT-412 (coil) | Positive | Small | Small |
| XI-410 (draft) | Small | Positive | Small |
| AIT-410 (CO) | Negative | Positive | Positive |

The signs make physical sense:
- More fuel (FCV-410 up) decreases O2, increases temperatures, and
  decreases CO.
- More damper opening (SC-400 up) increases draft and O2, and increases
  CO (more air dilution).

If the signs are wrong, the model may have incorrect tag assignments.
Return to APC Ident and verify.

> **Tip:** The gain matrix is the single best diagnostic for model
> correctness. If a gain sign is wrong, the controller will drive the
> MV in the wrong direction. Always check the gain matrix after
> importing a model.

---

## Chapter 5: Layer 1 Tuning

### Navigating to the Optimize Tab

Click **Optimize** in the sidebar (or press Ctrl+2). The Optimize panel
has a tab bar at the top with three pages:

- **Layer 3 (NLP)** -- Nonlinear re-linearization and RTO settings.
- **Layer 2 (LP)** -- Smart Tune wizard for steady-state optimization.
- **Layer 1 (QP)** -- Per-variable weights, horizons, and move
  suppression.

Click the **Layer 1 (QP)** tab.

### Setting Horizons

At the top of the Layer 1 page, three spin boxes control the horizons:

| Horizon | Spin box | Recommended value (cumene heater) |
|---|---|---|
| Prediction Horizon (P) | Steps | 60 |
| Control Horizon (M) | Steps | 5 |
| Model Horizon (N) | Steps | 150 |

For the cumene heater at $$T_s = 1$$ min:

- The slowest channel (bridgewall temperature) settles in about 90
  minutes, so $$P = 60$$ gives adequate foresight.
- $$M = 5$$ provides 5 independent future moves, which is sufficient for
  this 3-MV system.
- $$N = 150$$ captures the full step response with margin.

> **Common Mistake:** Setting the model horizon (N) shorter than the
> prediction horizon (P). The system requires $$P \leq N$$. If $$N < P$$,
> step response coefficients beyond $$N$$ are extrapolated as constant,
> which may degrade prediction accuracy.

### CV Tuning Table

The CV tuning table has one row per CV with the following columns:

| Column | Editable | Description |
|---|---|---|
| Tag | No | CV tag name |
| Description | No | CV description |
| Q Weight | Yes (cream) | CV error weight for the QP objective |
| Concern Lo | Yes (cream) | Soft constraint stiffness (lower bound) |
| Concern Hi | Yes (cream) | Soft constraint stiffness (upper bound) |
| Noise (std) | Yes (cream) | Simulation noise standard deviation |
| Status | No | "OK" or error indicator |

**Setting Q weights:**

The Q weight determines how aggressively the controller tracks each
CV's setpoint. Higher weight = tighter tracking. The auto-tune formula
is:

$$
Q_i = \frac{100}{(\text{eng\_hi}_i - \text{eng\_lo}_i)^2}
$$

This normalizes weights so that all CVs contribute equally to the
objective when they deviate by the same fraction of their engineering
range. You can then adjust individual weights up or down based on
relative importance.

For the cumene heater:

| CV | Engineering range | Auto-tune Q | Adjusted Q |
|---|---|---|---|
| XI-490 (O2, 0--10%) | 10 | 1.0 | 1.0 |
| TIT-400 (outlet, 500--900 degF) | 400 | 0.000625 | 0.001 |
| TIT-402 (bridgewall, 500--1200 degF) | 700 | 0.000204 | 0.0005 |
| TIT-412 (coil, 400--800 degF) | 400 | 0.000625 | 0.001 |
| XI-410 (draft, -2--2 inH2O) | 4 | 6.25 | 3.0 |
| AIT-410 (CO, 0--200 ppm) | 200 | 0.0025 | 0.001 |

We increased the outlet temperature (TIT-400) weight slightly because
it is the primary product quality variable.

### MV Tuning Table

The MV tuning table has one row per MV:

| Column | Editable | Description |
|---|---|---|
| Tag | No | MV tag name |
| Description | No | MV description |
| Move Suppress (R) | Yes (cream) | Move suppression weight |
| Max Move | Yes (cream) | Maximum move per sample period |
| Status | No | "OK" or error indicator |

**Setting move suppression:**

The auto-tune formula computes R from the rate limit:

$$
R_q = \frac{0.1}{(\text{rate\_limit}_q)^2}
$$

For the cumene heater:

| MV | Rate limit | Auto-tune R | Adjusted R |
|---|---|---|---|
| FCV-410 (fuel, 2%/min) | 2 | 0.025 | 0.05 |
| SC-400 (damper, 3%/min) | 3 | 0.011 | 0.02 |
| FCV-411 (air, 3%/min) | 3 | 0.011 | 0.02 |

We doubled the auto-tune values to start with a more conservative
(smoother) controller. We will refine these in simulation.

### Auto-Tune

Rather than setting each value manually, click the
**Auto-Tune (Smart Defaults)** button at the bottom of the Layer 1
page. This computes reasonable Q and R values from the engineering
ranges and rate limits for all variables in one click.

After auto-tuning, review the computed values and adjust any that need
fine-tuning.

### The Tuning Iteration

Layer 1 tuning is an iterative process:

1. Set initial values (auto-tune or manual).
2. Switch to the Simulate tab (Ctrl+4) and run a test.
3. Observe CV tracking and MV movement.
4. Return to the Optimize tab and adjust weights.
5. Click **Apply** (or the optimizer's Apply button) to push changes
   to the simulator.
6. Repeat until satisfied.

> **Common Mistake:** Adjusting Q and R in the Optimize tab but
> forgetting to click Apply. Changes in the Optimize tab are not
> applied to the simulator until you click Apply. The system will
> auto-navigate you to the Simulate tab after Apply.

---

## Chapter 6: Layer 2 Optimization

### The Smart Tune Wizard

Click the **Layer 2 (LP)** tab in the Optimize panel. The Layer 2
Smart Tune wizard has a left sidebar with six steps:

| Step | Label | Purpose |
|---|---|---|
| 1 | Select CV Ranks | Assign relaxation priority to each CV bound |
| 2 | Select Preferences | Choose Maximize/Minimize/Min Movement per variable |
| 3 | Prioritize MVs | Assign cost rank for lexicographic LP tiers |
| 4 | Evaluate Strategy | Inspect the gain matrix and verify achievability |
| 5 | Initialize Tuning | Apply smart defaults across all variables |
| 6 | Calculate SS | Solve Layer 2 LP and verify the steady-state target |

Each step has a help text at the bottom of the left sidebar. Click
through the steps in order.

### Step 1: Select CV Ranks

This step determines the relaxation order when constraints conflict.

The table shows each CV with its operating limits and editable rank
columns:

| Column | Description |
|---|---|
| CV Tag | Tag name |
| Description | Variable name |
| Op Lo | Operating lower limit (read-only, set in Simulation tab) |
| Op Hi | Operating upper limit (read-only, set in Simulation tab) |
| Lo Rank | Priority rank for the lower bound (1--100) |
| Hi Rank | Priority rank for the upper bound (1--100) |

Higher rank = more important = relaxed last. If the controller cannot
satisfy all constraints, it relaxes the lowest-rank constraints first.

**For the cumene heater:**

| CV | Lo Rank | Hi Rank | Rationale |
|---|---|---|---|
| XI-490 (O2) | 20 | 20 | Least critical -- informational |
| TIT-400 (outlet) | 60 | 60 | Product quality -- important |
| TIT-402 (bridgewall) | 40 | 80 | Hi limit is safety-critical |
| TIT-412 (coil) | 50 | 50 | Moderate importance |
| XI-410 (draft) | 10 | 10 | Lowest priority |
| AIT-410 (CO) | 30 | 70 | Hi limit is environmental limit |

Notice that TIT-402's upper rank (80) is much higher than its lower
rank (40). This is because the bridgewall high-temperature limit is a
safety constraint (overheating damages the refractory), while the lower
limit is just an efficiency target.

> **Tip:** Assign asymmetric ranks when the upper and lower limits have
> different consequences. A temperature CV with a safety high limit and
> an economic low limit should have Hi Rank >> Lo Rank.

### Step 2: Select Preferences

This step configures the economic optimization direction for each
variable.

The view shows two side-by-side tables: one for MVs and one for CVs.
Each table has a **Preference** dropdown per variable.

**MV preferences:**

| Preference | Meaning | Example |
|---|---|---|
| Minimize | Drive toward lower limit | Fuel gas (save fuel) |
| Maximize | Drive toward upper limit | Throughput |
| Min Movement | Stay near current value | Pressure setpoint |
| None | No economic preference | Let optimizer decide |

**CV preferences:**

| Preference | Meaning | Example |
|---|---|---|
| Minimize | Setpoint = lower operating limit | Waste stream flow |
| Maximize | Setpoint = upper operating limit | Product purity |
| Target | Track explicit setpoint | Temperature |
| None | Free within limits | No target |

**For the cumene heater:**

| Variable | Type | Preference | Rationale |
|---|---|---|---|
| FCV-410 (fuel) | MV | Minimize | Reduce fuel cost |
| SC-400 (damper) | MV | None | Let optimizer decide |
| FCV-411 (air) | MV | None | Let optimizer decide |
| XI-490 (O2) | CV | Target | Track setpoint (optimal O2) |
| TIT-400 (outlet) | CV | Target | Track setpoint (supply temp) |
| TIT-402 (bridgewall) | CV | None | Free within limits |
| TIT-412 (coil) | CV | Target | Track setpoint (coil temp) |
| XI-410 (draft) | CV | None | Free within limits |
| AIT-410 (CO) | CV | Minimize | Keep CO emissions low |

When you set an MV to "Minimize," the Layer 2 LP assigns a positive
cost to that MV and drives it toward its lower operating limit, subject
to all CV constraints being satisfied.

> **Common Mistake:** Setting all MVs to "Minimize." If fuel, air, and
> damper are all minimized, the optimizer may shut everything down.
> Only minimize variables with a clear economic benefit. Leave others
> at "None" so the optimizer can use them freely to satisfy constraints.

### Step 3: Prioritize MVs

This step assigns **cost ranks** to MVs for lexicographic optimization.

The table shows each MV with:

| Column | Description |
|---|---|
| MV Tag | Tag name |
| Description | Variable name |
| Preference | From Step 2 |
| LP Cost | Economic cost coefficient (editable) |
| Cost Rank | Priority for lexicographic LP (editable) |

Cost ranks determine the order in which economic objectives are
optimized. Higher rank = optimized first.

**For the cumene heater:**

| MV | LP Cost | Cost Rank | Rationale |
|---|---|---|---|
| FCV-410 (fuel) | 1.0 | 2 | Fuel is the primary economic driver |
| SC-400 (damper) | 0.0 | 0 | No economic cost |
| FCV-411 (air) | 0.2 | 1 | Small power cost for fan |

With these settings, the LP first minimizes fuel cost (rank 2), then
minimizes air flow cost (rank 1), then optimizes the damper freely
(rank 0 = no priority).

### Step 4: Evaluate Strategy

This step displays the **steady-state gain matrix** -- a table where
rows are CVs, columns are MVs, and each cell shows the gain
$$G_{ij} = \partial CV_i / \partial MV_j$$.

Cells are color-coded:
- Green = positive gain (increasing MV increases CV)
- Red = negative gain (increasing MV decreases CV)
- Gray = near-zero gain (no significant interaction)

The color intensity indicates the magnitude relative to the largest
gain.

**What to check:**

1. **Sign correctness:** Do the gain signs match your physical
   understanding? Increasing fuel should increase temperature (positive
   gain). If a sign is wrong, the model is incorrect.

2. **Interaction structure:** Which MVs affect which CVs? If an MV has
   near-zero gain on a CV, adjusting that MV will not help control that
   CV.

3. **Achievability:** Can your preferences be achieved? If you set
   "Minimize" on fuel (FCV-410) but the outlet temperature (TIT-400)
   has a lower limit that requires a certain minimum fuel flow, the
   gains tell you whether the objective is feasible.

Click **Recompute Gain Matrix** to refresh the display after any model
or configuration changes.

### Step 5: Initialize Tuning

This step provides a one-click way to apply smart defaults across all
variables.

The form shows four parameters:

| Parameter | Default | Formula |
|---|---|---|
| CV Concern (default) | 1.0 | Applied to all CV concern lo/hi |
| CV Rank (default) | 20 | Applied to all CV rank lo/hi |
| MV Move Suppression scale | 0.1 | $$R = \text{scale} / \text{rate\_limit}^2$$ |
| CV Q-weight scale | 100.0 | $$Q = \text{scale} / \text{range}^2$$ |

Click **Apply Smart Defaults to All Variables** to compute and apply
values. A confirmation dialog shows how many variables were updated.

> **Tip:** Use Step 5 as a starting point, then fine-tune individual
> values in Steps 1--3 and the Layer 1 tab. Step 5 is a "reset to
> reasonable defaults" button -- use it whenever you want to start fresh.

### Step 6: Calculate SS (Steady-State Calculator)

This step is the offline Layer 2 LP solver. It answers the question:
"Given the current preferences, costs, and constraints, where would the
controller drive the process to steady state?"

**Buttons:**

- **Calculate Steady State** -- Solves the Layer 2 LP at the current
  operating point with current operating limits.
- **Calculate Ideal SS (eng limits)** -- Solves with engineering limits
  (wider than operating limits). Shows the theoretical best the
  controller could achieve if operators removed all operating
  restrictions.
- **Clear** -- Clears the results.

**Results tables:**

The MV results table shows:

| Column | Description |
|---|---|
| Tag | MV tag |
| Description | MV name |
| Current | Current MV value |
| SS Value | Computed steady-state target |
| Op Lo | Operating lower limit |
| Op Hi | Operating upper limit |
| Active | "LO LIM", "HI LIM", or "FREE" |
| Delta (SS-Cur) | How much the MV would move |

The CV results table shows:

| Column | Description |
|---|---|
| Tag | CV tag |
| Description | CV name |
| Current | Current CV value |
| SS Value | Predicted CV at SS target |
| Op Lo | Operating lower limit |
| Op Hi | Operating upper limit |
| Status | "OK", "VIOLATION", or "INFEASIBLE" |
| Violation | Amount of constraint violation (if any) |

**Status chip** at the top right shows:
- "READY" (gray) -- waiting for calculation
- "OPTIMAL" (green) -- LP solved successfully
- "INFEASIBLE" (red) -- constraints are conflicting

**What to look for:**

1. The fuel gas valve (FCV-410) should be at or near its lower
   operating limit (because we set Minimize).
2. All CVs should be within their operating limits (Status = OK).
3. The solver status should be OPTIMAL.
4. The Delta column shows how far each MV would need to move. Large
   deltas suggest the current operating point is far from optimal.

> **Common Mistake:** Getting an INFEASIBLE result and not knowing why.
> Check that your CV operating limits are achievable given the MV
> limits and the gain matrix. If you require a minimum outlet temperature
> of 700 degF but the model shows you cannot reach 700 degF even with
> fuel at maximum, the LP is infeasible. Widen limits or change
> preferences.

---

## Chapter 7: Layer 3 NLP

### Overview

Layer 3 (Nonlinear Optimizer) is optional and requires:

- A nonlinear plant model (defined as ODEs in the YAML config with
  `type: nonlinear`).
- CasADi installed (`pip install casadi`).
- Layer 3 enabled in the configuration.

For the cumene heater with a linear model (from step-test identification),
Layer 3 is typically not needed. This chapter covers the setup for
users who have a first-principles nonlinear model.

### Enabling Layer 3

1. Navigate to the **Optimize** tab (Ctrl+2).
2. Click the **Layer 3 (NLP)** tab.
3. Check **Enable Layer 3 RTO**.
4. Set the **RTO Period** (how often Layer 3 runs, in minutes).
5. Configure IPOPT settings (defaults are usually fine):
   - Max iterations: 200
   - Convergence tolerance: 1e-6
   - Print level: 0 (silent)

### Running RTO Once

To test Layer 3 without waiting for the periodic timer:

1. Click **Run RTO Now** in the Layer 3 tab, or
2. From the main menu, trigger RTO (if available).

The RTO result shows:
- Updated gain matrix
- New operating point target
- NLP solve time
- Convergence status

### When to Skip Layer 3

Skip Layer 3 if:

- You have only a step-test model (no ODE model).
- The plant operates in a narrow range (linear model is adequate).
- You want to keep the controller simple for initial deployment.
- CasADi is not available in your environment.

> **Tip:** Start with Layers 1--2 only. Add Layer 3 later if you observe
> significant nonlinear behavior (gain changes with operating point) that
> degrades controller performance.

---

## Chapter 8: Calculations

### Navigating to the Calculate Tab

Click **Calculate** in the sidebar (or press Ctrl+3). The Calculations
panel has four regions:

**Top left -- Calculation List:**

A table listing all calculations (input and output) with:

| Column | Description |
|---|---|
| # | Sequence number (execution order) |
| Type | "Input" or "Output" |
| Name | User-assigned name |
| Status | "OK" (green check) or "ERR" (warning) |

**Top right -- Code Editor:**

A Python code editor with syntax highlighting. Editable cells have a
dark theme with color-coded keywords. The editor supports:
- Python keyword highlighting (purple)
- Built-in function highlighting (cyan)
- Special variable highlighting (green): `cvs`, `mvs`, `dvs`, `user`,
  `t`, `cycle`, `dt`, `engine`, `np`, `math`, `log`
- String highlighting (yellow)
- Comment highlighting (gray italic)

**Bottom left -- Variables Browser:**

A tree view showing all available variables organized by category:
- MVs (with tag names)
- CVs (with tag names)
- DVs (with tag names)

Double-click a variable to insert its accessor into the code editor.

**Bottom right -- Live State and Activity Log:**

The Live State panel shows real-time variable values. The Activity Log
shows execution results and any errors.

### Master Enable Toggles

At the top of the Calculations panel, two checkboxes control whether
input and output calculations are executed:

- **Input Calcs** (checkbox) -- Enable/disable all input calculations.
- **Output Calcs** (checkbox) -- Enable/disable all output calculations.

Unchecking these is useful for debugging: you can disable all
calculations temporarily without deleting them.

### Creating a New Calculation

1. Click **+New** below the calculation list.
2. A dialog asks for the calculation name and type (Input or Output).
3. Enter a name (e.g., "ValidateTemp") and select "Input."
4. Click OK. The new calculation appears in the list and the editor
   shows an empty script.

### Writing a Calculation

Type your Python code in the editor. For example, to compute an
average temperature and use it as a derived CV:

```python
# Average the three temperature CVs
avg = (cvs[1].value + cvs[2].value + cvs[3].value) / 3.0
user["avg_temp"] = avg

# Log the result
log(f"Avg temp = {avg:.1f} degF")

# Alert if above threshold
if avg > 800:
    log("WARNING: Average temperature exceeds 800 degF!")
```

### Testing a Calculation

1. Write the script.
2. Click **Test Run**. The script executes once with the current engine
   state.
3. Check the Activity Log at the bottom for output and errors.
4. If there are errors, fix the script and test again.
5. When satisfied, click **Apply** (Ctrl+S) to save and activate the
   calculation.

### Available Variables Reference

Inside a calculation, these variables are available:

**Variable arrays:**

```python
cvs[0]           # First CV object
cvs[0].value     # Current measurement value
cvs[0].setpoint  # Current setpoint
cvs[0].weight    # Q weight
cvs[0].limits.operating_lo   # Lower operating limit
cvs[0].limits.operating_hi   # Upper operating limit

mvs[0]           # First MV object
mvs[0].value     # Current output value
mvs[0].steady_state  # Steady-state operating point
mvs[0].move_suppress  # R weight

dvs[0]           # First DV object (if any)
dvs[0].value     # Current value
```

**Tag dictionaries:**

```python
cv["TIT-400.PV"]   # Access CV by tag name
mv["FCV-410.SP"]   # Access MV by tag name
```

**Engine state:**

```python
t        # Current time (minutes)
cycle    # Current cycle number
dt       # Sample period (minutes)
engine   # SimEngine object (advanced)
```

**User namespace (persistent across cycles):**

```python
user["my_var"] = 42          # Store a value
x = user.get("my_var", 0)   # Retrieve with default
```

**Libraries:**

```python
np       # NumPy
math     # Python math module
log("message")  # Log to Activity Log
```

### Example: Adaptive Move Suppression

This input calculation adjusts move suppression based on the prediction
error magnitude:

```python
# Increase move suppression when prediction error is large
# (indicates model-plant mismatch -- be more cautious)
for i, cv in enumerate(cvs):
    if hasattr(cv, 'pred_error'):
        err_pct = abs(cv.pred_error) / (cv.limits.engineering_hi - cv.limits.engineering_lo)
        if err_pct > 0.05:  # >5% error
            for mv in mvs:
                mv.move_suppress *= 1.5
            log(f"CV {cv.tag}: large pred error ({err_pct:.1%}), R increased")
            break
```

> **Common Mistake:** Modifying `mvs[i].value` in an *input*
> calculation. Input calculations run before the MPC, so changing
> MV values has no effect (the MPC will overwrite them). Modify MV
> values in *output* calculations if you need to post-process the
> MPC output.

### Calculation Execution Order

Calculations execute in sequence number order within their type:

```
1. Input calculations (lowest sequence number first)
2. MPC controller execution (Layers 1-2-3)
3. Output calculations (lowest sequence number first)
```

Use the arrow buttons (Up/Down) in the calculation list to change the
sequence order.

### Deleting and Disabling Calculations

To delete a calculation:

1. Select it in the list.
2. Click **-Del**.
3. Confirm the deletion.

To temporarily disable without deleting:

- Uncheck the master "Input Calcs" or "Output Calcs" toggle to disable
  all calculations of that type.
- Or comment out the entire script body with `#` prefixes.

### Example: Feedforward Compensation

This input calculation implements feedforward compensation for a
measured disturbance:

```python
# Feedforward: adjust outlet temp setpoint based on inlet temp
# The inlet temperature (DV) affects the outlet temperature (CV).
# When inlet temp drops, increase the outlet temp setpoint to
# maintain downstream process conditions.

if len(dvs) > 0:
    inlet_temp = dvs[0].value
    inlet_ref = dvs[0].steady_state
    delta_inlet = inlet_temp - inlet_ref
    
    # Feedforward gain: 0.5 degF outlet correction per 1 degF inlet change
    ff_gain = 0.5
    ff_correction = ff_gain * delta_inlet
    
    # Apply to outlet temp setpoint
    base_sp = 710.0  # nominal setpoint
    cvs[1].setpoint = base_sp + ff_correction
    
    if abs(ff_correction) > 1.0:
        log(f"FF correction: {ff_correction:+.1f} degF (inlet delta={delta_inlet:+.1f})")
```

### Example: Model-Plant Mismatch Monitor

This output calculation monitors prediction accuracy and logs warnings:

```python
# Monitor prediction error for each CV
if "pred_errors" not in user:
    user["pred_errors"] = {i: [] for i in range(len(cvs))}

for i, cv in enumerate(cvs):
    if hasattr(cv, 'pred_error'):
        user["pred_errors"][i].append(abs(cv.pred_error))
        # Keep last 100 errors
        if len(user["pred_errors"][i]) > 100:
            user["pred_errors"][i] = user["pred_errors"][i][-100:]
        
        # Alert if average error exceeds 5% of range
        avg_err = np.mean(user["pred_errors"][i])
        eng_range = cv.limits.engineering_hi - cv.limits.engineering_lo
        if eng_range > 0 and avg_err / eng_range > 0.05:
            log(f"WARNING: {cv.tag} avg pred error = {avg_err:.2f} ({avg_err/eng_range:.1%} of range)")
```

### Calculation Best Practices

1. **Keep calculations short.** Each calculation should do one thing.
   Use multiple calculations for different tasks.

2. **Use the `user` dict for state.** Do not rely on global variables
   or file I/O. The `user` dictionary is the sanctioned way to persist
   state between cycles.

3. **Handle missing data.** Check for None values and index bounds
   before accessing variables.

4. **Log sparingly.** Logging every cycle floods the Activity Log. Log
   only on significant events (threshold crossings, errors, mode
   changes).

5. **Test before deploying.** Always use the Test Run button before
   activating a calculation. A calculation error can disrupt the
   entire control cycle.

---

## Chapter 9: Simulation

### Navigating to the Simulate Tab

Click **Simulate** in the sidebar (or press Ctrl+4). This is the most
feature-rich panel -- it mirrors the DMC3 Builder simulation view.

### Layout Overview

The Simulation tab has three main regions:

**Left panel -- Variable Tables:**

Three tables stacked vertically, each with extensive column sets:

- **MV table** (Inputs): 47 columns covering identity, status,
  operating values, limits (validity, engineering, operator), SS
  results, tuning, economics, control, plot, and results.
- **DV table** (Disturbances): 10 columns for disturbance variables.
- **CV table** (Outputs): 48 columns similar to the MV table but for
  controlled variables.

Most columns are read-only (gray background). Editable columns have a
cream background and are organized into groups: operating, tuning,
economics, and plot.

**Right panel -- Strip Charts:**

Embedded pyqtgraph strip charts showing real-time variable trajectories.
Each CV and MV has its own chart showing:
- Measurement (solid line)
- Setpoint (dashed line)
- Operating limits (horizontal bands)
- Predicted trajectory (dotted line, when available)

The x-axis shows time relative to "now" in minutes/hours. Past data
scrolls left; future predictions extend right.

**Bottom panel -- Activity Log and Toolbar:**

The toolbar provides simulation controls and the activity log shows
cycle-by-cycle status messages.

### Column Visibility

Not all 47+ columns are visible by default. To control which columns
appear:

At the top of each table, **radio buttons** filter the visible columns:

| Filter | Shows |
|---|---|
| Operating | Identity + status + values + limits + results |
| Tuning | Identity + all tuning parameters |
| Results | Identity + computed results + predictions |

You can also right-click the column header to show/hide individual
columns.

### Simulation Controls

The toolbar at the bottom provides these controls:

| Control | Shortcut | Action |
|---|---|---|
| Step | F7 | Advance one sample period |
| Run | F5 | Run continuously |
| Stop | Shift+F5 | Stop continuous run |
| Reset | Ctrl+R | Reset to initial conditions |
| Noise toggle | -- | Enable/disable measurement noise |
| Speed selector | -- | 1x, 2x, 5x, 10x, 50x, 100x real time |
| Open/Closed loop | -- | Toggle between open-loop and closed-loop |

### Running a Basic Simulation

1. Click **Step** (F7) to advance one cycle.
2. Observe the MV and CV values update.
3. Check the activity log for solver status ("L1 OPTIMAL", solve time).
4. Click Step several more times or press **Run** (F5) for continuous
   operation.

On the first step, the controller computes initial moves to drive CVs
toward their setpoints. If the process starts at steady state (which it
does after import), the initial moves should be small.

### Setpoint Change Test

1. In the CV table, find TIT-400 (outlet temperature).
2. Scroll to the **Setpoint** column (or use the Tuning filter).
3. Type a new setpoint value (e.g., increase from 710 to 720 degF).
4. Press Enter.
5. Click Step (F7) repeatedly or Run (F5).
6. Watch the strip chart -- TIT-400 should ramp toward 720 degF.
7. Observe the MV movements -- FCV-410 (fuel) should increase to
   provide more heat.

**What to evaluate:**

- **Settling time:** How many cycles until TIT-400 reaches 720 degF?
  Should be roughly equal to the model settling time.
- **Overshoot:** Does TIT-400 overshoot 720? If so, increase move
  suppression on FCV-410.
- **MV smoothness:** Is FCV-410 moving in small, gradual steps? If it
  jumps wildly, increase move suppression.
- **Cross-coupling:** Do other CVs (O2, bridgewall) deviate
  significantly? If so, their models may need verification.

### Disturbance Test

1. If you have DVs, change a DV value in the DV table.
2. If no DVs are configured, simulate a disturbance by temporarily
   changing a CV's steady-state value.
3. Run the simulation and observe disturbance rejection.

### Constraint Test

1. Tighten a CV operating limit so it becomes active during operation.
   For example, set TIT-400 Op Hi = 715 degF (below the setpoint of 720).
2. Run the simulation.
3. The controller should respect the 715 degF limit and drive TIT-400
   to 715 instead of 720.
4. Other CVs may shift as the controller re-optimizes the constrained
   problem.

### Noise Test

1. In the CV table, find the **Simulation Noise** column.
2. Enter noise standard deviations for each CV:
   - XI-490 (O2): 0.1%
   - TIT-400 (outlet): 0.5 degF
   - TIT-402 (bridgewall): 1.0 degF
   - TIT-412 (coil): 0.5 degF
   - XI-410 (draft): 0.05 inH2O
   - AIT-410 (CO): 5.0 ppm
3. Enable noise using the noise toggle in the toolbar.
4. Run the simulation.
5. Observe whether MV movements are smooth despite noisy measurements.
   If MVs oscillate, increase move suppression or switch noisy CVs to
   first-order feedback filters.

### Reading the Strip Charts

Each strip chart shows:

- **Blue solid line:** Current measurement trajectory.
- **Orange dashed line:** Setpoint (for CVs) or target (for MVs).
- **Gray horizontal lines:** Operating limits (hi and lo).
- **Green dotted line:** Predicted future trajectory (from Layer 1).
- **Vertical "now" line:** Separates past (left) from predicted future
  (right).

The x-axis labels show relative time:
- `-30m` = 30 minutes ago
- `now` = current time
- `+15m` = 15 minutes into the future (prediction)

### Editing During Simulation

You can edit tuning parameters directly in the simulation tables during
a run:

- Change **Operator Lo/Hi** to test constraint tightening.
- Change **Move Suppression** to adjust controller aggressiveness.
- Change **Setpoint** to test setpoint tracking.
- Change **LP Cost** or **Cost Rank** to test economic optimization.
- Change **Opt Type** via the dropdown to change MV/CV preferences.

Changes take effect on the next simulation cycle.

> **Tip:** The simulation tables are the primary tuning interface during
> iterative tuning. You do not need to switch back to the Optimize tab
> for every change -- edit directly in the simulation and verify the
> effect immediately.

### Complete Tuning Walkthrough: Cumene Heater

This section walks through a full tuning session for the cumene heater,
step by step.

**Phase 1: Initial Setup (Cycles 0--5)**

1. Reset the simulation (Ctrl+R).
2. Verify the process is at steady state: all MV and CV values should
   match their steady-state values. Deltas should be zero.
3. Step once (F7). The activity log should show "L1 OPTIMAL" with a
   small solve time (< 5 ms).
4. All moves should be zero or near-zero (no reason to move yet).

**Phase 2: Setpoint Step on Outlet Temperature (Cycles 5--40)**

5. In the CV table, change TIT-400 setpoint from 710 to 720 degF.
6. Step the simulation 35 times (or press F5 and let it run).
7. Watch the strip chart for TIT-400. It should ramp up and settle near
   720 degF.

Expected observations:
- FCV-410 (fuel) increases to provide more heat.
- TIT-402 (bridgewall) and TIT-412 (coil) also increase slightly due
  to cross-coupling.
- XI-490 (O2) decreases slightly (more fuel, same air = less excess O2).
- The settling time should be approximately 30--60 cycles (30--60
  minutes at $$T_s = 1$$ min).

If TIT-400 settles in < 20 cycles, the controller may be too
aggressive. Increase FCV-410 move suppression.

If TIT-400 has not reached 718 degF after 60 cycles, the controller is
too sluggish. Decrease FCV-410 move suppression.

**Phase 3: Constraint Activation (Cycles 40--70)**

8. Set the TIT-402 (bridgewall) upper operating limit to a value just
   above the current measurement. For example, if TIT-402 is at 1050
   degF, set Op Hi = 1060 degF.
9. Now step the setpoint for TIT-400 up again (e.g., 720 to 730 degF).
10. Run the simulation.

Expected observations:
- The controller increases fuel to raise TIT-400.
- As TIT-402 approaches 1060 degF, the controller slows down to
  respect the constraint.
- TIT-400 may not reach 730 degF if the bridgewall constraint prevents
  enough fuel increase.
- The CV status for TIT-402 should show "AT LIMIT" or similar.

This tests whether the constraint priority system is working correctly.

**Phase 4: Economic Optimization (Cycles 70--100)**

11. Set FCV-410 Opt Type to "Minimize" (either in the simulation table's
    Opt Type dropdown or in the Layer 2 wizard, Step 2).
12. Set the FCV-410 LP Cost to 1.0.
13. Run the simulation for 30 cycles.

Expected observations:
- The fuel valve gradually moves toward its lower operating limit.
- CV setpoints are maintained as long as possible.
- If CVs cannot be maintained at the lower fuel level, the controller
  finds the optimal balance between fuel cost and CV tracking.

**Phase 5: Disturbance Rejection (Cycles 100--130)**

14. If you have DVs, change a DV value to simulate a disturbance.
15. If no DVs are configured, manually override one MV: set FCV-411
    (air valve) to manual and change its value by +5%.
16. Run the simulation and observe recovery.

Expected observations:
- XI-490 (O2) changes due to the air flow change.
- The controller adjusts FCV-410 and SC-400 to compensate.
- All CVs should return to their targets within 30--60 cycles.

**Phase 6: Noise Robustness (Cycles 130--160)**

17. Set Simulation Noise values for all CVs (see noise values above).
18. Enable the noise toggle.
19. Run the simulation for 30 cycles.

Expected observations:
- CV measurements show noise.
- MV moves should remain smooth (not chasing noise).
- If MVs oscillate, increase move suppression or enable first-order
  feedback filters.

### Exporting Simulation Results

After completing a tuning session, you may want to export the results
for documentation or comparison:

1. The activity log can be copied to clipboard (right-click > Copy All).
2. Strip chart data is available via the engine's history arrays.
3. Save the project to preserve the current tuning state.

### Understanding the Simulation Variable Tables in Detail

**MV Table Columns (47 columns, grouped):**

*Identity group:* Tag, Description, Units, Subcontroller -- identifying
information, all read-only.

*Status group:* Combined Status (AUTO/MAN/SHED), Service Request,
Service Status -- runtime status indicators.

*Operating group:* Measurement (current value from plant model).

*Limits group (7 columns):* Arranged as a "bar chart" from left to
right: Validity Lo | Eng Lo | Operator Lo | SS Value | Operator Hi |
Eng Hi | Validity Hi. This layout mirrors the DMC3 Builder variable
bar, showing all limit levels at a glance. Operator Lo/Hi are editable;
the others are set during configuration.

*SS Results group:* Ideal SS (target from Layer 2), Ideal Constraint
(which constraint is active at SS), Current Move (last computed
$$\Delta u$$).

*Tuning group:* Move Suppression, Move Supp Incr, Max Move, Move
Resolution, Move Accumulation, Target Suppression, MinMove Criterion,
Dyn Min Movement -- all tuning parameters.

*Economics group:* LP Cost, Shadow Price, Cost Rank, Active Constraint.

*Control group:* Reverse Acting, Anti Windup, Loop Status, Setpoint, Is
FeedForward, Use Limit Track, Shed Option.

*Plot group:* Plot Lo, Plot Hi, Plot Auto Scale.

*Results group:* Predicted, Delta, Last Move, Transformed Target,
Transformed Measurement, Status, Opt Type.

**CV Table Columns (48 columns, grouped):**

Similar to MVs with additional columns for SS tuning (Lo Rank, Hi
Concern, Hi Rank), dynamic tuning (Lo/Hi Concern, Target Concern, Lo/Hi
Zone), ramp control (Ramp, Ramp SP, Ramp Rate, Ramp Horizon, Rotation
Factor, Max Imbalance), and noise (Simulation Noise, Pred Error).

> **Tip:** Use the Operating/Tuning/Results radio filters at the top of
> each table to focus on the columns relevant to your current task.
> Trying to view all 47+ columns at once is overwhelming and
> counterproductive.

---

## Chapter 10: Deployment

### Overview

The Deploy tab connects the controller to a real (or simulated) process
via OPC UA. It has three sub-tabs:

- **Online Settings** -- General settings and validation limits.
- **IO Tags** -- Tag mapping between controller variables and OPC UA
  nodes.
- **Activity** -- Real-time monitoring during deployment.

### Connection Setup

At the top of the Deploy tab:

1. **Server URL field:** Enter the OPC UA server URL.
   - For an external DCS: `opc.tcp://dcs-server:4840`
   - For the embedded test server: `opc.tcp://localhost:48400`

2. **Use embedded server (checkbox):** Check this to start a built-in
   OPC UA server that publishes the simulated plant model. This is
   perfect for testing the deployment pipeline without a real DCS.

3. Click **Connect** to establish the OPC UA connection.

The status bar below shows:
- Connection indicator: green dot "CONNECTED" or red dot "DISCONNECTED"
- Cycle count and timing when deployed

### Online Settings

The Online Settings sub-tab has three sections:

**General Settings table:** One row with global settings:

| Setting | Description |
|---|---|
| Sample Time | Execution period (minutes) |
| Controller Mode | AUTO / MANUAL / SHED |
| Write Enabled | Whether MV outputs are written to the DCS |
| Simulation Mode | If checked, reads/writes go to embedded server |

**Input Validation Limits table:** One row per CV and DV:

| Column | Description |
|---|---|
| Variable | Tag name |
| Validity Lo | Lowest acceptable measurement |
| Validity Hi | Highest acceptable measurement |
| Engineering Lo | Equipment range lower bound |
| Engineering Hi | Equipment range upper bound |
| Operator Lo | Current operating lower limit |
| Operator Hi | Current operating upper limit |

Measurements outside validity limits are rejected as BAD. Measurements
outside engineering limits trigger a warning.

**Output Validation Limits table:** One row per MV:

| Column | Description |
|---|---|
| Variable | Tag name |
| Validity Lo/Hi | Output clamping limits |
| Engineering Lo/Hi | Physical limits |
| Operator Lo/Hi | Operating limits |

MV outputs are clamped to the validity limits before being written to
the DCS. This prevents the controller from ever commanding a value
outside the safe range.

### IO Tags

The IO Tags sub-tab maps controller variables to OPC UA nodes:

**Tag Browser (top):** Shows the OPC UA server's node tree. Browse to
find the correct node for each variable.

**Tag Generator (middle):** One row per controller variable. Each row
shows:

| Column | Description |
|---|---|
| Variable | Controller variable tag |
| Type | Input (CV/DV) or Output (MV) |
| OPC UA Node | The mapped OPC UA node ID |
| Status | Connection status (green/red) |

Click a row to see its detailed parameter mapping below.

**Variable Detail (bottom):** Shows the individual parameters for the
selected variable (PV, SP, STATUS, MODE, etc.) and their OPC UA node
mappings.

### Testing the Connection

1. After connecting, click **Test Connections**.
2. The system reads all input tags and writes test values to output
   tags (if write is enabled and in simulation mode).
3. Results appear in the Activity log.
4. Fix any failed connections before deploying.

### Deploying the Controller

1. Verify all connections are green (IO Tags status column).
2. Click **Deploy**.
3. The deployment runtime starts:
   - A timer fires every $$T_s$$ minutes.
   - Each cycle: read inputs, run MPC, write outputs.
4. The status bar updates with cycle count and execution time.
5. The Activity sub-tab shows real-time per-variable status.

### Monitoring During Deployment

The Activity sub-tab shows:

- Per-variable current values, setpoints, and limit status.
- Solver status each cycle (OPTIMAL, INFEASIBLE, etc.).
- Execution timing (read time, solve time, write time, total cycle
  time).
- Any warnings or errors (bad values, communication failures,
  constraint relaxation).

### Stopping the Controller

Click **Stop** to halt the deployment:

1. The controller stops computing moves.
2. MV outputs remain at their last values (no sudden jumps).
3. The base-layer PID loops continue operating at whatever setpoints
   the MPC last wrote.
4. The status changes to "Runtime: idle."

> **Common Mistake:** Stopping the controller and expecting MVs to
> return to some default value. MVs stay where they are. If you want
> MVs at specific values after shutdown, write an output calculation
> that sets MVs to their steady-state values when the controller is
> stopped.

### Deployment Walkthrough: Embedded Server Test

Before connecting to a real DCS, always test the full deployment
pipeline using the embedded OPC UA server. This walkthrough uses the
cumene heater example.

**Step 1: Prepare the controller.**

1. Complete tuning in the Simulate tab. Verify that the controller
   performs well with setpoint changes, constraint handling, and
   disturbance rejection.
2. Save the project (Ctrl+S).
3. Navigate to the Deploy tab (Ctrl+5).

**Step 2: Configure the embedded server.**

4. Check **Use embedded server**.
5. Leave the Server URL as `opc.tcp://localhost:48400`.
6. Click **Connect**.
7. The status bar should change to green "CONNECTED."

If connection fails, check that port 48400 is not in use by another
application.

**Step 3: Verify IO tags.**

8. Click the **IO Tags** sub-tab.
9. The Tag Generator table should show one row per variable (3 MVs +
   6 CVs = 9 rows).
10. Each row should have a green Status indicator.
11. Click a variable row to see its parameter mappings in the Variable
    Detail section below.
12. Verify that each parameter (PV, SP, STATUS, MODE) has a valid
    OPC UA node mapping.

**Step 4: Set validation limits.**

13. Click the **Online Settings** sub-tab.
14. Review the Input Validation Limits table. Set validity limits wider
    than engineering limits (e.g., Validity Lo = Eng Lo - 10%,
    Validity Hi = Eng Hi + 10%).
15. Review the Output Validation Limits table. Set validity limits to
    match the physical equipment limits.

**Step 5: Deploy.**

16. Click **Deploy**.
17. The runtime starts executing:
    - Cycle count increments every $$T_s$$ minutes.
    - Cycle time shows the execution time per cycle.
    - Runtime status shows "Running."
18. Click the **Activity** sub-tab to see per-cycle status.

**Step 6: Test during deployment.**

19. While deployed, you can still make changes in the Simulate tab.
    These changes flow through to the deployed controller.
20. Change a CV setpoint and observe the response through the Activity
    tab's live status display.
21. Verify that MV outputs are changing appropriately.

**Step 7: Stop and review.**

22. Click **Stop** when satisfied.
23. Review the Activity log for any warnings or errors during the
    deployment run.
24. If everything worked with the embedded server, you are ready to
    connect to the real DCS.

### Deployment Checklist

Before deploying to a production DCS, complete this checklist:

- [ ] Model validated against recent plant data (prediction error < 10%)
- [ ] All operating limits set from current operating procedures
- [ ] Validation limits set from instrument specifications
- [ ] Feedback filters configured for noisy measurements
- [ ] Move suppression tuned (verified in simulation)
- [ ] Constraint priority ranks assigned
- [ ] Economic preferences and costs configured
- [ ] Calculations tested (if any)
- [ ] Simulation testing completed:
  - [ ] Setpoint tracking (all CVs)
  - [ ] Disturbance rejection
  - [ ] Constraint handling
  - [ ] Noise robustness
  - [ ] Infeasibility behavior
- [ ] Embedded server deployment test successful
- [ ] OPC UA server URL and credentials obtained from DCS team
- [ ] IO tag mapping verified against DCS tag database
- [ ] Operations team briefed on controller behavior
- [ ] Rollback plan documented (how to stop controller and revert)
- [ ] Project file saved and version-controlled

> **Tip:** Print this checklist and sign off each item. APC deployment
> is a safety-critical activity. Skipping steps leads to incidents.

---

## Chapter 11: Recipes and Version Control

### Saving Your Work

APC Architect saves all configuration in a single `.apcproj` file
(YAML format). This includes:

- All variable definitions (MVs, CVs, DVs)
- Operating limits and engineering ranges
- Tuning parameters (Q weights, R weights, concerns, ranks)
- Preferences and economic costs
- Feedback filter settings
- Subcontroller assignments
- Calculation scripts
- Deployment configuration
- Model source reference

### Creating Recipe Variants

To create different tuning configurations:

1. Configure the controller for one operating scenario.
2. File > Save As: `heater_conservative.apcproj`
3. Adjust tuning for a different scenario (e.g., more aggressive).
4. File > Save As: `heater_aggressive.apcproj`

Now you have two recipes that you can switch between by opening the
appropriate project file.

### Comparing Recipes

To compare two recipes:

1. Open recipe A.
2. Run a standardized test in the simulator (e.g., +10 degF setpoint
   step, 60 cycles).
3. Note the key metrics:
   - Settling time (cycles to reach 95% of setpoint change)
   - Overshoot (maximum deviation beyond setpoint)
   - Total MV movement (sum of absolute moves)
4. Open recipe B.
5. Run the same test.
6. Compare metrics.

### Version Control with Git

The `.apcproj` file is plain YAML text, making it ideal for version
control:

```bash
git add heater_apc.apcproj
git commit -m "Initial tuning after step test"
```

After tuning changes:

```bash
git diff heater_apc.apcproj  # see what changed
git commit -m "Increased fuel valve move suppression R=0.05->0.10"
```

> **Tip:** Use meaningful commit messages that describe *why* you
> changed the tuning, not just *what* changed. Future you (or your
> colleague) will thank you.

---

## Chapter 12: Troubleshooting

### Problem: "No plant model loaded" Warning

**Symptom:** The status bar shows "No plant model loaded. Running
open-loop only." The simulation runs but the controller does not
compute moves.

**Cause:** No model bundle has been imported, or the model bundle did
not contain a valid state-space realization.

**Solution:**
1. File > Import Model Bundle (Ctrl+I).
2. Select a valid `.apcmodel` file.
3. If the bundle lacks a state-space realization, re-export it from
   APC Ident with ERA enabled.

### Problem: "C++ core not available" Warning

**Symptom:** The status bar shows "C++ core not available. Running
open-loop only."

**Cause:** The C++ MPC core library (`_azeoapc_core`) was not found.
This is needed for the OSQP and HiGHS solvers.

**Solution:**
1. Build the C++ core: `cmake --build build --config Release`
2. Verify the binding exists: check `build/bindings/Release/` for
   `_azeoapc_core.pyd` (Windows) or `_azeoapc_core.so` (Linux).
3. Restart APC Architect.

### Problem: QP Returns INFEASIBLE Every Cycle

**Symptom:** The activity log shows "L1 INFEASIBLE" on every cycle.
The controller does not move any MVs.

**Causes and solutions:**

1. **Conflicting CV limits.** Two or more CVs have limits that cannot
   be simultaneously satisfied. Check the gain matrix (Step 4) to see
   if the physical constraints are achievable.

2. **MV limits too tight.** The MVs do not have enough range to
   satisfy all CV constraints. Widen MV operating limits.

3. **Model error.** The model gains are significantly wrong, causing
   the controller to compute targets that are physically impossible.
   Re-identify the affected channels.

4. **Operating point far from steady state.** If the current operating
   point is far from the model's steady state, the linear predictions
   may be inaccurate. Reset the simulation and let the plant settle
   before enabling closed-loop control.

### Problem: MV Oscillates

**Symptom:** An MV alternates between two values (high-low-high-low)
on successive cycles.

**Causes and solutions:**

1. **Move suppression too low.** Increase R by a factor of 5--10.
2. **CV weight too high.** The controller overreacts to small CV errors.
   Decrease Q.
3. **Noisy CV measurement.** The controller chases noise. Enable a
   first-order feedback filter with appropriate prediction error lag.
4. **Model gain sign error.** If the model says "more MV increases CV"
   but in reality it decreases it, the controller will oscillate.
   Check the gain matrix.
5. **Control horizon too large.** Decrease M from (e.g.) 10 to 5 or 3.

### Problem: CV Does Not Track Setpoint

**Symptom:** A CV stays at a constant offset from its setpoint, never
reaching it.

**Causes and solutions:**

1. **No feedback filter enabled.** Without a disturbance observer, the
   controller cannot compensate for model error. Verify that feedback
   filters are configured (Configure tab, Feedback Filters).
2. **Move suppression too high.** The controller is not making large
   enough moves. Decrease R.
3. **CV weight too low.** The controller is not prioritizing this CV.
   Increase Q.
4. **MV at limit.** The MV has reached its operating limit and cannot
   move further. Check the MV table for "at limit" flags. Widen limits
   or reduce load on the MV.
5. **Opt type conflict.** If the CV's opt type is set to "None" or the
   wrong direction, it may not track. Set it to "Target."

### Problem: Controller Is Too Sluggish

**Symptom:** CVs respond very slowly to setpoint changes. It takes
many cycles to reach the new setpoint.

**Solutions:**

1. Decrease move suppression (R) on the relevant MVs.
2. Increase the control horizon (M) from 3 to 5 or 7.
3. Verify the prediction horizon (P) is not excessively long.
4. Check that max move is not too restrictive.

### Problem: Controller Is Too Aggressive

**Symptom:** CVs overshoot setpoints. MVs make large jumps.

**Solutions:**

1. Increase move suppression (R) on all MVs.
2. Decrease the control horizon (M) to 3.
3. Add or tighten rate limits (Max Move column).
4. Ensure CV noise values are set appropriately and noise filtering
   is enabled.

### Problem: OPC UA Connection Fails

**Symptom:** Clicking "Connect" in the Deploy tab does not establish
a connection. Status remains "DISCONNECTED."

**Solutions:**

1. Verify the server URL is correct and the OPC UA server is running.
2. Check firewall settings (port 4840 or custom port must be open).
3. Try the embedded server first to verify the deployment pipeline
   works locally.
4. Check the Activity log for specific error messages.

### Problem: Calculations Produce Errors

**Symptom:** A calculation shows "ERR" status. The Activity Log shows
a Python traceback.

**Solutions:**

1. Click the calculation in the list to see its code.
2. Read the error message in the Activity Log.
3. Common issues:
   - `IndexError`: Accessing `cvs[i]` with wrong index. Check variable
     count.
   - `KeyError`: Using wrong tag name in `cv["tag"]`. Check tag names
     in the Summary view.
   - `NameError`: Using a variable not in scope. Only the documented
     variables (cvs, mvs, dvs, user, t, cycle, dt, engine, np, math,
     log) are available.
4. Fix the code and click **Test Run** to verify.

### Problem: Simulation Runs But Nothing Happens

**Symptom:** Stepping the simulation does not change any values. CVs
and MVs stay constant.

**Causes and solutions:**

1. **Open-loop mode.** The simulation may be in open-loop mode (no MPC
   moves). Toggle to closed-loop using the Open/Closed loop control.
2. **Already at steady state.** If the process is at steady state and
   all setpoints are met, the controller correctly does nothing.
   Change a setpoint to test.
3. **Controller mode is MANUAL.** Check the Combined Status column for
   each MV. If it shows MAN, the MV is not under MPC control.

### Problem: Gain Matrix Shows All Zeros

**Symptom:** Step 4 (Evaluate Strategy) shows a gain matrix with all
zero entries.

**Causes and solutions:**

1. **No plant model loaded.** Import a model bundle first.
2. **State-space matrices are invalid.** The A matrix may have
   eigenvalues on the unit circle (marginally stable), making
   $$(A - I)$$ singular. Check the ERA order in the model bundle --
   try a different order.
3. **Wrong model type.** If the plant uses FOPTD parameters instead
   of state-space, the gain computation path is different. Verify
   the plant type in the Summary view.

Click **Recompute Gain Matrix** after fixing the issue.

### Problem: Steady-State Calculator Shows Wrong Results

**Symptom:** The SS Calculator (Step 6) returns values that do not
make physical sense (e.g., negative temperatures, impossibly high
flows).

**Causes and solutions:**

1. **Operating limits not set.** Default limits may be 0 and 1e18. Set
   realistic operating limits for all CVs and MVs.
2. **Gain matrix sign error.** If the model has wrong signs, the LP
   drives variables in the wrong direction. Check Step 4.
3. **Preferences conflict.** Minimizing all MVs while maximizing all
   CVs may produce unrealistic targets. Review Step 2 preferences.

### Problem: Layer 2 Shadow Prices Are Zero

**Symptom:** All shadow prices in the simulation table show 0.0.

**Explanation:** Shadow prices are zero when no constraint is active.
The optimal point is in the interior of the feasible region. Shadow
prices become nonzero only when the LP solution is at a constraint
boundary.

To see nonzero shadow prices, tighten operating limits until at least
one constraint becomes active.

### Problem: Slow Simulation Performance

**Symptom:** Each simulation step takes several seconds instead of
milliseconds.

**Causes and solutions:**

1. **Large problem size.** A 50-CV, 30-MV problem with P=200, M=20
   creates a large QP. Reduce P or M.
2. **No warm-starting.** The first cycle after reset is always slower
   (cold start). Subsequent cycles should be fast.
3. **OSQP convergence issues.** If the QP is ill-conditioned, OSQP
   needs many iterations. Check that Q and R weights are not
   extremely disparate (e.g., Q = 1e6, R = 1e-6). Normalize weights.
4. **Python overhead.** The simulation engine has Python overhead for
   plotting and logging. This is normal and does not affect real-time
   deployment (which runs the C++ core directly).

### Problem: Project File Will Not Open

**Symptom:** Opening a `.apcproj` file produces a "Failed to load
project" error.

**Causes and solutions:**

1. **Corrupted YAML.** Open the file in a text editor and check for
   syntax errors (unmatched brackets, missing colons, invalid Unicode).
2. **Missing model file.** If the project references an `.apcmodel`
   bundle that has been moved or deleted, the loader may fail. Check
   the `model.source` field in the YAML and ensure the file exists.
3. **Version mismatch.** A project saved with a newer version of APC
   Architect may have fields not recognized by an older version.
   Update APC Architect.

### Problem: Strip Charts Not Updating

**Symptom:** The strip charts in the Simulate tab are blank or frozen.

**Causes and solutions:**

1. **pyqtgraph not installed.** Install it: `pip install pyqtgraph`.
2. **OpenGL issues.** Some virtual machines and remote desktop sessions
   have OpenGL problems. Try setting the environment variable
   `PYQTGRAPH_QT_LIB=PySide6` and restarting.
3. **Plot range mismatch.** If Plot Lo and Plot Hi are set to the same
   value, the chart has zero vertical range. Set appropriate plot
   limits.

### General Debugging Tips

1. **Read the activity log.** Every solver execution, calculation
   result, and error is logged. The activity log is your primary
   debugging tool.

2. **Start simple.** If you have a complex controller (many MVs and CVs),
   test with a reduced set first. Put non-essential variables in manual
   mode and tune one interaction at a time.

3. **Compare open-loop and closed-loop.** Run the simulation in
   open-loop (MPC disabled) and manually step MVs to verify the plant
   model responds correctly. If the plant model is wrong, no amount of
   tuning will help.

4. **Check the units.** A common source of errors is unit mismatch
   between the model (identified at one sample time) and the controller
   (running at a different sample time). Ensure the controller sample
   time matches the model sample time.

5. **Use the SS Calculator.** Before running dynamic simulations, use
   Step 6 to verify that the steady-state target is reasonable. If the
   SS target is wrong, the dynamic simulation will also be wrong.

6. **Save early, save often.** Save the project before making major
   changes. If something goes wrong, you can always revert to the saved
   version.

---

## Quick Reference Card

### Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+N | New project |
| Ctrl+O | Open project |
| Ctrl+S | Save project |
| Ctrl+Shift+S | Save As |
| Ctrl+I | Import model bundle |
| Ctrl+Q | Exit |
| Ctrl+1 | Go to Configure tab |
| Ctrl+2 | Go to Optimize tab |
| Ctrl+3 | Go to Calculate tab |
| Ctrl+4 | Go to Simulate tab |
| Ctrl+5 | Go to Deploy tab |
| F5 | Run simulation continuously |
| Shift+F5 | Stop simulation |
| F7 | Step simulation (one cycle) |
| Ctrl+R | Reset simulation |

### Typical Workflow

```
1. Import model bundle from APC Ident     (File > Import)
2. Set operating limits                   (Simulate tab, Op Lo/Hi columns)
3. Configure feedback filters             (Configure tab, Filters sub-tab)
4. Auto-tune Layer 1                      (Optimize tab, Layer 1, Auto-Tune)
5. Set economic preferences               (Optimize tab, Layer 2, Steps 1-3)
6. Apply and simulate                     (Optimize tab, Apply button)
7. Iterate tuning                         (Simulate tab, adjust + test)
8. Save project                           (File > Save)
9. Deploy (when ready)                    (Deploy tab, Connect + Deploy)
```

### Tuning Quick Reference

| Want this... | Adjust this... | Direction |
|---|---|---|
| Smoother MV moves | Move Suppression (R) | Increase |
| Faster CV tracking | Move Suppression (R) | Decrease |
| Tighter tracking on one CV | CV Weight (Q) | Increase |
| Less constraint violation | Concern value | Increase |
| Different relaxation order | Rank value | Increase for more important |
| Economic optimization | LP Cost + Preference | Set cost + Minimize/Maximize |
| Noise rejection | Feedback filter | First Order, increase lag |
