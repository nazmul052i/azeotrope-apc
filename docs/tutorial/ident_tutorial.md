# APC Ident Tutorial: Complete Model Identification Workflow

**Cumene Hot Oil Heater Example**

This tutorial walks you through the complete model identification workflow
using APC Ident, from loading raw step-test data to exporting a validated
model bundle ready for controller design. We use the cumene hot oil heater
example included with the application.

**Prerequisites:** Basic DCS/process control knowledge (what a PID loop
is, what a setpoint means). No prior model identification experience
required.

---

## Table of Contents

1. [Getting Started](#chapter-1-getting-started)
2. [Loading and Inspecting Data](#chapter-2-loading-and-inspecting-data)
3. [Data Conditioning](#chapter-3-data-conditioning)
4. [Tag Assignment](#chapter-4-tag-assignment)
5. [FIR Identification](#chapter-5-fir-identification)
6. [Subspace Identification](#chapter-6-subspace-identification)
7. [Multi-Trial and Model Assembly](#chapter-7-multi-trial-and-model-assembly)
8. [Curve Operations](#chapter-8-curve-operations)
9. [Analysis Tools](#chapter-9-analysis-tools)
10. [Validation](#chapter-10-validation)
11. [Exporting and Reporting](#chapter-11-exporting-and-reporting)
12. [Advanced Topics](#chapter-12-advanced-topics)

---

## Chapter 1: Getting Started

### What Is Model Identification?

Every Advanced Process Control (APC/MPC) controller needs a mathematical
model of the plant it controls. This model describes how each manipulated
variable (MV -- the knobs you turn) affects each controlled variable
(CV -- the measurements you care about).

In practice, this means answering questions like:

- "If I open the fuel gas valve by 5%, how much does the outlet
  temperature rise, and how quickly?"
- "Does increasing air flow affect the bridgewall temperature or just
  the stack draft?"
- "How long is the dead time between a pump speed change and a coil
  temperature response?"

**Model identification** is the process of extracting these relationships
from plant test data. You deliberately move the MVs in a planned
sequence (a "step test"), record how the CVs respond, and then use
mathematical algorithms to fit a model to the data.

The output is a **step response matrix** -- a grid of curves where each
cell (i, j) shows how CV_i responds to a unit step change in MV_j over
time. This matrix is the foundation of the MPC controller.

### Why Do We Need It?

Without an accurate model, the MPC controller cannot predict the future
behavior of the plant. Poor models lead to:

- Sluggish control (controller does not move aggressively enough)
- Oscillation (controller overreacts because gains are wrong)
- Constraint violations (controller does not know about interactions)
- Economic losses (optimizer cannot find the true optimum)

A well-identified model is the single most important ingredient in a
successful APC project. Spending an extra day on identification saves
weeks of tuning later.

### The Cumene Hot Oil Heater

Throughout this tutorial we use the **cumene hot oil heater** -- a
fired heater that supplies heat to a cumene production unit. The heater
has three manipulated variables and six controlled variables:

**Manipulated Variables (MVs):**

| Tag         | Description                  | Units |
|-------------|------------------------------|-------|
| FCV-410.SP  | Fuel gas valve setpoint      | %     |
| SC-400.SP   | Stack damper control setpoint| %     |
| FCV-411.SP  | Air flow valve setpoint      | %     |

**Controlled Variables (CVs):**

| Tag         | Description                  | Units |
|-------------|------------------------------|-------|
| XI-490.PV   | Excess O2 in flue gas        | %     |
| TIT-400.PV  | Outlet (supply) temperature  | degF  |
| TIT-402.PV  | Bridgewall temperature       | degF  |
| TIT-412.PV  | Coil outlet temperature      | degF  |
| XI-410.PV   | Stack draft                  | inH2O |
| AIT-410.PV  | CO analyzer                  | ppm   |

The step test data consists of **721 rows at 1-minute intervals**
(approximately 12 hours of data). During the test, each MV was moved
in a planned sequence while the other MVs were held steady, allowing us
to isolate each MV's effect on the CVs.

### Overview of the App Layout

When you launch APC Ident, the main window is divided into four regions:

```
+------------------+--------------------------------------+--------------+
|                  |                                      |              |
|   SIDEBAR        |        WORKSPACE                     |  PROPERTIES  |
|                  |        (trends, tables, plots)       |  PANEL       |
|   APC IDENT      |                                      |              |
|   Model ID       |                                      |  File info   |
|   Studio         |                                      |  Tag stats   |
|                  |                                      |  Conditioning|
|   WORKFLOW       |                                      |  report      |
|   * Data         |                                      |              |
|   * Tags         |                                      |              |
|   * Identify     |                                      |              |
|   * Results      |                                      |              |
|   * Analysis     |                                      |              |
|   * Validate     |                                      |              |
|                  |                                      |              |
|   v0.2.0         |                                      |              |
+------------------+--------------------------------------+--------------+
```

**Sidebar (left):** The vertical sidebar shows the six workflow steps:
Data, Tags, Identify, Results, Analysis, and Validate. Each step has a
status indicator (a colored dot):

- Green dot = completed
- Blue dot = currently active
- Gray dot = not yet started

Click any step to navigate to that panel. The sidebar also shows loaded
data files as child nodes under the Data step.

**Workspace (center):** The main content area changes depending on which
workflow step is active. In the Data step, it shows trend plots. In the
Identify step, it shows configuration forms and progress. In the Results
step, it shows the step response matrix grid.

**Properties Panel (right):** A 260-pixel-wide panel on the right side
showing contextual information -- file statistics, tag properties,
conditioning reports, and other details relevant to the current step.

**Tag Browser (left of workspace, Data step only):** When data is loaded,
a tag browser panel appears between the sidebar and the trend workspace.
It shows checkboxes for each column, color-coded by role (blue for MV,
green for CV, orange for DV), with search and filter buttons.

### Opening a Project vs Creating New

APC Ident uses project files with the `.apcident` extension. A project
stores your tag assignments, conditioning configuration, identification
settings, and references to data files. It does NOT store the raw data
itself -- only the path to the CSV/Parquet file.

**To open an existing project:**

1. Use **File > Open Project** (Ctrl+O) from the menu bar.
2. Navigate to the project file. For the cumene example:
   `apps/apc_ident/examples/cumene_hotoil_heater.apcident`
3. The project loads with all saved settings intact.

You can also open a project by passing it as a command-line argument:

```
python -m apps.apc_ident apps/apc_ident/examples/cumene_hotoil_heater.apcident
```

**To create a new project:**

1. Launch APC Ident without arguments, or use **File > New Project** (Ctrl+N).
2. A blank project opens with the name "New Project".
3. Load data in the Data step, assign tags, and configure identification.
4. Save your project with **File > Save Project** (Ctrl+S).

**To open a recent project:**

The **File** menu maintains a list of the 10 most recently opened
projects. Click any entry to open it directly.

> **Tip: Drag-and-Drop**
>
> You can drag a `.csv`, `.parquet`, or `.apcident` file directly onto
> the APC Ident window. CSV and Parquet files are loaded as data;
> `.apcident` files are opened as projects.

> **Common Mistake: Editing the CSV After Loading**
>
> If you edit the CSV file outside of APC Ident after loading it, the
> in-memory data becomes stale. Use the Reload button (circular arrow
> icon) in the Data toolbar to refresh, or re-load the file.

---

## Chapter 2: Loading and Inspecting Data

### Loading a CSV File

1. Click **Data** in the sidebar to navigate to the Data workspace.
2. Click the **Load** button (folder icon) in the toolbar at the top
   of the workspace.
3. In the file dialog, navigate to:
   `apps/apc_ident/examples/cumene/cumene_step_test.csv`
4. Click Open.

The application loads the CSV and immediately:

- Populates the **Tag Browser** on the left with one checkbox per column
- Draws **trend plots** in the workspace -- one stacked panel per
  variable, all sharing the same X-axis (time)
- Updates the **Properties Panel** on the right with file statistics
  (row count, column count, time range, file size)
- Shows the loaded file as a child node under the Data step in the sidebar

You should see 9 trend panels (3 MVs + 6 CVs) stacked vertically. The
X-axis shows sample index or time; each panel shows one variable's
raw values.

**What you should see in the Properties Panel:**

```
File: cumene_step_test.csv
Path: apps/apc_ident/examples/cumene/
Rows: 721
Columns: 9
Time range: 0.0 - 720.0 min
```

If the row count is different from what you expect, check that the
CSV was not truncated during export from the historian. If the column
count is wrong, verify the delimiter (APC Ident expects comma-
separated files by default).

**Supported file formats:**

| Format   | Extension     | Notes                                    |
|----------|---------------|------------------------------------------|
| CSV      | `.csv`        | Comma-separated, header row required     |
| Parquet  | `.parquet`    | Columnar binary, preserves types         |
| DMC Vec  | `.vec`        | Legacy DMC3 vector files (via import)    |

> **Tip: Multiple Files**
>
> You can load multiple CSV files into the same project. Each file
> appears as a child node under Data in the sidebar. The dataframes are
> concatenated along rows (time axis). This is useful when a step test
> was split across multiple historian exports.

### Understanding the Tag Browser

The tag browser panel appears on the left side of the Data workspace
once data is loaded. It has three sections:

**Search bar:** Type any part of a tag name to filter the list. For
example, typing "TIT" shows only `TIT-400.PV`, `TIT-402.PV`, and
`TIT-412.PV`.

**Quick filter buttons:**

| Button | Action                                        |
|--------|-----------------------------------------------|
| All    | Check all tags (show everything)              |
| MVs    | Show only tags assigned as MV                 |
| CVs    | Show only tags assigned as CV                 |
| None   | Uncheck all tags (clear the trend workspace)  |

**Tag checklist:** Each column from the CSV appears as a checkbox.
Tags are color-coded by their assigned role:

- **Blue** `[MV]` -- Manipulated Variable
- **Green** `[CV]` -- Controlled Variable
- **Orange** `[DV]` -- Disturbance Variable
- **Gray** (no prefix) -- Unassigned / Ignored

Check or uncheck boxes to control which variables appear in the trend
workspace. When you hover over a tag, the small stats area at the
bottom of the tag browser shows quick statistics: mean, standard
deviation, range, and NaN percentage.

**Right-click on any tag** to access a context menu with:

- **Properties** -- opens the Tag Properties dialog (detailed stats
  and role assignment)
- **Set Role > MV / CV / DV / Ignore** -- quick role assignment
  without leaving the Data step
- **Plot Only This Tag** -- solo view
- **Hide This Tag** -- uncheck it

### Using the Trend Workspace

The trend workspace shows one stacked panel per selected tag, all with
linked horizontal axes. This means panning or zooming one plot moves
all of them in sync -- essential for seeing how CVs respond to MV
changes at the same points in time.

**Navigation:**

| Action             | How                                          |
|--------------------|----------------------------------------------|
| Pan                | Click and drag on a plot                     |
| Zoom (box)         | Right-click and drag to draw a zoom box      |
| Zoom (scroll)      | Mouse wheel to zoom in/out                   |
| Reset zoom         | Right-click > "View All" or double-click     |
| Auto-range Y       | Right-click > "Auto Range"                   |

**Right-click context menu on a trend plot:**

The context menu provides data conditioning actions that operate
directly on the visible data:

- **Mark Bad Data** -- select a time region and mark it as bad
  (values are replaced with NaN and interpolated)
- **Set Cutoff Limits** -- add horizontal draggable lines for
  high/low cutoff limits
- **Detect Spikes** -- automatically find and flag outliers
- **Detect Flatline** -- find periods where the signal is stuck
- **Exclude Time Period** -- remove a time range from identification
- **Steady-State Detection** -- highlight steady-state regions

These conditioning actions are covered in detail in Chapter 3.

### Checking Data Quality

Before running identification, inspect the raw data for common problems.
Look for:

**NaN / Missing Values:** Gaps in the data appear as breaks in the
trend lines. The Properties Panel shows the NaN percentage for each
column. Columns with more than 20% NaN need attention.

**Flatline Periods:** If a transmitter is in fault or a valve is
saturated, the signal stays perfectly constant. This adds no
information to the identification and can bias the model. Look for
perfectly horizontal line segments.

**Spikes and Outliers:** Sudden jumps that are clearly instrument
noise, not real process responses. These corrupt the regression.

**Insufficient Excitation:** If an MV was not moved during the test,
or only moved once, there is not enough information to identify its
effect on the CVs. You need at least 2-3 step changes per MV,
preferably in both directions (up and down).

**Process Upsets:** If an unmeasured disturbance hit the process
during the test (a different unit tripped, ambient weather changed
drastically), the affected time region should be excluded.

> **Tip: Check MVs First**
>
> Click the **MVs** filter button in the tag browser to see only the
> manipulated variables. Verify that each MV was moved in a clear
> step pattern. Then click **CVs** to verify that the controlled
> variables responded. If a CV did not respond at all to any MV
> movement, it may not be controllable from the available MVs.

### Using the Properties Panel

The Properties Panel on the right side of the Data workspace shows
contextual information:

**File Information (top):**
- File name and path
- Number of rows and columns
- Time range (first and last timestamp)
- File size

**Conditioning Report (bottom):**
After running Auto Condition or any manual conditioning, this section
shows a detailed report of what was detected and changed:
- Number of NaN values filled
- Number of outliers clipped
- Number of flatline periods detected
- Cutoff violations flagged
- Overall data quality assessment

You can right-click on the conditioning report text to copy it to the
clipboard.

> **Common Mistake: Ignoring the Properties Panel**
>
> Many engineers skip the Properties Panel and jump straight to
> identification. This is risky. The conditioning report tells you
> exactly what the auto-conditioner did to your data. If it replaced
> 30% of a CV's values, you need to investigate why -- it might mean
> the test was poorly conducted for that variable.

---

## Chapter 3: Data Conditioning

Raw step-test data almost always contains imperfections: instrument
noise, transmitter faults, process upsets, and drift. Data conditioning
cleans the data before identification. Skipping this step is one of the
most common reasons for poor models.

### Auto Condition (One-Click)

The fastest way to condition your data is the **Auto Condition** button
(lightning bolt icon) in the Data toolbar.

Click it, and the following operations run automatically in sequence:

1. **NaN Detection:** Finds all missing values. Short gaps (1-3 samples)
   are filled by linear interpolation. Longer gaps are flagged.

2. **Outlier Clipping:** Values more than 4 sigma from the local mean
   are clipped to the 4-sigma boundary. This catches instrument spikes
   without distorting real process dynamics.

3. **Flatline Detection:** Finds periods where a signal has zero
   variance (identical consecutive values for 5+ samples). These
   periods are flagged and excluded from the regression.

4. **Cutoff Limit Detection:** Checks if any signal exceeds
   pre-configured high/low limits. Values outside limits are replaced.

5. **Bad Data Replacement:** Flagged regions are replaced with
   interpolated values so the identification algorithm sees a clean,
   continuous signal.

After Auto Condition runs, three things happen:

- The trend plots update to show the conditioned data
- The **Before/After** toggle button becomes active
- The Properties Panel shows a detailed conditioning report

A typical conditioning report for the cumene heater looks like:

```
Conditioning Report
==================
Columns processed:  9
Total samples:      721

FCV-410.SP:  0 NaN filled, 0 spikes clipped, 0 flatline regions
SC-400.SP:   0 NaN filled, 0 spikes clipped, 0 flatline regions
FCV-411.SP:  0 NaN filled, 0 spikes clipped, 0 flatline regions
XI-490.PV:   0 NaN filled, 2 spikes clipped, 0 flatline regions
TIT-400.PV:  0 NaN filled, 0 spikes clipped, 0 flatline regions
TIT-402.PV:  0 NaN filled, 1 spikes clipped, 0 flatline regions
TIT-412.PV:  0 NaN filled, 0 spikes clipped, 0 flatline regions
XI-410.PV:   0 NaN filled, 0 spikes clipped, 0 flatline regions
AIT-410.PV:  0 NaN filled, 3 spikes clipped, 0 flatline regions

Overall: GOOD quality -- 6 values clipped out of 6489 total
```

Since this is simulated data, there are very few issues. Real
plant data typically has more NaN values and more spikes from
instrument noise.

> **Tip: Auto Condition Is Non-Destructive**
>
> Auto Condition does not modify your original CSV file. It creates
> a conditioned copy in memory. You can always get back to the raw
> data by toggling the Before/After button or by reloading the file.

### Manual Conditioning via Right-Click

For finer control, right-click on any trend plot to access manual
conditioning tools:

#### Setting Cutoff Limits

Cutoff limits define the valid engineering range for a variable. Any
value outside these limits is treated as bad data.

1. Right-click on a trend plot and select **Set Cutoff Limits**.
2. Two horizontal dashed lines appear on the plot -- one red (high
   limit) and one blue (low limit).
3. **Drag the lines** to adjust the limits. As you drag, any data
   points outside the limits turn red to highlight violations.
4. The limits are saved in the project and applied during conditioning.

For the cumene heater example, reasonable cutoff limits might be:

| Variable    | Low Limit | High Limit | Reason                          |
|-------------|-----------|------------|---------------------------------|
| TIT-400.PV  | 400       | 900        | Physical range of thermocouple  |
| TIT-402.PV  | 500       | 1200       | Bridgewall physical range       |
| XI-490.PV   | 0         | 15         | O2 cannot be negative or >21%   |
| XI-410.PV   | -2.0      | 0.5        | Draft is slightly negative      |
| AIT-410.PV  | 0         | 500        | CO analyzer range               |

#### Detecting and Removing Flatline Data

A flatline is a period where a signal does not change at all. This
usually means a transmitter is frozen, a valve is saturated, or the
DCS is holding a last-good-value.

1. Right-click on the trend plot and select **Detect Flatline**.
2. The algorithm scans for consecutive identical values (default
   threshold: 5 samples minimum).
3. Detected flatline regions are highlighted with a shaded overlay.
4. You can choose to exclude these regions or replace them with
   interpolated values.

#### Detecting and Removing Spikes

Spikes are sudden, short-lived deviations caused by instrument noise,
communication errors, or electrical interference.

1. Right-click on the trend plot and select **Detect Spikes**.
2. The algorithm uses a rolling-window z-score approach. Points more
   than 4 sigma from the local mean (over a configurable window) are
   flagged.
3. Flagged points appear as red X markers on the plot.
4. Spikes are replaced with linearly interpolated values during
   conditioning.

#### Marking Bad Data Regions

Sometimes you know that a time period is bad (a process upset occurred,
an instrument was being calibrated, etc.) but the automatic detectors
do not catch it.

1. Right-click on the trend plot and select **Mark Bad Data**.
2. Click and drag on the plot to select a time region. The region
   highlights in orange.
3. All data points in the selected region are flagged as bad.
4. During conditioning, bad regions are replaced with interpolation.

#### Excluding Time Periods

Excluding a time period removes it entirely from the identification
dataset, rather than interpolating through it. Use this when a large
upset makes a whole section of data unreliable.

1. Right-click and select **Exclude Time Period**.
2. Select the time range to exclude.
3. The excluded region appears with a gray overlay and is skipped
   during identification.

You can also use the **Segments bar** at the bottom of the workspace
to define and manage data segments. Click **+ Add** to create a new
segment, or click the X on an existing segment to remove it.

### Steady-State Detection (SSD)

Steady-state detection identifies periods where the process is at or
near steady state. This is useful for:

- Verifying that the process reached steady state between MV steps
- Finding good initial conditions for identification
- Assessing whether the step test was well-designed

Click the **SSD** button in the toolbar to run automatic steady-state
detection. The algorithm uses a ratio test:

```
R(k) = variance(short window) / variance(long window)
```

When R(k) is small, the signal is in steady state. Detected steady
periods are highlighted with green shading on the trend plots.

The SSD configuration (window sizes, threshold) is auto-configured
based on the data characteristics, but you can adjust it through the
Properties Panel.

> **Tip: SSD and Model Length**
>
> The time between the last MV step and the next detected steady state
> gives you an estimate of the process settling time. Your model length
> (n_coeff) should be at least 1.5x the longest settling time. If the
> process never reaches steady state between steps, your model length
> may be too short -- or the steps were made too close together.

### Before/After Toggle

The **Before/After** button in the toolbar toggles between the raw
(unconditioned) and conditioned data views. This is invaluable for
verifying that conditioning did not distort real process dynamics.

- **Before (unchecked):** Shows the original raw data as loaded from CSV.
- **After (checked):** Shows the conditioned data with all corrections
  applied.

Toggle back and forth to visually confirm:

- Spikes were correctly identified (not real process transients)
- Flatline replacements look reasonable
- Cutoff clipping did not remove valid data
- The overall shape of the response curves is preserved

> **Common Mistake: Over-Conditioning**
>
> Aggressive conditioning can remove real process dynamics. If the
> sigma threshold for spike detection is set too low (e.g., 2.0 instead
> of 4.0), normal process noise gets clipped and the model will
> underestimate the true process gain. Always check the Before/After
> comparison.

### Resampling to a Uniform Sample Period

Step-test data from historians sometimes has irregular time spacing --
rows at 58 seconds, 62 seconds, 61 seconds apart, etc. The
identification algorithms require a uniform sample period.

1. Click the **Resample** button in the toolbar.
2. A dialog shows the detected sample rate statistics: median interval,
   standard deviation, suggested resample rate.
3. Accept the suggested rate or enter a custom period (in seconds).
4. Click OK to resample the data using linear interpolation.

The resampled data replaces the in-memory dataframe. The original
file is not modified.

> **Tip: Check the Suggested Rate**
>
> For the cumene heater example, the data is already at uniform
> 1-minute intervals. The resample dialog will confirm this and
> suggest 60.0 seconds. If your data comes from a historian with
> "exception-based" reporting (values only recorded on change), you
> may see highly irregular intervals and should definitely resample.

---

## Chapter 4: Tag Assignment

Tag assignment tells the identification engine which columns are inputs
(MVs), which are outputs (CVs), and which are disturbances (DVs). This
step maps the CSV column names to controller variable roles.

### Assigning MV, CV, DV Roles

Navigate to the **Tags** step by clicking Tags in the sidebar. You see
a table with one row per CSV column:

| CSV Column  | Role    | Controller Tag | Mean    | Std     | NaN % |
|-------------|---------|----------------|---------|---------|-------|
| FCV-410.SP  | Ignore  |                | 0.6500  | 0.0354  | 0.0%  |
| SC-400.SP   | Ignore  |                | 0.9800  | 0.0283  | 0.0%  |
| FCV-411.SP  | Ignore  |                | 0.6500  | 0.0316  | 0.0%  |
| XI-490.PV   | Ignore  |                | 3.2100  | 0.8900  | 0.0%  |
| TIT-400.PV  | Ignore  |                | 712.40  | 18.200  | 0.0%  |
| ...         | ...     | ...            | ...     | ...     | ...   |

For each row, set the **Role** dropdown to one of:

- **MV** -- Manipulated Variable (an input you controlled during the test)
- **CV** -- Controlled Variable (an output you want the controller to regulate)
- **DV** -- Disturbance Variable (a measured disturbance you cannot control)
- **Ignore** -- Not used in identification

For the cumene heater, assign:

| CSV Column  | Role | Controller Tag  |
|-------------|------|-----------------|
| FCV-410.SP  | MV   | FCV-410.SP      |
| SC-400.SP   | MV   | SC-400.SP       |
| FCV-411.SP  | MV   | FCV-411.SP      |
| XI-490.PV   | CV   | XI-490.PV       |
| TIT-400.PV  | CV   | TIT-400.PV      |
| TIT-402.PV  | CV   | TIT-402.PV      |
| TIT-412.PV  | CV   | TIT-412.PV      |
| XI-410.PV   | CV   | XI-410.PV       |
| AIT-410.PV  | CV   | AIT-410.PV      |

The **Controller Tag** column lets you assign a different name from
the CSV column name. This is useful when your CSV columns are historian
tag names (e.g., `UNIT1.FIC101.PV`) but you want shorter names in
the controller configuration (e.g., `FIC-101.PV`).

The summary bar at the top shows the current count: **MV: 3 | CV: 6 | DV: 0**.
When you have at least 1 MV and 1 CV assigned, the counter turns green,
indicating you have enough for identification.

### Using the Tags Tab vs Right-Click in Tag Browser

There are two ways to assign roles:

**Tags tab (recommended for bulk assignment):**
Navigate to Tags in the sidebar. The full table lets you see and edit
all assignments at once. Use the Role dropdown for each row.

**Right-click in the Tag Browser (quick single-tag assignment):**
In the Data step, right-click any tag in the tag browser panel and
select **Set Role > MV / CV / DV / Ignore**. This is faster when you
just need to change one or two tags without leaving the Data view.

Both methods update the same underlying tag assignment list. Changes
made in one place are immediately reflected in the other.

### Tag Properties Dialog

Double-click any tag name in the tag browser, or right-click and
select **Properties**, to open the Tag Properties dialog. This shows:

- **CSV Column:** The original column name (read-only)
- **Controller Tag:** Editable name for the controller configuration
- **Role:** MV / CV / DV / Ignore dropdown

And detailed statistics:

```
Statistics (721 samples):
  Mean:    712.4000
  Std:     18.2000
  Min:     678.3000
  Max:     748.9000
  Median:  711.8000
  NaN:     0 (0.0%)
  Range:   70.6000
```

Click OK to save changes, or Cancel to discard.

### Auto-Assign Feature

The **Auto-Assign** button in the Tags toolbar provides a one-click
starting point: it assigns the first half of the columns as MV and the
second half as CV, and sets the Controller Tag to match the CSV column
name.

For the cumene heater with 9 columns, Auto-Assign would set columns
1-4 as MV and columns 5-9 as CV. This is close to correct but may
need adjustment -- you should always verify the assignments manually.

The **Clear All** button resets every tag to Ignore.

> **Tip: Name Your Controller Tags Clearly**
>
> The Controller Tag names carry through to the exported model bundle
> and ultimately to the controller configuration in APC Architect. Use
> consistent, meaningful names with instrument type and loop number
> (e.g., `TIT-400.PV` not `Temperature`). Your future self will
> thank you.

> **Common Mistake: Forgetting DVs**
>
> If you have measured disturbance variables in your data (ambient
> temperature, feed composition, upstream flow changes), assign them as
> DVs. The identification engine can model their effect on the CVs,
> giving the controller feedforward capability. Ignoring DVs means the
> controller treats their effects as unmeasured disturbances, which
> it handles more slowly.

---

## Chapter 5: FIR Identification

### Understanding FIR Identification

FIR (Finite Impulse Response) identification is the workhorse algorithm
for APC model building. It is the same method used in AspenTech DMC3
and Honeywell RMPCT.

**Conceptually**, FIR identification answers this question: "Given the
history of MV moves and CV measurements, what set of step response
coefficients best predicts the CV values?"

**Mathematically**, for each CV, the algorithm builds a Toeplitz matrix
from the MV move history and solves a linear regression:

```
y = A * h + e

where:
  y = measured CV values          (N x 1 vector)
  A = Toeplitz matrix of MV moves (N x n_coeff*nu matrix)
  h = FIR coefficients to find    (n_coeff*nu x 1 vector)
  e = residual error              (N x 1 vector)
```

The solution `h` gives the impulse response coefficients. The
cumulative sum of these coefficients gives the step response -- the
curve you see in the results.

Three solution methods are available:

| Method | Full Name              | Best For                              |
|--------|------------------------|---------------------------------------|
| DLS    | Direct Least Squares   | Open-loop step tests with independent MV moves |
| COR    | Correlation-Based      | Closed-loop data or correlated MV moves |
| Ridge  | L2-Regularized LS      | Short datasets or collinear inputs    |

For most open-loop step tests (including our cumene heater), **DLS** is
the right choice.

### Configuring Parameters

Navigate to the **Identify** step in the sidebar. The left panel shows
the configuration form:

#### Model Length (n_coeff)

The number of FIR coefficients to estimate per MV-CV pair. This
determines how far into the future the model can predict.

**Rule of thumb:** Set n_coeff to at least 1.5x the longest settling
time of any CV, measured in sample periods.

For the cumene heater at 1-minute sampling:
- Temperature CVs settle in about 30-40 minutes
- Draft settles in about 10 minutes
- A model length of 60 (= 60 minutes) is a good starting point

**Too short:** The model truncates the response before it settles,
underestimating the steady-state gain.

**Too long:** More coefficients to estimate means more noise in the
tail of the response. The model may show spurious oscillation at
long time horizons.

#### Sample Period (dt)

The sample time of the data in seconds. For the cumene heater: **60.0**
(one sample per minute).

This value must match the actual data sampling rate. If you resampled
the data in the Data step, use the resampled period here.

#### Method

Choose between DLS, COR, and Ridge:

- **DLS (Direct Least Squares):** Default. Best for open-loop tests
  where MVs were moved independently. Fast and unbiased.

- **COR (Correlation-Based):** Use when the data contains feedback
  (closed-loop operation) or when MVs were moved simultaneously.
  Slightly noisier than DLS but handles correlation better.

- **Ridge (L2-Regularized):** Use when the dataset is short (fewer
  than 3x n_coeff samples) or when multiple MVs are collinear
  (moved together). The **Ridge Alpha** parameter controls the
  regularization strength:
  - Alpha = 0 is equivalent to DLS
  - Alpha = 1.0 is a good default
  - Higher values produce smoother but potentially biased models

#### Smoothing

FIR coefficients are often noisy, especially in the tail. Smoothing
reduces this noise:

| Method     | What It Does                                        |
|------------|-----------------------------------------------------|
| None       | No smoothing. Raw coefficients.                     |
| Exponential| Forces the tail to decay exponentially to the final value |
| Savgol     | Savitzky-Golay polynomial smoothing (local filter)  |
| Asymptotic | Projects tail coefficients toward the steady-state gain |
| Pipeline   | Applies Exponential, then Savgol, then Asymptotic in sequence |

**Pipeline** is the recommended default. It handles most noise patterns
well.

#### Preprocessing Options

- **Detrend:** Remove linear trend from data before identification.
  Recommended for most cases.
- **Remove Mean:** Subtract the mean from each signal. Standard
  practice for step response identification.
- **Clip Sigma:** Outlier clipping threshold (standard deviations).
  Default 4.0.
- **Holdout Fraction:** Reserve a fraction of data (from the end) for
  validation. Default 0.2 (20%). See Chapter 10 for details.

### Smart Config: One-Click Auto-Configuration

The **Smart Config** button analyzes your data and automatically
recommends values for all identification parameters. It examines:

- **Sample period:** Detected from the data index
- **Model length:** Estimated from the autocorrelation decay time
  of the CVs (approximating the settling time)
- **Method:** DLS if MV cross-correlations are low; Ridge if they are
  high
- **Smoothing:** Pipeline by default
- **CV types:** Detects ramp/pseudoramp variables (see Chapter 12)
- **Data quality:** Flags NaN, flatline, spike, and drift issues
- **Excitation adequacy:** Grades each MV's excitation (enough
  moves? large enough steps? varied enough frequency?)

After Smart Config runs, the status panel on the right shows a detailed
report explaining every recommendation and its rationale. You can
accept all recommendations or modify individual parameters.

For the cumene heater, Smart Config typically recommends:

```
n_coeff: 60        (based on ~40-minute settling time)
dt: 60.0            (detected from 1-minute spacing)
method: DLS         (low MV cross-correlation)
smoothing: Pipeline
detrend: Yes
remove_mean: Yes
clip_sigma: 4.0
```

> **Tip: Always Run Smart Config First**
>
> Even if you plan to manually tune parameters, Smart Config gives you
> a solid baseline. Its data quality report alone is worth the click --
> it catches problems you might miss by visual inspection.

### Running Identification

Once parameters are configured:

1. Click the **IDENTIFY** button (or press F5).
2. A progress bar appears showing the identification stages:
   - "Building regression matrix..."
   - "Solving FIR identification..."
   - "Done"
3. For the cumene heater (3 MVs x 6 CVs, 721 samples), identification
   takes 1-3 seconds.

When identification completes, the application automatically:

- Stores the result in the session
- Marks the "Identify" step as done in the sidebar
- Enables the Results, Analysis, and Validate steps
- Switches to the Results view to show you the step response matrix

### Understanding the Results

The **Results** step shows three main displays:

#### Step Response Matrix

The central area shows a grid of small plots -- one for each CV-MV
combination. For the cumene heater (6 CVs x 3 MVs = 18 cells):

```
           FCV-410.SP    SC-400.SP     FCV-411.SP
XI-490.PV  [curve]       [curve]       [curve]
TIT-400.PV [curve]       [curve]       [curve]
TIT-402.PV [curve]       [curve]       [curve]
TIT-412.PV [curve]       [curve]       [curve]
XI-410.PV  [curve]       [curve]       [curve]
AIT-410.PV [curve]       [curve]       [curve]
```

Each cell shows the cumulative step response: how the CV responds over
time to a unit step change in the MV. The X-axis is time (in sample
periods) and the Y-axis is the change in the CV.

**Key things to look for:**

- **Shape:** Most responses should be monotonic (rising or falling
  smoothly to a steady-state value). Oscillatory or erratic shapes
  suggest noise or poor model fit.
- **Dead time:** The flat region at the start before the response
  begins. Should match your physical understanding of the process.
- **Steady-state gain:** The final value the curve settles to. This
  is the ratio of CV change to MV change at steady state.
- **Settling time:** How long it takes to reach ~95% of the final
  value.
- **Zero cells:** If a cell shows a flat line at zero, it means the
  identification found no relationship between that MV and CV. This
  may be correct (no physical coupling) or may indicate insufficient
  excitation.

#### Gain Matrix

The side panel shows the steady-state gain matrix as a table:

```
           FCV-410.SP   SC-400.SP    FCV-411.SP
XI-490.PV    -2.34        0.12         1.87
TIT-400.PV   45.6        -3.21         2.10
TIT-402.PV   62.3        -5.40         3.80
...
```

Each value is the final step response coefficient -- the steady-state
gain for that MV-CV pair. Positive means the CV increases when the MV
increases; negative means they move in opposite directions.

Check the gain signs against your process knowledge:

- Increasing fuel gas (FCV-410) should increase temperatures (positive gain)
- Increasing fuel gas should decrease excess O2 (negative gain)
- Increasing air flow (FCV-411) should increase excess O2 (positive gain)

If a gain sign contradicts your process knowledge, investigate further.
The model may be wrong, or the step test may not have excited that
particular relationship adequately.

#### Channel Fits

The Channel Fits table shows per-CV quality metrics:

| CV         | R-squared | RMSE   | LB-p    |
|------------|-----------|--------|---------|
| XI-490.PV  | 0.87      | 0.234  | 0.42    |
| TIT-400.PV | 0.94      | 1.230  | 0.18    |
| TIT-402.PV | 0.91      | 2.100  | 0.31    |
| ...        | ...       | ...    | ...     |

**Example interpretation for the cumene heater:**

Looking at the TIT-400.PV row (outlet temperature):
- The FCV-410.SP column should show a rising curve (fuel increases
  temperature) with a dead time of 2-5 minutes and settling in
  30-40 minutes.
- The SC-400.SP column should show a smaller response (stack damper
  has indirect effect on outlet temp).
- The FCV-411.SP column should show a moderate response (more air
  changes combustion dynamics).

If any curve looks physically implausible -- for example, increasing
fuel gas causes temperature to decrease -- flag it for investigation
before proceeding.

### What R-squared, RMSE, and Ljung-Box Tell You

**R-squared (R-squared):** The fraction of CV variance explained by the model.
Ranges from 0 to 1.

| R-squared | Interpretation                                     |
|-----------|----------------------------------------------------|
| > 0.90    | Excellent fit                                      |
| 0.80-0.90 | Good fit, acceptable for most applications         |
| 0.60-0.80 | Moderate fit, investigate further                  |
| < 0.60    | Poor fit, model may not be reliable                |

**RMSE (Root Mean Square Error):** The average prediction error in
engineering units. Compare this to the CV's operating range -- RMSE
should be a small fraction of the range.

**Ljung-Box p-value (LB-p):** Tests whether the residuals are white
noise (random). A high p-value (> 0.05) means the residuals are
white -- good. A low p-value means the model missed some dynamics.

| LB-p  | Interpretation                                       |
|-------|------------------------------------------------------|
| > 0.10| Residuals look like white noise. Good model.         |
| 0.05  | Borderline. Model may be missing minor dynamics.     |
| < 0.05| Residuals are correlated. Model is missing something.|

> **Common Mistake: Obsessing Over R-squared**
>
> R-squared depends heavily on how much the CV moved during the test.
> A CV that barely moved will have low R-squared even with a perfect
> model. Always consider R-squared alongside RMSE and the visual
> quality of the step response curves.

### The Quality Scorecard

The identification engine computes a comprehensive Quality Scorecard
that grades five categories on a traffic-light scale:

| Category          | What It Checks                            | Grades        |
|-------------------|-------------------------------------------|---------------|
| DATA QUALITY      | NaN, flatline, outliers, sample count     | GREEN/YELLOW/RED |
| EXCITATION        | MV move count, move size, frequency       | GREEN/YELLOW/RED |
| MODEL FIT         | R-squared, RMSE, residual whiteness       | GREEN/YELLOW/RED |
| CONTROLLABILITY   | Gain matrix condition, colinearity, RGA   | GREEN/YELLOW/RED |
| UNCERTAINTY       | SS gain uncertainty, dynamic uncertainty  | GREEN/YELLOW/RED |

The **overall grade** is the worst grade across all categories. Each
category includes specific findings and actionable recommendations.

For example:

```
Model Quality Scorecard
==================================================
Overall: [!!] YELLOW

[OK] DATA QUALITY: GREEN
     721 samples, 0 NaN, 0 flatline periods detected
[OK] EXCITATION: GREEN
     All MVs have 3+ step changes with adequate amplitude
[!!] MODEL FIT: YELLOW
     AIT-410.PV R^2 = 0.68 (below 0.80 threshold)
  -> Consider increasing model length or adding DV
[OK] CONTROLLABILITY: GREEN
     Condition number = 12.4 (acceptable)
[OK] UNCERTAINTY: GREEN
     All gains within 15% confidence
```

> **Tip: GREEN Does Not Mean Perfect**
>
> A GREEN scorecard means the model meets minimum quality standards.
> You should still visually inspect the step response curves and
> validate against holdout data (Chapter 10). The scorecard catches
> obvious problems but cannot judge whether the model makes physical
> sense.

---

## Chapter 6: Subspace Identification

### When to Use Subspace vs FIR

Subspace identification produces a **state-space model** (A, B, C, D
matrices) rather than FIR coefficients. The step response is then
derived from the state-space model.

Use subspace identification when:

- **You need a low-order model.** FIR models have n_coeff parameters
  per MV-CV pair; state-space models may need only 4-8 states for
  the entire system.
- **The process has strong interactions.** Subspace methods capture
  MIMO interactions more naturally because they identify the full
  system simultaneously rather than one CV at a time.
- **You have closed-loop data.** Subspace methods (especially CVA)
  handle mild feedback better than DLS.
- **You want a state-space model directly** for simulation or
  advanced control design.

Stick with FIR when:

- You have a well-designed open-loop step test
- The process is relatively simple (few interactions)
- You want direct control over individual MV-CV curves
- You are comfortable with the DMC3-style workflow

For the cumene heater tutorial, we focus on FIR (Chapter 5) because the
data comes from a well-designed open-loop step test. But you can try
subspace identification on the same data to compare results.

### Configuring Subspace Identification

In the Identify step, the left panel has both FIR and Subspace
configuration sections. The Subspace section has these parameters:

#### Algorithm (Method)

| Algorithm | Full Name                     | Characteristics               |
|-----------|-------------------------------|-------------------------------|
| N4SID     | Numerical Subspace State Space| Most popular, good all-around |
| MOESP     | Multivariable Output-Error SS | Better for systems with noise |
| CVA       | Canonical Variate Analysis    | Best for closed-loop data     |

**N4SID** is the recommended default.

#### Model Order (nx)

The number of states in the state-space model. This is analogous to
n_coeff in FIR but much smaller.

- **Auto:** Leave blank or set to 0. The algorithm inspects the
  singular value gap to automatically choose the order.
- **Manual:** Set a specific value. Typical range: 2-10 for most
  industrial processes.

**Too low:** The model cannot capture all the dynamics. Step responses
will be oversimplified.

**Too high:** The model overfits the data. Step responses may oscillate
or diverge.

#### Future Horizon (f)

The number of future time steps used in the block Hankel matrices.
Must be larger than the model order plus the maximum dead time.

**Rule of thumb:** Set f to 1.5-2x the expected model order. For the
cumene heater with expected order 4-6, set f = 10-20.

### Expert Mode Options

Check the "Expert Mode" checkbox to reveal advanced settings:

- **Differencing:** First-difference the data before identification.
  Useful for integrating processes (levels, inventories).
- **Oversampling:** Use a finer internal sample rate during
  identification, then decimate the result. Can improve accuracy for
  fast dynamics.
- **Force Stability:** Reflect any unstable eigenvalues of the
  identified A matrix inside the unit circle. Recommended.
- **Force Zero D:** Constrain D = 0 (no direct feedthrough). Enable
  for strictly proper systems (most thermal and flow processes).
- **Estimate Kalman Gain (K):** Estimate the innovation form gain
  from residuals. Useful for simulation fidelity but not needed for
  MPC.
- **SV Threshold:** Relative threshold for the singular value gap
  detector (used in auto model order selection).

### CV Grouping for Large Systems

For systems with many CVs (20+), identifying all CVs simultaneously
produces an enormous state-space model. CV grouping splits the problem
into smaller sub-problems:

- **Auto:** Groups CVs by cross-correlation. CVs that are highly
  correlated share dynamics and are identified together.
- **One Per Group:** Each CV in its own group (MISO decomposition).
  Simplest but ignores CV-CV interactions.
- **All In One:** All CVs in one group. Full MIMO but may produce
  an impractically large model.

For the cumene heater with 6 CVs, "All In One" works fine. For a large
refinery column with 30 CVs, use Auto or One Per Group.

### Running Subspace Identification

To run subspace identification on the cumene heater data:

1. Navigate to the **Identify** step.
2. In the Subspace Config section, set:
   - Method: **N4SID**
   - Model Order: **0** (auto-detect)
   - Future Horizon: **20**
3. Check **Force Stability** and **Force Zero D** in Expert Mode.
4. Click **IDENTIFY**.

The status panel shows:

```
Building Hankel matrices...
Computing oblique projection...
Singular value decomposition...
Model order selected: 5 (from SV gap)
Estimating A, B, C, D...
Done (0.8s)
```

The auto-detected model order of 5 means the subspace algorithm
determined that 5 states are sufficient to capture the dominant
dynamics of the 3-input, 6-output system.

> **Tip: Interpreting the Singular Value Plot**
>
> The subspace algorithm computes singular values that indicate how
> much each additional state contributes to the model. A clear "gap"
> or "elbow" in the singular value plot indicates the right model
> order. If there is no clear gap, the auto-detection may choose a
> conservative (higher) order. In that case, try manually setting
> a lower order and comparing the results.

### Comparing FIR vs Subspace Results

After running both FIR and subspace identification, you can compare
them in the Results step:

1. Run FIR identification first. The results are stored.
2. Run subspace identification. Both results are now available.
3. In the Results step, the step response grid can overlay both sets
   of curves for visual comparison.

Look for:

- **Agreement on gain signs:** If FIR and subspace disagree on whether
  a gain is positive or negative, investigate further.
- **Agreement on dead times:** Both methods should find similar dead
  times for the same MV-CV pairs.
- **Curve smoothness:** Subspace curves are inherently smoother
  (parameterized by a low-order model). FIR curves may be noisier
  but capture more detail.

> **Tip: Use FIR for the Controller, Subspace for Sanity**
>
> A practical approach is to use FIR as your primary identification
> method (since MPC controllers work directly with step response
> coefficients) and run subspace as a cross-check. If the two methods
> broadly agree, you have confidence in the model. If they disagree
> significantly, investigate the discrepancy.

---

## Chapter 7: Multi-Trial and Model Assembly

### Running Multiple Parameter Sets

Real-world identification is not a one-shot process. Different
parameter settings (model length, method, alpha) produce different
models, and the "best" settings may vary by CV-MV pair.

Multi-trial identification automates this exploration:

1. In the Identify step, check the **Run multiple trials** checkbox
   in the Multi-Trial section.
2. Specify which parameter to vary and its values. For example:
   - Vary `n_coeff`: `40, 60, 80`
   - This creates three trials with model lengths of 40, 60, and 80.
3. Optionally vary additional parameters:
   - Vary method: `dls, ridge`
   - Vary ridge alpha: `0.1, 1.0, 10.0`
   - Combinations are crossed: 3 n_coeff x 2 methods = 6 trials
4. Click **IDENTIFY**. All trials run sequentially.

The status panel shows progress for each trial:

```
Trial 1/3: n_coeff=40 ... done (1.2s)
Trial 2/3: n_coeff=60 ... done (1.5s)
Trial 3/3: n_coeff=80 ... done (1.8s)
```

You can also run multi-trial via the sidebar context menu: right-click
the Identify step and select **Run Multi-Trial**.

### Comparing Trials Side-by-Side

After multi-trial completes, navigate to the **Results** step. The step
response grid now overlays all trial curves on each cell, using
different colors:

- Trial 1 (n_coeff=40): blue
- Trial 2 (n_coeff=60): green
- Trial 3 (n_coeff=80): orange

This visual comparison instantly shows:

- **Which model length captures the full response:** If the n_coeff=40
  curve is still rising at sample 40 while the n_coeff=60 curve has
  settled, 40 is too short.
- **Which method is smoothest:** Ridge curves are typically smoother
  than DLS.
- **Where trials disagree:** If all three trials produce similar curves
  for a cell, you can be confident in that response. If they diverge,
  the data may be insufficient for that pair.

### Picking the Best Trial Per CV-MV Cell

The Model Assembly section on the right side of the Results step lets
you select which trial to use for each CV-MV combination:

The Assembly Table shows:

| CV / MV                  | Trial    | Gain    |
|--------------------------|----------|---------|
| XI-490.PV / FCV-410.SP   | Trial 2  | -2.34   |
| XI-490.PV / SC-400.SP    | Trial 1  | 0.12    |
| TIT-400.PV / FCV-410.SP  | Trial 3  | 45.6    |
| ...                      | ...      | ...     |

For each row, use the Trial dropdown to select which trial's
coefficients to use for that particular cell. The system starts with
the "best" trial auto-selected based on fit metrics (highest R-squared
for that CV).

You can mix and match: use Trial 2 for most cells but Trial 3 for
a specific slow-responding CV where the longer model captured the
tail better.

### Building the Master Model

Once you have selected the best trial for each cell:

1. Click **Build Master Model**.
2. The assembler extracts the selected coefficients from each trial
   and combines them into a single coherent model.
3. The master model status label updates:
   "Master model assembled: 6 CVs x 3 MVs, 60 coefficients"

The master model is now the baseline for curve operations (Chapter 8)
and export (Chapter 11).

> **Tip: You Do Not Need Multi-Trial for Simple Cases**
>
> For the cumene heater tutorial, a single run with Smart Config
> settings usually produces a good model. Multi-trial is most
> valuable for large, complex systems where different CVs have
> very different dynamics.

> **Common Mistake: Mixing Incompatible Trials**
>
> If you ran trials with different sample periods (dt), the
> coefficients are on different time scales and cannot be mixed.
> Only mix trials that share the same dt.

---

## Chapter 8: Curve Operations

### Why You Need to Shape Curves

Even after identification, individual step response curves often need
adjustment:

- **Dead time correction:** The identified dead time may be off by a
  sample or two. For tight control, getting the dead time right matters
  more than getting the gain perfect.
- **Gain correction:** Process knowledge may tell you the true gain is
  different from what the data shows (perhaps the test did not reach
  complete steady state).
- **Noise cleanup:** Some curves may have residual noise that smoothing
  did not fully remove.
- **Missing relationships:** A cell may show zero response, but you
  know from process knowledge that a relationship exists. You can
  insert a first-order curve manually.
- **Engineering constraints:** You may know that a gain must be
  positive, but the identification found a small negative value due
  to noise.

Curve operations let you modify individual cells of the step response
matrix without re-running identification.

### Available Operations

The Curve Operations section on the right side of the Results step
provides these operations:

| Operation    | Parameters            | What It Does                                  |
|--------------|-----------------------|-----------------------------------------------|
| SHIFT        | Shift (samples)       | Move the curve left or right in time. Positive = add dead time (shift right, insert leading zeros). Negative = reduce dead time (shift left). |
| GAIN         | Target gain           | Replace the steady-state gain. Draws a ramp from (time_to_response, 0) to (end, target_gain). |
| GSCALE       | Target gain           | Scale the entire curve so the final value equals the target gain. Preserves the shape. |
| FIRSTORDER   | Delay, Tau, Gain      | Replace the curve with a first-order step response: K * (1 - exp(-(t-delay)/tau)). |
| SECONDORDER  | Delay, Tau, Zeta, Gain| Replace with a second-order response. Supports underdamped (oscillatory) and overdamped shapes. |
| LEADLAG      | R (ratio), T (lag)    | Apply a lead-lag filter: (R*T*s + 1) / (T*s + 1). Useful for fine-tuning dynamic shape. |
| MULTIPLY     | Factor                | Multiply all coefficients by a constant. Scales the entire response proportionally. |
| ZERO         | (none)                | Set all coefficients to zero. Use to remove a spurious relationship. |
| UNITY        | (none)                | Set all coefficients to 1.0. Useful as a starting point for manual curve entry. |

### Applying Operations Per Cell

1. In the Curve Operations section, select the **CV** and **MV** from
   the dropdown menus to target a specific cell.
2. Select the **Operation** from the Op dropdown.
3. Enter the **parameters** (the form updates to show the relevant
   parameters for the selected operation).
4. Click **Apply to Cell**.

The step response grid immediately updates to show the modified curve.
The original curve remains visible as a faded line for comparison.

**Example: Adjusting Dead Time**

Suppose the identified response for TIT-400.PV / FCV-410.SP shows a
dead time of 2 minutes, but you know from operating experience that
the real dead time is 4 minutes:

1. Select CV: TIT-400.PV, MV: FCV-410.SP
2. Select Op: SHIFT
3. Set Shift: 2 (add 2 samples = 2 minutes of dead time)
4. Click Apply to Cell

**Example: Correcting a Gain**

The identified gain for XI-490.PV / FCV-411.SP is 1.87, but process
simulation suggests it should be closer to 2.5:

1. Select CV: XI-490.PV, MV: FCV-411.SP
2. Select Op: GSCALE
3. Set Target Gain: 2.5
4. Click Apply to Cell

The entire curve is scaled up proportionally so the final value is 2.5.

### Undo/Redo

Click the **Undo** button to reverse the most recent curve operation
on the selected cell. Operations are tracked in a per-cell history, so
you can undo multiple operations in sequence.

The operations status label at the bottom shows a log of applied
operations:

```
Applied: SHIFT(shift=2) to TIT-400.PV / FCV-410.SP
Applied: GSCALE(gain=2.5) to XI-490.PV / FCV-411.SP
Undone: GSCALE(gain=2.5) on XI-490.PV / FCV-411.SP
```

**Example: Inserting a Known First-Order Response**

The identified response for AIT-410.PV (CO analyzer) / SC-400.SP
(stack damper) shows a flat zero line, but you know from combustion
engineering that the stack damper affects CO emissions. The effect
was not captured because the SC-400.SP steps during the test were
small and the CO analyzer has high noise.

To insert a first-order response based on process knowledge:

1. Select CV: AIT-410.PV, MV: SC-400.SP
2. Select Op: FIRSTORDER
3. Set Delay: 5.0 (5-minute dead time)
4. Set Tau (time constant): 15.0 (15-minute time constant)
5. Set Gain: -8.0 (negative: opening stack damper reduces CO)
6. Click Apply to Cell

The cell now shows a smooth first-order step response replacing the
flat zero line. This is a judgment call -- you are inserting process
knowledge that the data could not provide. Document your reasoning
in the project notes.

**Example: Removing a Spurious Response**

The identified response for XI-410.PV (draft) / FCV-410.SP (fuel gas)
shows a very small, noisy response with a gain of 0.003. From your
process knowledge, fuel gas has no direct effect on stack draft (draft
is driven by the stack damper and air flow, not fuel). This tiny
response is noise fitting.

1. Select CV: XI-410.PV, MV: FCV-410.SP
2. Select Op: ZERO
3. Click Apply to Cell

The cell now shows a flat zero line. This tells the controller that
fuel gas does not affect draft, preventing unnecessary MV movements.

### Building the Final Assembled Model

After all curve operations are complete, the modified step response
matrix IS your final model. It is ready for export (Chapter 11).

If you have not yet built a master model (Chapter 7), the curve
operations apply directly to the single-trial identification result.

> **Tip: Less Is More**
>
> Resist the temptation to heavily modify every curve. The best models
> are the ones closest to what the data actually shows. Apply curve
> operations only when you have a clear engineering reason -- not just
> because a curve "looks a little noisy."

> **Common Mistake: Shifting the Wrong Direction**
>
> A positive SHIFT value adds dead time (shifts right). If the
> identified dead time is already too long, you need a negative shift.
> Double-check the direction before applying. The visual preview in
> the step response grid helps -- watch the curve move in real time
> as you change the parameter.

---

## Chapter 9: Analysis Tools

The Analysis step provides three complementary tools for assessing
model quality beyond basic fit metrics. Navigate to the **Analysis**
step in the sidebar to access them via sub-tabs.

### Cross-Correlation: Checking Step Test Quality

The Cross-Correlation sub-tab evaluates whether your step test was
well-designed by analyzing the MV signals.

**What it checks:**

1. **Auto-correlation** of each MV: How quickly the MV signal
   decorrelates with itself. Slow decay means the MV drifted or
   had periodic content -- both are problematic for identification.

2. **Cross-correlation** between MV pairs: How similar the MV
   movements were at various time lags. High cross-correlation means
   the MVs were moved together, making it impossible to separate
   their individual effects on the CVs.

**Running the analysis:**

1. Click **Run Cross-Correlation**.
2. The plot area shows auto-correlation and cross-correlation functions.
3. The results text panel shows a graded summary.

**Quality grades:**

| Peak Cross-Correlation | Grade         | Action                           |
|------------------------|---------------|----------------------------------|
| < 30%                  | IDEAL         | Excellent test design            |
| 30-50%                 | ACCEPTABLE    | Usable, minor correlation        |
| 50-80%                 | POOR          | Consider using Ridge or COR method |
| > 80%                  | UNACCEPTABLE  | Re-test or use closed-loop ID    |

For the cumene heater, the step test was designed with staggered MV
moves, so you should see IDEAL or ACCEPTABLE grades for all MV pairs.
A typical result:

```
Cross-Correlation Analysis
==========================
MV Pairs:
  FCV-410.SP vs SC-400.SP:   peak |r| = 0.12  IDEAL
  FCV-410.SP vs FCV-411.SP:  peak |r| = 0.18  IDEAL
  SC-400.SP  vs FCV-411.SP:  peak |r| = 0.09  IDEAL

Auto-Correlation (lag-1):
  FCV-410.SP:  0.95  (step inputs hold value -- expected)
  SC-400.SP:   0.94  (step inputs hold value -- expected)
  FCV-411.SP:  0.93  (step inputs hold value -- expected)
```

Note that high auto-correlation (0.90+) is normal and expected for step
test inputs, because the MVs are held constant between steps. What
matters is that the cross-correlation between MV pairs is low.

**What to do with poor grades:**

If two MVs are highly correlated (e.g., fuel gas and air were always
moved together):

- Switch to the COR or Ridge identification method
- Re-run the step test with better staggering
- Consider treating one of the correlated MVs as a DV
- Use constrained identification to enforce known gain signs

> **Tip: Run Cross-Correlation Before Identification**
>
> Cross-correlation analysis does not require a model -- it analyzes
> the raw data. You can run it as soon as tags are assigned, before
> even running identification. This gives you early warning about
> data quality issues.

### Model Uncertainty: A/B/C/D Grades

The Model Uncertainty sub-tab quantifies how confident you should be
in the identified model parameters.

**What it computes:**

For each MV-CV pair, uncertainty analysis produces:

- **Steady-state gain uncertainty:** How much the gain estimate could
  vary given the noise in the data. Expressed as a percentage of the
  gain value.
- **Dynamic uncertainty:** How much the transient (time-varying)
  response could vary. Includes confidence bands around the step
  response curve.

**Grading:**

| Grade | SS Gain Uncertainty | Dynamic Uncertainty | Interpretation          |
|-------|---------------------|---------------------|-------------------------|
| A     | < 10% of gain       | < 20% of gain       | High confidence         |
| B     | 10-25%              | 20-50%              | Adequate confidence     |
| C     | 25-50%              | 50-100%             | Low confidence, verify  |
| D     | > 50%               | > 100%              | Unreliable, re-test     |

**Running the analysis:**

1. Click **Run Uncertainty Analysis**.
2. The results text shows a per-cell grade table.
3. The plot area shows step response curves with confidence envelopes.

**What to do with poor grades:**

- Grade C or D on a specific cell: check if the MV was adequately
  excited for that CV.
- Grade C or D across many cells: the dataset may be too short, too
  noisy, or the process may have been disturbed during the test.
- If a gain is uncertain but the sign is known, consider constrained
  identification (Chapter 12).

### Gain Matrix Analysis: Condition Number, RGA, Colinearity

The Gain Matrix sub-tab evaluates whether the identified model is
well-conditioned for control. This is about controllability, not
model accuracy.

**What it computes:**

1. **Condition Number:** The ratio of the largest to smallest singular
   value of the gain matrix. Indicates how sensitive the control
   solution is to model errors.

   | Condition Number | Interpretation                              |
   |------------------|---------------------------------------------|
   | < 10             | Well-conditioned, easy to control            |
   | 10-50            | Moderate, standard MPC tuning works          |
   | 50-200           | Ill-conditioned, may need careful tuning     |
   | > 200            | Severely ill-conditioned, consider reformulation |

2. **Relative Gain Array (RGA):** For square systems, the RGA shows
   the degree of MV-CV interaction. Diagonal elements near 1.0 mean
   low interaction; elements far from 1.0 mean strong coupling.

3. **Colinearity Detection:** Identifies pairs of MVs that have nearly
   parallel gain vectors. Collinear MVs provide redundant control
   authority -- the controller may struggle to decide which MV to
   move.

4. **Sub-Matrix Scanning:** Examines all 2x2, 3x3, and 4x4 sub-
   matrices of the gain matrix to find problematic sub-systems.

**Running the analysis:**

1. Select a **Scaling Method** if desired:
   - None: raw gain matrix
   - Typical Moves: scale by expected MV move sizes
   - Range: scale by engineering range
2. Click **Run Gain Matrix Analysis**.
3. Review the condition number, RGA, and colinearity results.

> **Tip: Condition Number Depends on Scaling**
>
> The condition number changes dramatically with scaling. A system
> that looks ill-conditioned with raw gains may be perfectly fine when
> scaled by typical move sizes (because one MV might have a range of
> 0-100% while another is 0-1.0). Always check with Typical Moves
> scaling.

> **Common Mistake: Panicking Over High Condition Number**
>
> A high condition number does not mean the model is wrong. It means
> the MPC controller needs to be careful about which MVs it moves.
> Modern MPC controllers handle condition numbers up to ~100 well
> through move suppression tuning. Only condition numbers above
> 500 are truly problematic.

### Interpreting Results and What to Do When They Are Bad

| Analysis           | Problem Found                     | Action                                   |
|--------------------|-----------------------------------|------------------------------------------|
| Cross-Correlation  | Two MVs highly correlated         | Use Ridge method; re-stagger next test   |
| Cross-Correlation  | MV auto-correlation decays slowly | Check for drift; detrend; increase n_coeff |
| Uncertainty        | Grade D on several cells          | Longer test; bigger steps; more data     |
| Uncertainty        | Grade D on one cell               | May be a weak relationship; consider ZERO |
| Gain Matrix        | Condition number > 200            | Check scaling; consider removing an MV   |
| Gain Matrix        | Collinear MV pair                 | One MV may be redundant; investigate     |

---

## Chapter 10: Validation

Validation answers the fundamental question: **does the model predict
well on data it was not trained on?**

### Holdout Validation vs Full Training Set

During identification, the **holdout fraction** parameter (default 0.2)
reserves the last 20% of the data for validation. The model is trained
on the first 80% and tested on the last 20%.

Navigate to the **Validate** step in the sidebar. The top bar has a
**Test data** dropdown with three options:

| Source             | What It Uses                                     |
|--------------------|--------------------------------------------------|
| Hold-out tail      | The 20% of data reserved during identification   |
| Full training set  | The same data used for training (overfit check)   |
| Load CSV...        | An external CSV file (independent validation)     |

### Loading External Test Data

If you have a separate step test (run on a different day or under
different conditions), loading it as external validation data provides
the strongest evidence of model quality:

1. Select **Load CSV...** from the Test data dropdown.
2. A file dialog opens. Select the external CSV.
3. The data is loaded, conditioned with the current conditioning
   settings, and used as the validation set.

### Understanding Actual vs Predicted Plots

Click **Run Validation** to generate the validation plots. The workspace
shows one stacked panel per CV:

- **Orange line:** Measured (actual) CV values from the test data
- **Blue line:** Open-loop prediction (model predicts forward from
  initial conditions using only MV moves)
- **Green dashed line:** One-step-ahead prediction (model updates its
  state at each time step using the measured CV value before predicting
  the next step)

### Open-Loop vs One-Step-Ahead Prediction

**Open-loop prediction** is the harder test. The model starts from
initial conditions and predicts the entire future trajectory using only
the MV moves -- no CV measurements are fed back. Errors accumulate over
time, so the prediction may drift from the actual values. This tests
whether the model captures the true dynamics.

**One-step-ahead prediction** is easier. At each time step, the model
uses the actual measured CV value to correct its prediction before
predicting one step forward. This is how the model will be used inside
the MPC controller (with the disturbance observer providing corrections),
so it tests operational performance.

**Per-CV Metrics Table:**

| CV         | Open R-sq | 1-Step R-sq | Open RMSE | NRMSE  | Bias    |
|------------|-----------|-------------|-----------|--------|---------|
| XI-490.PV  | 0.82      | 0.96        | 0.31      | 0.042  | -0.05   |
| TIT-400.PV | 0.89      | 0.98        | 1.85      | 0.026  | 0.12    |
| ...        | ...       | ...         | ...       | ...    | ...     |

Key columns:

- **Open R-sq:** R-squared for open-loop prediction. Target > 0.75.
- **1-Step R-sq:** R-squared for one-step-ahead. Target > 0.90.
- **NRMSE:** Normalized RMSE (RMSE divided by CV range). Target < 0.10.
- **Bias:** Systematic offset. Should be close to zero.

**Interpreting the plots for the cumene heater:**

For TIT-400.PV (outlet temperature), a good validation looks like:

- The blue open-loop prediction follows the overall trend of the
  orange measured line, capturing the direction and magnitude of
  temperature swings in response to MV changes.
- Some drift is normal -- the open-loop prediction may slowly
  diverge from the measurement over long horizons because it
  does not get corrective feedback.
- The green one-step-ahead prediction should closely track the
  measurement with only small deviations.

For XI-490.PV (excess O2), validation may be harder because O2
measurements are typically noisier. Lower R-squared values are
expected and acceptable.

**Warning banner:** If the MV variance in the test data is very low
(the MVs barely moved), a yellow warning banner appears at the top
of the validation tab:

```
Warning: MV variance in test data is low. Validation may not be
meaningful because the model is not being challenged.
```

This means the test data does not adequately exercise the model.
Good validation requires that the MVs in the test data move
significantly -- ideally with different step sizes and timing
from the training data.

### When to Re-Identify

Consider re-running identification if:

- Open-loop R-squared is below 0.6 for any important CV
- The actual vs predicted plots show systematic divergence (the model
  consistently over- or under-predicts)
- One-step-ahead R-squared is below 0.85 (indicates the model is
  missing fast dynamics)
- The bias is large relative to the CV's operating range

Before re-identifying, first check:

1. **Data quality:** Are there unconditioned spikes or upsets in the
   training data?
2. **Tag assignments:** Are all relevant MVs and DVs included?
3. **Model length:** Is n_coeff long enough to capture the settling
   time?
4. **Method:** Would COR or Ridge work better than DLS?

> **Tip: Validate on Holdout First, Then External**
>
> Holdout validation is faster (no extra file needed) and gives you a
> quick sanity check. If holdout validation passes, try external
> validation for final confirmation. If holdout validation fails,
> fix the model before spending time on external validation.

> **Common Mistake: Validating on Training Data Only**
>
> If you select "Full training set" as the test data source and get
> great R-squared values, that only proves the model fits the training
> data well -- it does not prove the model generalizes. This is
> especially dangerous with large model lengths (high n_coeff) that
> can overfit. Always validate on holdout or external data.

---

## Chapter 11: Exporting and Reporting

### Exporting the Model Bundle (.apcmodel)

The model bundle is an HDF5 file that packages everything APC Architect
needs to build a controller:

- **Tag lists:** MV, CV, and DV names linking the model to process tags
- **FIR coefficients:** The full impulse response matrix [ny, n_coeff, nu]
- **Step response:** Cumulative step response [ny, n_coeff, nu]
- **Gain matrix:** Steady-state gains [ny, nu]
- **State-space realization:** (A, B, C, D) matrices derived from the
  FIR coefficients via ERA (Eigensystem Realization Algorithm)
- **Confidence bands:** Upper and lower confidence envelopes for each
  step response curve
- **Metadata:** Sample time, identification method, fit metrics,
  source file references

**To export:**

1. In the Results step, click the **Export Model Bundle...** button
   (green button at the bottom of the side panel).
2. Choose a save location and filename. The default extension is
   `.apcmodel`.
3. Click Save.

The bundle label updates to show the export path and timestamp.

For the cumene heater:
```
examples/cumene_hotoil_heater.apcmodel
```

You can also export via the sidebar: right-click the Results step and
select **Export Model Bundle...**.

### Generating HTML Reports

An HTML report summarizes the entire identification project in a
printable format. It includes:

- Project metadata (name, date, data source)
- Data conditioning summary
- Tag assignments table
- Identification configuration
- Gain matrix (formatted table with color coding)
- Per-channel fit metrics
- Quality Scorecard results
- Smart Config recommendations (if used)

**To generate a report:**

1. Right-click the **Validate** step in the sidebar.
2. Select **Generate Report (HTML)...**.
3. Choose a save location and filename (e.g.,
   `cumene_heater_ident_report.html`).
4. The report opens in your default web browser.

The report is self-contained HTML (no external dependencies) and can
be emailed, printed, or archived as a project record.

**Report sections include:**

- Project header (name, date, engineer, data source)
- Data conditioning summary (number of corrections per tag)
- Tag assignment table (role, controller tag, statistics)
- Identification configuration (method, n_coeff, dt, smoothing)
- Gain matrix (color-coded: green for expected signs, red for
  unexpected)
- Per-channel fit metrics table (R-squared, RMSE, Ljung-Box)
- Quality Scorecard with traffic-light grades
- Smart Config recommendations and rationale (if used)

> **Tip: Include the Report in Your Management of Change (MOC)**
>
> Many sites require documentation for APC controller commissioning
> as part of their Management of Change process. The HTML report
> provides a professional, auditable record of the model
> identification that can be printed and signed off by the process
> engineer and control engineer.

### What the Architect App Needs from the Bundle

When you open the `.apcmodel` file in APC Architect, it reads:

1. **Tag lists** to set up the controller variable configuration
   (CV/MV definitions, engineering ranges, initial limits)
2. **Step response coefficients** for the dynamic matrix used in
   Layer 1 (QP controller)
3. **Gain matrix** for Layer 2 (steady-state target optimizer)
4. **State-space model** for simulation and Layer 3 (nonlinear
   optimizer)
5. **Sample time** to set the controller execution period

The model bundle is the bridge between identification and control
design. A well-identified, validated, properly exported bundle makes
the architect's job straightforward.

> **Tip: Version Your Bundles**
>
> Include a date or version number in the bundle filename:
> `cumene_hotoil_heater_v2_2025-01-15.apcmodel`. When you re-identify
> after a process change, you can compare old and new bundles in the
> Architect app.

> **Common Mistake: Exporting Before Validation**
>
> Always run validation (Chapter 10) before exporting. An exported
> bundle with a poor model will propagate errors into the controller
> design. The Architect app trusts the model it receives -- it has
> no way to know if the model was properly validated.

---

## Chapter 12: Advanced Topics

### Constrained Identification (Enforcing Gain Signs, Dead Times)

Standard FIR identification is unconstrained -- it finds whatever
coefficients minimize the prediction error, even if the results
violate known physics. Constrained identification lets you enforce
engineering knowledge during the solve.

**Available constraints:**

| Constraint Type  | Example                                    |
|------------------|--------------------------------------------|
| Gain sign        | gain(TIT-400/FCV-410) must be positive     |
| Gain bound       | 0.5 <= gain(TIT-400/FCV-410) <= 5.0        |
| Dead time min    | dead_time(TIT-400/FCV-410) >= 3 samples    |
| Dead time max    | dead_time(TIT-400/FCV-410) <= 10 samples   |
| Gain ratio       | gain(CV1/MV1) / gain(CV1/MV2) = 2.5 +/- 0.2 |

**When to use:**

- The unconstrained identification gives a gain with the wrong sign
  (you know from first principles that increasing fuel should increase
  temperature, but the model shows a negative gain due to noise)
- You have prior knowledge of dead times from process design or
  previous studies
- Two gains must maintain a known ratio (e.g., from mass balance)

**How to use:**

Constrained identification is configured in the Identify tab's
preprocessing section. Define constraints as a list, then run
identification as usual. The solver uses scipy's constrained
minimization to find FIR coefficients that satisfy all constraints
while minimizing prediction error.

> **Tip: Start Unconstrained, Then Add Constraints**
>
> Run unconstrained identification first to see what the data says.
> Then add constraints only where the unconstrained result contradicts
> known physics. Do not over-constrain -- you might force the model
> to fit your expectations rather than the data.

### Closed-Loop Identification

Sometimes you cannot perform an open-loop step test because:

- Turning off the controller would violate safety constraints
- The process is unstable without feedback
- Production cannot tolerate the large deviations of open-loop tests

Closed-loop identification extracts the plant model from data collected
while the controller is running. This is harder than open-loop
identification because the input (MV) is correlated with the output
noise through the feedback loop.

APC Ident supports three closed-loop methods:

| Method           | Requires Setpoints? | Best For                          |
|------------------|---------------------|-----------------------------------|
| Instrumental Variable (IV) | Yes        | Setpoint step tests (most reliable) |
| Two-Stage        | No                  | When controller parameters are known |
| Regularized Direct | No               | Quick-and-dirty, no extra info needed |

**Best practice:** If possible, run setpoint step tests (change the
setpoints of the existing controller in a staggered pattern). This
gives the IV method the instrument it needs to break the feedback
correlation.

**Usage:**

In the Identify tab, select "Closed-Loop" as the identification mode.
Choose the method, provide setpoint columns if using IV, and run.

### Calculated Vectors (Derived Variables)

Sometimes you need to identify a model for a variable that is not
directly measured but is calculated from other measurements. Examples:

- Heat duty = flow * delta-T * Cp
- Efficiency = output / input * 100
- Ratio = flow_A / flow_B

The Calculated Vectors feature lets you define formula-based columns
that are computed from existing CSV columns:

1. In the Identify step, expand the Calculated Vectors section.
2. Define a new tag with a name and formula.
3. The calculated column is added to the dataframe and appears in the
   tag browser.
4. Assign it a role (CV or DV) and include it in identification.

### Process Templates

Process templates provide starting-point configurations for common
industrial process types, saving you from building identification
projects from scratch. They encode decades of APC engineering
experience about typical dynamics, time constants, and recommended
identification settings for each process type.

Available templates:

| Template   | Description                                          |
|------------|------------------------------------------------------|
| HEATER     | Fired heater (fuel, air, draft -- temperatures, O2)  |
| COLUMN     | Distillation column (reflux, reboil -- compositions) |
| REACTOR    | Chemical reactor (feed, coolant -- temperature, conversion) |
| BOILER     | Steam boiler (fuel, feedwater -- steam pressure, level) |
| COMPRESSOR | Compressor (speed, guide vanes -- flow, pressure)    |

Each template provides:

- Suggested MV and CV names with units
- Recommended n_coeff and dt based on typical dynamics
- Expected time constant and dead time ranges
- Known CV types (ramp/pseudoramp for integrating outputs)
- Suggested identification method

**Usage:**

When creating a new project, select a template to pre-populate the
configuration. Then adjust to match your specific process.

### OPC UA Data Acquisition

> **Common Mistake: Exporting Data at the Wrong Sample Rate**
>
> When exporting step test data from a historian (PI, IP.21, PHD,
> etc.), make sure you export at a fixed sample rate, not "exception
> based" or "on change." Exception-based exports produce irregular
> time spacing that requires resampling and may lose information.
> Export at 1x or 2x the controller sample rate (e.g., every 30-60
> seconds for a controller running at 1-minute intervals).

Instead of loading data from a CSV file, you can acquire step-test data
directly from an OPC UA server:

1. In the Data step, right-click the Data step in the sidebar and
   select **OPC UA Data Acquisition...**.
2. Enter the OPC UA server URL and browse the address space.
3. Select the tags to record.
4. Configure the sample rate and duration.
5. Click Start to begin recording.

The recorded data appears in the trend workspace just like CSV data.
You can then proceed with conditioning, tag assignment, and
identification as usual.

This feature is useful when you want to run the step test and identify
the model in real time, without the intermediate step of exporting
data from the historian and loading it into a CSV.

> **Tip: OPC UA Security**
>
> Most production OPC UA servers require authentication (username/
> password or certificates). Check with your site IT team for the
> correct endpoint URL and credentials. APC Ident supports both
> anonymous and authenticated connections.

### Ramp/Pseudoramp CVs (Integrating Processes)

Many industrial variables are integrators -- their step response does
not settle to a constant value but ramps indefinitely. Examples:

- Tank levels (flow in minus flow out integrates to level change)
- Inventories
- Slow temperature drifts in large thermal masses

Standard FIR identification assumes a settling process (the step
response reaches a constant steady-state gain). For integrating CVs,
special preprocessing is needed.

**CV Types:**

| Type        | Description                                           |
|-------------|-------------------------------------------------------|
| Normal      | Standard settling process. No special treatment.      |
| Ramp        | Pure integrator. Response ramps linearly forever.     |
| Pseudoramp  | Very slow time constant that looks like a ramp over the test duration. |

**Configuration:**

In the Identify step, the CV Types section shows a dropdown for each CV:

```
XI-490.PV:  [Normal]
TIT-400.PV: [Normal]
TIT-402.PV: [Normal]
TIT-412.PV: [Normal]
XI-410.PV:  [Normal]
AIT-410.PV: [Normal]
```

For the cumene heater, all CVs are normal (settling). If you were
identifying a column with a level CV, you would set that CV to Ramp.

**What happens internally:**

- **Ramp CV:** The algorithm first-differences the CV data
  (delta_y[k] = y[k] - y[k-1]) to convert the ramp into a
  step-like response, identifies the FIR coefficients on the
  differenced data, then converts back to represent the
  integrating behavior.
- **Pseudoramp CV:** The algorithm removes a linear trend from the CV
  data, identifies normally, then adjusts the coefficients to account
  for the removed trend.

Smart Config can auto-detect ramp and pseudoramp CVs based on their
statistical properties (large drift relative to variance).

> **Tip: If In Doubt, Try Normal First**
>
> If you are not sure whether a CV is a ramp or just slow, try Normal
> first. If the step response curve shows a clear upward ramp that does
> not settle within the model horizon, switch to Ramp and re-identify.

### Batch Execution for Large Controllers

Large controllers (20+ CVs, 10+ MVs) produce hundreds of MV-CV pairs.
Identifying all of them in one MIMO regression can be slow and
numerically challenging.

Batch execution decomposes the problem into MISO (Multiple Input,
Single Output) sub-problems -- one per CV. Each sub-problem identifies
the response of one CV to all MVs:

1. CV1 = f(MV1, MV2, ..., MVn) -- one regression
2. CV2 = f(MV1, MV2, ..., MVn) -- another regression
3. ...

This is faster (each sub-problem is smaller) and more robust (one
poorly-conditioned CV does not contaminate the others).

**When to use:**

- More than 15-20 CVs
- When the full MIMO identification is slow or produces poor results
- When individual CVs have very different dynamics (different n_coeff
  would be optimal for each)

**Usage:**

Batch execution runs automatically in the background when the Identify
button is clicked and the system detects a large number of CVs. You can
also trigger it explicitly through the Identify step's context menu.

The batch report shows per-case timing and success/failure status:

```
Batch Execution Report:
  Case 1 (XI-490.PV):  OK   0.3s   R^2=0.87
  Case 2 (TIT-400.PV): OK   0.4s   R^2=0.94
  Case 3 (TIT-402.PV): OK   0.3s   R^2=0.91
  ...
  6/6 cases succeeded, total time: 2.1s
```

> **Common Mistake: Different n_coeff Per CV in Batch Mode**
>
> In batch mode, each MISO case uses the same n_coeff. If one CV
> settles in 20 minutes but another takes 120 minutes, the shared
> n_coeff is a compromise. For such cases, use multi-trial with
> different n_coeff values and assemble the best per-CV result
> (Chapter 7).

---

## Putting It All Together: End-to-End Walkthrough

Here is the complete sequence for the cumene heater, from start to
finish, as a quick-reference recipe:

```
1.  Launch APC Ident
2.  File > New Project
3.  [Data] Click Load > select cumene_step_test.csv
4.  [Data] Click Auto Condition (lightning bolt)
5.  [Data] Click Before/After to verify conditioning
6.  [Data] Click SSD to check steady-state regions
7.  [Tags] Set FCV-410.SP, SC-400.SP, FCV-411.SP as MV
8.  [Tags] Set XI-490.PV, TIT-400.PV, TIT-402.PV,
           TIT-412.PV, XI-410.PV, AIT-410.PV as CV
9.  [Identify] Click Smart Config, review recommendations
10. [Identify] Accept defaults (n_coeff=60, DLS, Pipeline)
11. [Identify] Click IDENTIFY (or press F5)
12. [Results] Inspect step response matrix:
    - Check gain signs against process knowledge
    - Check dead times are physically reasonable
    - Look for noisy or oscillatory curves
13. [Results] Apply curve operations if needed:
    - SHIFT to correct dead times
    - GSCALE to correct gains
    - ZERO for spurious relationships
14. [Results] Click Build Master Model
15. [Analysis] Run Cross-Correlation -- check MV independence
16. [Analysis] Run Uncertainty Analysis -- target all A/B grades
17. [Analysis] Run Gain Matrix Analysis -- check condition number
18. [Validate] Select "Hold-out tail", click Run Validation
19. [Validate] Verify open-loop R^2 > 0.75 for all CVs
20. [Results] Click Export Model Bundle
21. [Validate] Right-click > Generate Report (HTML)
22. File > Save Project
```

Total time for the cumene heater: approximately 15-30 minutes for a
first-time user, 5-10 minutes for an experienced user.

## Troubleshooting Common Problems

### "All step responses are flat (zero)"

**Cause:** The MV and CV tag assignments are swapped, or all tags are
set to the same role.

**Fix:** Check the Tags tab. MVs should be the variables you moved
during the step test. CVs should be the variables that responded.

### "Step responses are very noisy / oscillatory"

**Cause:** Insufficient data, model length too long, or the data
contains unremoved disturbances.

**Fix:** Try reducing n_coeff, switching to Ridge method, or
applying more aggressive conditioning. Check that smoothing is set
to Pipeline.

### "R-squared is very low for all CVs"

**Cause:** The MVs were not moved enough during the test, the data
has too much unmeasured disturbance, or the sample period is wrong.

**Fix:** Verify the sample period matches the data. Check that each
MV has at least 2-3 clear step changes. Run cross-correlation to
check excitation adequacy.

### "Identification takes a very long time"

**Cause:** The dataset is very large (thousands of samples) combined
with a large model length (n_coeff > 100) and many MV-CV pairs.

**Fix:** Reduce n_coeff if possible. Resample to a coarser sample
period if the dynamics are slow enough. Use batch execution for
large MIMO systems.

### "Gain signs are wrong"

**Cause:** MV cross-correlation is high (MVs were moved together,
confounding their effects), or the test duration was too short for
the model to disambiguate individual effects.

**Fix:** Use Ridge method to regularize the solution. Apply
constrained identification to enforce known gain signs. Run
cross-correlation analysis to quantify the problem.

### "Dead time is zero when it should not be"

**Cause:** The conditioning or detrending removed the initial
transient, or the model length is too short relative to the
dead time.

**Fix:** Check the Before/After toggle to see if conditioning
altered the beginning of the response. Use the SHIFT curve
operation to manually add the correct dead time.

### "Cannot export -- Export button is grayed out"

**Cause:** No identification has been run yet, or the identification
failed.

**Fix:** Go to the Identify step and run identification. Check the
status panel for error messages.

## Quick Reference: Keyboard Shortcuts

| Shortcut      | Action                          |
|---------------|---------------------------------|
| Ctrl+N        | New Project                     |
| Ctrl+O        | Open Project                    |
| Ctrl+S        | Save Project                    |
| Ctrl+Shift+S  | Save Project As                 |
| F5            | Run Identification              |
| Ctrl+Z        | Undo (in curve operations)      |

## Quick Reference: Workflow Checklist

Use this checklist for every identification project:

- [ ] **Data:** Load CSV, check for NaN/spikes/flatline, run Auto Condition
- [ ] **Tags:** Assign MV/CV/DV roles, set controller tag names
- [ ] **Identify:** Run Smart Config, review recommendations, click Identify
- [ ] **Results:** Inspect step response curves, check gain signs and dead times
- [ ] **Analysis:** Run cross-correlation, uncertainty, gain matrix analysis
- [ ] **Validate:** Run holdout validation, check open-loop R-squared > 0.75
- [ ] **Export:** Export model bundle, generate HTML report
- [ ] **Review:** Compare gain matrix against process knowledge

## Further Reading

For deeper understanding of the algorithms and theory behind model
identification, these references are recommended:

- **Qin, S.J. (2006)** "An overview of subspace identification" --
  Comprehensive survey of subspace identification methods (N4SID,
  MOESP, CVA).
- **Ljung, L. (1999)** "System Identification: Theory for the User"
  -- The classic textbook on system identification.
- **Rawlings, J.B. et al. (2017)** "Model Predictive Control: Theory,
  Computation, and Design" -- Covers MPC theory including the model
  identification requirements.
- **Cutler, C.R. and Ramaker, B.L. (1980)** "Dynamic Matrix Control
  -- A Computer Control Algorithm" -- The original DMC paper that
  introduced step response models for MPC.
- **AspenTech DMC3 Builder Help** -- Reference for the industry-
  standard workflow that APC Ident follows.

## Glossary

| Term              | Definition                                                    |
|-------------------|---------------------------------------------------------------|
| APC               | Advanced Process Control                                      |
| CV                | Controlled Variable -- a measurement you want to regulate     |
| DLS               | Direct Least Squares -- standard FIR identification method    |
| DV                | Disturbance Variable -- a measured but uncontrollable input   |
| FIR               | Finite Impulse Response -- discrete-time model representation |
| MPC               | Model Predictive Control                                      |
| MV                | Manipulated Variable -- an input you can adjust               |
| N4SID             | Numerical Subspace State Space System ID algorithm            |
| NRMSE             | Normalized Root Mean Square Error                             |
| R-squared         | Coefficient of determination (fraction of variance explained) |
| RGA               | Relative Gain Array -- interaction measure for MIMO systems   |
| RMSE              | Root Mean Square Error                                        |
| SSD               | Steady-State Detection                                        |
| Step Response     | How a CV changes over time in response to a unit step in an MV |

---

*APC Ident v0.2.0 -- Azeotrope Process Control*
