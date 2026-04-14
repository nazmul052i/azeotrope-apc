# MPC Controller Configuration, Tuning, and Deployment Theory

**A Mathematical and Practical Reference for the Azeotrope APC Architect**

---

This document is the companion to the
[Identification Theory](identification_theory.md) reference. Where that
document covers extracting a plant model from data, this document covers
everything that happens *after* you have a model: building the prediction
engine, formulating the optimization layers, tuning the controller, and
deploying it to a live process.

The audience is a process engineer who has just completed model
identification in APC Ident and is now configuring a controller in APC
Architect. Mathematical rigor is maintained where it clarifies the
algorithms; practical rules of thumb are given where they accelerate
tuning.

---

## Table of Contents

1. [From Model to Controller](#1-from-model-to-controller)
2. [Layer 1: Dynamic QP](#2-layer-1-dynamic-qp)
3. [Layer 2: Steady-State Target](#3-layer-2-steady-state-target)
4. [Layer 3: Nonlinear Optimizer](#4-layer-3-nonlinear-optimizer)
5. [Tuning Guide](#5-tuning-guide)
6. [Constraint Priority System](#6-constraint-priority-system)
7. [Feedback Filters](#7-feedback-filters)
8. [Subcontrollers](#8-subcontrollers)
9. [Disturbance Observer](#9-disturbance-observer)
10. [Simulation and What-If Testing](#10-simulation-and-what-if-testing)
11. [Deployment via OPC UA](#11-deployment-via-opc-ua)
12. [Calculations (Python Scripting)](#12-calculations-python-scripting)
13. [Performance Monitoring](#13-performance-monitoring)
14. [Recipes](#14-recipes)

---

## Notation and Conventions

| Symbol | Meaning |
|--------|---------|
| $$n_y$$ | Number of controlled variables (CVs / outputs) |
| $$n_u$$ | Number of manipulated variables (MVs / inputs) |
| $$n_d$$ | Number of disturbance variables (DVs) |
| $$n_x$$ | State-space model order |
| $$N$$ | Model horizon (number of FIR / step-response coefficients) |
| $$P$$ | Prediction horizon (how far ahead the controller looks) |
| $$M$$ | Control horizon (number of future moves optimized) |
| $$T_s$$ | Sample period (minutes) |
| $$u(k) \in \mathbb{R}^{n_u}$$ | Input (MV) vector at sample $$k$$ |
| $$y(k) \in \mathbb{R}^{n_y}$$ | Output (CV) vector at sample $$k$$ |
| $$\Delta u(k)$$ | MV move: $$u(k) - u(k-1)$$ |
| $$S_j \in \mathbb{R}^{n_y \times n_u}$$ | Step response coefficient at step $$j$$ |
| $$K = S_N$$ | Steady-state gain matrix |
| $$Q$$ | CV error weight matrix (diagonal) |
| $$R$$ | MV move suppression weight matrix (diagonal) |
| $$d(k) \in \mathbb{R}^{n_y}$$ | Estimated disturbance (output bias) |

All variables in the QP formulation are expressed in **deviation form**
relative to the current steady-state operating point:

$$
\tilde{y}(k) = y(k) - y_{ss}, \quad \tilde{u}(k) = u(k) - u_{ss}
$$

The controller internally works in deviations. Engineering-unit values
are reconstructed at the interface boundary.

---

## 1. From Model to Controller

### 1.1 The Identification Output

APC Ident exports a **model bundle** (`.apcmodel` file) containing:

- **State-space realization** $$(A, B, C, D)$$ from ERA (Eigensystem
  Realization Algorithm), where $$A \in \mathbb{R}^{n_x \times n_x}$$,
  $$B \in \mathbb{R}^{n_x \times n_u}$$, $$C \in \mathbb{R}^{n_y \times n_x}$$,
  $$D \in \mathbb{R}^{n_y \times n_u}$$.
- **FIR coefficients** $$\{g_0, g_1, \ldots, g_{n-1}\}$$ from
  least-squares identification.
- **Operating point** $$(u_0, y_0)$$ -- the steady-state values during
  the step test.
- **Tag lists** mapping each MV and CV index to a DCS tag name.
- **Sample time** $$T_s$$ used during identification.

When you import this bundle into APC Architect, the system performs
three key transformations to build the prediction engine.

### 1.2 State-Space to Step Response Conversion

The MPC controller's Layer 1 QP uses a **step response model** (also
called FIR coefficients in step-response form). Given discrete
state-space matrices $$(A, B, C, D)$$, the step response coefficients
are computed by simulating a unit step on each input:

$$
x(0) = 0
$$

$$
x(j+1) = A \, x(j) + B \, e_q
$$

$$
S_j^{(\cdot, q)} = C \, x(j) + D \, e_q
$$

where $$e_q$$ is the $$q$$-th unit vector (step applied to input $$q$$
only). The resulting matrix $$S_j \in \mathbb{R}^{n_y \times n_u}$$
gives, at time step $$j$$, the response of all $$n_y$$ outputs to a
unit step on each of the $$n_u$$ inputs.

The model horizon $$N$$ is chosen so that all channels have settled:
$$S_j \approx S_N = K$$ for $$j \geq N$$. Typical values:

| Process type | Settling time | Suggested $$N$$ |
|---|---|---|
| Fast liquid flow | 5--15 min | 30--60 steps at $$T_s = 1$$ min |
| Temperature loop | 30--120 min | 60--200 steps |
| Distillation column | 2--8 hours | 200--500 steps |
| Reactor composition | 4--24 hours | 400--1000+ steps |

**Rule of thumb:** set $$N$$ to 1.5 to 2 times the longest 95% settling
time divided by the sample period.

### 1.3 The Step Response Model Object

Internally, the step response model is stored as a 3D array:

$$
\mathbf{S} \in \mathbb{R}^{n_y \times N \times n_u}
$$

where $$\mathbf{S}[i, j, q] = S_j^{(i,q)}$$ is the response of CV $$i$$
at step $$j$$ to a unit step on MV $$q$$.

The C++ core provides `StepResponseModel` with two factory methods:

- `fromStateSpace(A, B, C, D, N, dt)` -- converts state-space to step
  response by simulation.
- `fromFOPTD(K, tau, L, dt, N)` -- generates step response from
  first-order-plus-dead-time parameters (gain $$K$$, time constant
  $$\tau$$, dead time $$L$$).

### 1.4 The Steady-State Gain Matrix

The steady-state gain matrix $$K \in \mathbb{R}^{n_y \times n_u}$$
relates the final change in outputs to a sustained change in inputs:

$$
K = \lim_{j \to \infty} S_j = S_N
$$

For a discrete state-space system (assuming $$A$$ is stable, i.e., all
eigenvalues inside the unit circle):

$$
K = -C (A - I)^{-1} B + D
$$

This gain matrix is used by:

- **Layer 2** to compute steady-state targets.
- **Step 4 (Evaluate Strategy)** in the optimizer wizard to visualize
  input-output interactions.
- **Economic optimization** to determine which MV movements achieve the
  desired CV directions.

### 1.5 Building the Dynamic Matrix

The **dynamic matrix** $$\mathbf{A}_{dyn}$$ is a block lower-triangular
Toeplitz matrix constructed from the step response coefficients. It maps
future MV moves to predicted CV changes:

$$
\mathbf{A}_{dyn} = \begin{bmatrix}
S_1       & 0         & 0      & \cdots & 0 \\
S_2       & S_1       & 0      & \cdots & 0 \\
S_3       & S_2       & S_1    & \cdots & 0 \\
\vdots    & \vdots    & \vdots & \ddots & \vdots \\
S_P       & S_{P-1}   & S_{P-2}& \cdots & S_{P-M+1}
\end{bmatrix}
\in \mathbb{R}^{(P \cdot n_y) \times (M \cdot n_u)}
$$

Each block $$S_j \in \mathbb{R}^{n_y \times n_u}$$. The matrix has
$$P$$ block rows (one per prediction step) and $$M$$ block columns (one
per control move). For a 6-CV, 3-MV system with $$P = 60$$ and $$M = 5$$,
this matrix is $$360 \times 15$$.

The dynamic matrix is typically sparse (upper-right blocks are zero) and
is stored in compressed sparse column (CSC) format for efficient QP
construction.

### 1.6 Prediction and Control Horizons

Three horizons govern the controller's behavior:

**Model Horizon (N):** How many step response coefficients are stored.
Must be long enough for all channels to reach steady state.

**Prediction Horizon (P):** How many steps into the future the
controller predicts. Must be at least as long as the longest dead time
plus response time. Setting $$P$$ too short causes the controller to
ignore long-term consequences; setting it too long increases computation
without benefit once all channels have settled.

**Control Horizon (M):** How many independent future moves the
controller optimizes. Beyond step $$M$$, future moves are assumed zero
($$\Delta u(k+j) = 0$$ for $$j \geq M$$). Typical values are $$M = 3$$
to $$M = 10$$.

Relationships and constraints:

$$
M \leq P \leq N
$$

Practical guidelines:

| Parameter | Typical range | Effect of increasing |
|---|---|---|
| $$P$$ | 30--120 | More foresight, higher compute cost |
| $$M$$ | 3--10 | More aggressive control, risk of oscillation |
| $$N$$ | $$P$$ to $$2P$$ | Captures slower dynamics |

**Example: Cumene hot oil heater.** With $$T_s = 1$$ min, the slowest
channel (bridgewall temperature TIT-402) settles in about 90 minutes.
Setting $$N = 150$$, $$P = 60$$, $$M = 5$$ is a reasonable starting
point.

---

## 2. Layer 1: Dynamic QP

Layer 1 is the **dynamic controller**. It runs every sample period and
computes the optimal sequence of MV moves to drive the CVs toward their
targets while respecting constraints.

### 2.1 The Prediction Equation

At each sample $$k$$, the controller predicts the future output
trajectory over $$P$$ steps. The prediction has two components:

**Free response** $$\mathbf{y}_{free}$$: the predicted output trajectory
assuming no future moves are made ($$\Delta u(k+j) = 0$$ for all
$$j \geq 0$$). This accounts for:

- Past MV moves that have not yet fully affected the CVs.
- The current disturbance estimate $$d(k)$$.

**Forced response**: the additional output change caused by future MV
moves, captured by the dynamic matrix multiplication.

The complete prediction equation is:

$$
\mathbf{y}_{pred} = \mathbf{y}_{free} + \mathbf{A}_{dyn} \, \boldsymbol{\Delta u}
$$

where:

- $$\mathbf{y}_{pred} \in \mathbb{R}^{P \cdot n_y}$$ is the stacked
  predicted output vector:

$$
\mathbf{y}_{pred} = \begin{bmatrix}
\tilde{y}(k+1|k) \\ \tilde{y}(k+2|k) \\ \vdots \\ \tilde{y}(k+P|k)
\end{bmatrix}
$$

- $$\boldsymbol{\Delta u} \in \mathbb{R}^{M \cdot n_u}$$ is the stacked
  future move vector:

$$
\boldsymbol{\Delta u} = \begin{bmatrix}
\Delta u(k) \\ \Delta u(k+1) \\ \vdots \\ \Delta u(k+M-1)
\end{bmatrix}
$$

### 2.2 Free Response Calculation

The free response is computed from the step response model and the
history of past MV moves. Let $$\Delta u(k-j)$$ be the move made $$j$$
steps ago. The free response at prediction step $$p$$ is:

$$
y_{free}(k+p|k) = \sum_{j=1}^{N-1} \bigl(S_{p+j} - S_j\bigr) \, \Delta u(k-j) + d(k)
$$

where $$d(k)$$ is the disturbance estimate (output bias correction).
For $$p + j > N$$, we use $$S_{p+j} = S_N = K$$ (the steady-state gain).

The key insight is that past moves contribute to the free response
because their effects have not yet fully materialized. A move made 5
steps ago on a channel with a 100-step settling time still has 95 steps
of "pending" response.

### 2.3 QP Formulation

The Layer 1 controller solves the following quadratic program at every
sample period:

$$
\min_{\boldsymbol{\Delta u}} \quad
\|\mathbf{y}_{pred} - \mathbf{y}_{target}\|^2_{\mathbf{Q}}
+ \|\boldsymbol{\Delta u}\|^2_{\mathbf{R}}
$$

subject to:

$$
\mathbf{y}_{pred} = \mathbf{y}_{free} + \mathbf{A}_{dyn} \, \boldsymbol{\Delta u}
$$

$$
\boldsymbol{\Delta u}_{min} \leq \boldsymbol{\Delta u} \leq \boldsymbol{\Delta u}_{max}
\quad \text{(P2: MV rate limits)}
$$

$$
\mathbf{u}_{min} \leq \mathbf{u}_{current} + \mathbf{C}_{sum} \, \boldsymbol{\Delta u} \leq \mathbf{u}_{max}
\quad \text{(P1: MV hard limits)}
$$

$$
\mathbf{y}_{min} \leq \mathbf{y}_{pred} \leq \mathbf{y}_{max}
\quad \text{(P3/P4: CV limits, softened)}
$$

where:

- $$\mathbf{Q} = \text{diag}(Q_1, Q_1, \ldots, Q_1) \in \mathbb{R}^{(P \cdot n_y) \times (P \cdot n_y)}$$
  with $$Q_1 = \text{diag}(q_1, q_2, \ldots, q_{n_y})$$ being the per-CV
  weight matrix.

- $$\mathbf{R} = \text{diag}(R_1, R_1, \ldots, R_1) \in \mathbb{R}^{(M \cdot n_u) \times (M \cdot n_u)}$$
  with $$R_1 = \text{diag}(r_1, r_2, \ldots, r_{n_u})$$ being the per-MV
  move suppression matrix.

- $$\mathbf{C}_{sum}$$ is a block lower-triangular matrix of identity
  blocks that accumulates moves into absolute MV positions.

- $$\mathbf{y}_{target}$$ is the stacked target trajectory, typically
  the steady-state target from Layer 2 repeated $$P$$ times.

### 2.4 Substituting the Prediction Equation

Substituting the prediction equation into the objective and expanding:

$$
J = \|\mathbf{A}_{dyn} \boldsymbol{\Delta u} + \mathbf{y}_{free} - \mathbf{y}_{target}\|^2_{\mathbf{Q}} + \|\boldsymbol{\Delta u}\|^2_{\mathbf{R}}
$$

Let $$\mathbf{e} = \mathbf{y}_{free} - \mathbf{y}_{target}$$. Expanding:

$$
J = \boldsymbol{\Delta u}^T \underbrace{(\mathbf{A}_{dyn}^T \mathbf{Q} \, \mathbf{A}_{dyn} + \mathbf{R})}_{\mathbf{H}} \boldsymbol{\Delta u}
+ 2 \underbrace{\mathbf{e}^T \mathbf{Q} \, \mathbf{A}_{dyn}}_{\mathbf{f}^T} \boldsymbol{\Delta u}
+ \text{const.}
$$

This is a standard QP in the form:

$$
\min_{\boldsymbol{\Delta u}} \quad
\tfrac{1}{2} \boldsymbol{\Delta u}^T \mathbf{H} \, \boldsymbol{\Delta u}
+ \mathbf{f}^T \boldsymbol{\Delta u}
$$

subject to linear inequality constraints.

The Hessian $$\mathbf{H}$$ is positive definite (because $$\mathbf{R}$$
has positive diagonal entries), guaranteeing a unique global minimum.

### 2.5 OSQP Solver

Azeotrope APC uses [OSQP](https://osqp.org) (Operator Splitting
Quadratic Program) as the Layer 1 QP solver. OSQP is an open-source,
first-order method based on the alternating direction method of
multipliers (ADMM). Key properties:

- **Warm-starting:** The solution from the previous cycle is used as the
  initial guess, dramatically reducing solve time (typically 1--5
  iterations after warm-start vs. 50--200 from cold start).
- **Infeasibility detection:** OSQP returns a certificate of primal or
  dual infeasibility, which triggers the constraint relaxation logic
  (see Section 6).
- **Sparse formulation:** The Hessian and constraint matrices are stored
  in CSC format; OSQP exploits sparsity for $$O(n)$$-like performance
  on the structured MPC problem.
- **No matrix factorizations:** Unlike interior-point methods, OSQP
  avoids expensive Cholesky factorizations, making it suitable for
  real-time embedded deployment.

Typical solve times for industrial-scale problems:

| Problem size | Warm-start time | Cold-start time |
|---|---|---|
| 6 CV, 3 MV (heater) | 0.1--0.5 ms | 2--10 ms |
| 20 CV, 10 MV (column) | 0.5--2 ms | 10--50 ms |
| 50 CV, 30 MV (complex) | 2--10 ms | 50--200 ms |

### 2.6 Move Blocking and Receding Horizon

Only the first move $$\Delta u(k)$$ of the optimal sequence is actually
applied to the plant. At the next sample period, the entire optimization
is repeated with updated measurements. This is the **receding horizon**
principle.

The remaining moves $$\Delta u(k+1), \ldots, \Delta u(k+M-1)$$ are
discarded and re-optimized. This provides inherent robustness: the
controller continuously corrects for model errors and disturbances.

**Move blocking** can be applied to reduce the number of decision
variables by constraining groups of moves to be equal:

$$
\Delta u(k+j) = \Delta u(k+j-1) \quad \text{for } j \in \text{blocked set}
$$

This is equivalent to reducing $$M$$ but allowing non-uniform spacing.
Move blocking is rarely needed for problems smaller than 30 MVs.

### 2.7 The Role of Move Suppression

The move suppression term $$\|\boldsymbol{\Delta u}\|^2_{\mathbf{R}}$$
prevents the controller from making excessively large or rapid MV changes.
Physically, this corresponds to:

- **Equipment protection:** Valves, dampers, and pumps have finite
  actuation speeds and mechanical wear limits.
- **Process stability:** Large, sudden moves can excite nonlinear
  dynamics, trigger safety trips, or cause product quality upsets.
- **Regulatory layer interaction:** MPC outputs are typically setpoints
  to PID loops. If MPC moves faster than the PID can track, the base
  layer oscillates.

The move suppression weight $$r_q$$ for MV $$q$$ determines the tradeoff
between CV tracking performance and MV smoothness. See Section 5.1 for
detailed tuning guidance.

---

## 3. Layer 2: Steady-State Target

### 3.1 Purpose

Layer 2 runs every sample period, *before* Layer 1. Its job is to find
the **optimal steady-state operating point** within the current
constraint envelope. Layer 1 then drives the process dynamically toward
this target.

The two-layer architecture separates concerns:

- **Layer 2** answers: "Where should we be?" (economics, constraint
  satisfaction).
- **Layer 1** answers: "How do we get there?" (dynamics, stability).

### 3.2 LP/QP Formulation

The steady-state target problem is:

$$
\min_{u_{ss}, y_{ss}} \quad
\|y_{ss} - y_{sp}\|^2_{Q_s} + c^T u_{ss}
$$

subject to:

$$
y_{ss} = K \, u_{ss} + d_{ss}
$$

$$
u_{min} \leq u_{ss} \leq u_{max}
$$

$$
y_{min} \leq y_{ss} \leq y_{max} \quad \text{(prioritized soft constraints)}
$$

where:

- $$K$$ is the steady-state gain matrix.
- $$d_{ss}$$ is the steady-state disturbance estimate (from the
  disturbance observer).
- $$Q_s$$ is the steady-state CV weight matrix.
- $$c$$ is the MV cost vector (economics).
- $$y_{sp}$$ is the CV setpoint vector.

### 3.3 Economic Optimization

The linear cost term $$c^T u_{ss}$$ enables **economic optimization**.
Each MV is assigned a cost coefficient:

- **Positive cost** (e.g., fuel flow, steam, electricity): the optimizer
  minimizes usage.
- **Negative cost** (e.g., throughput, product flow): the optimizer
  maximizes usage.
- **Zero cost**: the MV is free to move wherever constraints allow.

The optimizer drives each MV toward the bound that minimizes the total
economic cost, subject to all CV constraints being satisfied.

**Example: Cumene heater.** The fuel gas valve (FCV-410) has a positive
cost (fuel is expensive). The optimizer will reduce fuel flow as much as
possible while keeping all temperatures within their operating limits.
If the outlet temperature (TIT-400) has a minimum constraint of 680 degF
and reducing fuel would violate it, the optimizer finds the minimum fuel
flow that satisfies the temperature constraint.

### 3.4 Preferences and Optimization Types

Each variable can be assigned an **optimization type** (preference) that
determines how Layer 2 treats it:

**MV Preferences:**

| Preference | Behavior | LP cost sign |
|---|---|---|
| Minimize | Drive to lower limit | Positive |
| Maximize | Drive to upper limit | Negative |
| Min Movement | Stay near current value | Zero (quadratic) |
| None | Free variable | Zero |

**CV Preferences:**

| Preference | Behavior | Effect |
|---|---|---|
| Minimize | Setpoint at lower operating limit | Target = lo limit |
| Maximize | Setpoint at upper operating limit | Target = hi limit |
| Target | Track explicit setpoint | Target = setpoint |
| None | Free within limits | No tracking penalty |

When "Minimize" or "Maximize" is selected for a CV, the effective
setpoint is automatically set to the corresponding operating limit, and
the CV weight is applied as a tracking penalty toward that limit.

### 3.5 Lexicographic LP (Cost Ranks)

When multiple MVs have economic costs, **lexicographic LP** resolves
ties by priority. Each MV is assigned a **cost rank**:

1. The LP is solved for the highest-rank MV group first.
2. The optimal cost for that group is locked as a constraint.
3. The LP is re-solved for the next-rank group within the remaining
   feasible space.
4. This continues until all ranks are resolved.

**Example:** In a power plant, steam pressure has rank 3 (most
important) and fuel flow has rank 2. The optimizer first minimizes steam
cost. Once steam is at its optimum, it minimizes fuel cost within the
remaining degrees of freedom.

### 3.6 HiGHS Solver

Azeotrope APC uses [HiGHS](https://highs.dev) as the Layer 2 LP/QP
solver. HiGHS is a high-performance open-source solver for linear and
quadratic programming. It uses the revised simplex method (LP) and
interior-point method (QP).

Key properties:

- **Exact solutions:** Unlike OSQP's first-order method, HiGHS produces
  machine-precision solutions suitable for active constraint
  identification.
- **Dual information:** The dual variables (shadow prices) indicate the
  economic value of relaxing each constraint by one unit.
- **Warm-starting:** The simplex basis from the previous cycle is reused,
  typically reducing the solve to 0--2 iterations.

### 3.7 Shadow Prices

The dual variable (shadow price) associated with each constraint
indicates how much the objective function would improve if that
constraint were relaxed by one unit:

$$
\lambda_i = \frac{\partial J^*}{\partial b_i}
$$

In economic terms, the shadow price of a CV upper limit tells you:
"reducing this temperature limit by 1 degree would save \$X/hour in
operating cost."

Shadow prices are displayed in the Simulation tab's CV table under the
"Shadow Price" column. Large shadow prices indicate constraints that
significantly limit economic performance -- candidates for process
debottlenecking.

---

## 4. Layer 3: Nonlinear Optimizer

### 4.1 Purpose and Architecture

Layer 3 is the **real-time optimizer (RTO)**. Unlike Layers 1 and 2,
which use a linear model (step response or gain matrix), Layer 3 works
with the full nonlinear plant model. Its role is to:

1. Re-linearize the plant model at the current operating point.
2. Update the gain matrix $$K$$ used by Layer 2.
3. Update the step response model used by Layer 1.
4. Optionally solve a nonlinear economic optimization to find a better
   operating point.

Layer 3 runs periodically (every few minutes to hours), not every sample
period, because nonlinear optimization is computationally expensive.

### 4.2 CasADi and IPOPT

The nonlinear optimization uses [CasADi](https://web.casadi.org/) for
automatic differentiation and [IPOPT](https://coin-or.github.io/Ipopt/)
as the interior-point NLP solver.

CasADi constructs a symbolic computation graph of the plant model and
objective function. It then provides exact gradients, Jacobians, and
Hessians to IPOPT via automatic differentiation -- no finite differences
or hand-coded derivatives needed.

### 4.3 Re-Linearization

Given a nonlinear plant model $$\dot{x} = f(x, u)$$, $$y = h(x, u)$$,
the Jacobians at the current operating point $$(x_0, u_0)$$ are:

$$
A_c = \frac{\partial f}{\partial x}\bigg|_{x_0, u_0}, \quad
B_c = \frac{\partial f}{\partial u}\bigg|_{x_0, u_0}
$$

$$
C = \frac{\partial h}{\partial x}\bigg|_{x_0, u_0}, \quad
D = \frac{\partial h}{\partial u}\bigg|_{x_0, u_0}
$$

These continuous-time Jacobians are discretized using the matrix
exponential method:

$$
\begin{bmatrix} A_d & B_d \\ 0 & I \end{bmatrix}
= \exp\left(
\begin{bmatrix} A_c & B_c \\ 0 & 0 \end{bmatrix} T_s
\right)
$$

The resulting discrete $$(A_d, B_d, C, D)$$ are used to rebuild the step
response model and gain matrix.

### 4.4 Nonlinear Economic Optimization

When the plant model is nonlinear, the steady-state gain matrix $$K$$
depends on the operating point. Layer 3 can solve the full nonlinear
steady-state optimization:

$$
\min_{x_{ss}, u_{ss}} \quad c^T u_{ss}
$$

subject to:

$$
0 = f(x_{ss}, u_{ss}) \quad \text{(steady state)}
$$

$$
y_{ss} = h(x_{ss}, u_{ss})
$$

$$
u_{min} \leq u_{ss} \leq u_{max}
$$

$$
y_{min} \leq y_{ss} \leq y_{max}
$$

This NLP captures nonlinear interactions and constraints that the linear
Layer 2 approximation misses. The NLP solution provides a better
operating point and updated linearization for Layers 1--2.

### 4.5 When to Use Layer 3

Layer 3 is optional and should be enabled when:

- The plant has significant nonlinearities (e.g., reaction kinetics,
  thermodynamics, phase equilibria).
- The operating range spans multiple linearization regions.
- Economic optimization benefits from nonlinear gain correction.
- The plant model is available as a first-principles ODE.

Layer 3 is not needed when:

- The plant operates in a narrow range where linear models are adequate.
- No first-principles model is available (only step-test data).
- The sample time is so short that NLP solve time is a concern.

### 4.6 Execution Frequency

Layer 3 typically runs on a slower schedule than Layers 1--2:

| Application | Layer 3 frequency |
|---|---|
| CSTR (fast dynamics) | Every 5--10 minutes |
| Distillation column | Every 15--60 minutes |
| Fired heater | Every 30--120 minutes |
| Power boiler | Every 1--4 hours |

The frequency should be fast enough to track slow changes in operating
point but slow enough that each NLP solve completes before the next one
starts.

---

## 5. Tuning Guide

### 5.1 Move Suppression (R)

Move suppression is the most important tuning parameter. It directly
controls the tradeoff between CV tracking performance and MV smoothness.

**Physical meaning:** The move suppression weight $$r_q$$ for MV $$q$$
penalizes the square of each move:

$$
J_R = \sum_{j=0}^{M-1} r_q \, (\Delta u_q(k+j))^2
$$

A larger $$r_q$$ makes the controller prefer smaller moves on MV $$q$$.
This makes control smoother but slower.

**Setting move suppression from rate limits:**

The auto-tune formula in APC Architect computes:

$$
r_q = \frac{\alpha}{(\text{rate\_limit}_q)^2}
$$

where $$\alpha$$ is a scaling factor (default 0.1). The rate limit is
the maximum acceptable move per sample period in engineering units.

**Rationale:** If the maximum acceptable move is 5%/min, then
$$r_q = 0.1 / 25 = 0.004$$. A move of 5% would contribute
$$0.004 \times 25 = 0.1$$ to the objective, which is "noticeable" to the
optimizer but not prohibitively expensive.

**Practical rules of thumb:**

| Situation | Action |
|---|---|
| Controller too sluggish | Decrease $$r_q$$ by factor 2--5 |
| MV moves too aggressively | Increase $$r_q$$ by factor 2--5 |
| MV oscillating | Increase $$r_q$$ by factor 5--10 |
| CV not reaching setpoint | Check if $$r_q$$ is preventing sufficient moves |
| MV hitting rate limit every cycle | $$r_q$$ is too low (or rate limit too tight) |

**Example: Fuel gas valve.** The fuel gas valve (FCV-410) has a rate
limit of 2%/min. Auto-tune computes:

$$
r_{FCV} = \frac{0.1}{2^2} = 0.025
$$

After initial simulation, we observe the valve is too aggressive. We
increase to $$r_{FCV} = 0.1$$, and the response becomes smoother without
significantly degrading temperature control.

### 5.2 CV Weights (Q)

The CV weight $$q_i$$ determines how much the controller prioritizes
tracking CV $$i$$ versus other CVs. The objective function contains:

$$
J_Q = \sum_{p=1}^{P} \sum_{i=1}^{n_y} q_i \, (\hat{y}_i(k+p|k) - y_{target,i})^2
$$

**Setting CV weights from engineering ranges:**

$$
q_i = \frac{\beta}{(\text{range}_i)^2}
$$

where $$\text{range}_i = \text{eng\_hi}_i - \text{eng\_lo}_i$$ and
$$\beta$$ is a scaling factor (default 100). This normalizes the
weights so that a 1% deviation from setpoint (relative to the
engineering range) produces roughly the same penalty for all CVs.

**Relative importance:** If two CVs have the same engineering range but
CV A is twice as important as CV B, set $$q_A = 2 q_B$$. The
controller will sacrifice performance on B to improve A.

**Practical rules of thumb:**

| Situation | Action |
|---|---|
| CV not tracked tightly enough | Increase $$q_i$$ by factor 2--5 |
| CV tracked at expense of others | Decrease $$q_i$$ |
| Safety-critical CV | Set $$q_i$$ 10--100x higher than non-critical CVs |
| CV is an analyzer (noisy) | Reduce $$q_i$$ to prevent chasing noise |

**Warning:** Increasing all CV weights uniformly has no effect -- only
the ratio $$q_i / r_q$$ matters. If you want tighter control on all CVs,
decrease all $$r_q$$ values instead.

### 5.3 Max Move

The max move parameter sets a hard limit on the magnitude of a single
move:

$$
|\Delta u_q(k)| \leq \Delta u_{max,q}
$$

Unlike move suppression (which is a soft penalty), max move is a hard
constraint. It protects against:

- Sudden large moves when the controller first enters closed loop.
- Model-plant mismatch causing inappropriately large corrections.
- Equipment limitations (e.g., valve positioner slew rate).

**Setting max move:**

$$
\Delta u_{max,q} = \alpha \times \text{rate\_limit}_q
$$

where $$\alpha = 1.0$$ to $$2.0$$. Setting max move equal to the rate
limit means the controller can use the full rate limit in a single move.
Setting it to half the rate limit provides extra protection.

### 5.4 Prediction and Control Horizons

**Prediction Horizon (P):**

- Set $$P$$ to the longest open-loop settling time divided by $$T_s$$.
- If $$P$$ is too short, the controller ignores long-term interactions
  and may oscillate.
- If $$P$$ is too long, computation increases with marginal benefit.

**Control Horizon (M):**

- Start with $$M = 3$$ or $$M = 5$$.
- Increase $$M$$ only if the controller is too sluggish or if there are
  many active constraints.
- $$M > 10$$ is rarely needed; $$M > 20$$ is almost never beneficial.

**Relationship between M, P, and aggressiveness:**

$$
\text{aggressiveness} \propto \frac{M}{P}
$$

A large $$M/P$$ ratio means the controller has many degrees of freedom
relative to the prediction window -- it will be more aggressive. A small
ratio is more conservative.

### 5.5 Concern Values

Concern values control the **softness** of CV constraints. A CV with
concern $$c$$ has its constraint violation penalized as:

$$
J_{slack} = c^2 \times (\text{slack})^2
$$

where slack is the amount by which the CV exceeds its constraint.

| Concern value | Behavior |
|---|---|
| 0.01 | Very soft -- constraint easily violated |
| 0.5 | Moderate softness |
| 1.0 | Default -- reasonable stiffness |
| 5.0 | Stiff -- rarely violated |
| 100.0 | Near-hard constraint |

**Practical guidance:**

- **Product quality CVs** (e.g., composition, impurity): high concern
  (5--50). These should rarely be violated.
- **Temperature CVs**: moderate concern (1--5). Some transient violation
  is acceptable.
- **Draft/pressure CVs**: low concern (0.5--1). These are informational
  limits.

### 5.6 Tuning Workflow

The recommended tuning sequence:

1. **Start with auto-tune.** Click "Auto-Tune (Smart Defaults)" in the
   Layer 1 tab. This sets weights from engineering ranges and move
   suppression from rate limits.

2. **Run the simulator.** Switch to the Simulate tab and step through
   10--20 cycles. Observe CV tracking and MV movement.

3. **Adjust move suppression first.** If MVs are too aggressive, increase
   $$R$$. If too sluggish, decrease $$R$$. Change one MV at a time.

4. **Adjust CV weights second.** If a CV is not tracking well while
   others are fine, increase its weight. If a CV is dominating at the
   expense of others, decrease it.

5. **Test disturbance rejection.** Add a disturbance (change a DV or
   move a CV setpoint suddenly) and observe recovery.

6. **Test constraint handling.** Tighten a CV limit so it is active
   during operation. Verify the controller respects the limit while
   maintaining the best feasible performance.

7. **Check steady-state economics.** Use Step 6 (SS Calculator) to
   verify the Layer 2 target is reasonable.

8. **Iterate.** Repeat steps 2--7 until performance is satisfactory.
   Save intermediate tuning sets as recipes (see Section 14).

### 5.7 Common Tuning Mistakes

**Mistake 1: Setting all R values to 1.0.**
Move suppression should be scaled to the engineering range. A move of
1% on a valve and a move of 1 degC on a temperature setpoint have very
different physical significance. Using auto-tune (which scales by rate
limit) avoids this.

**Mistake 2: Increasing all Q values together.**
This has no effect on relative CV priorities. Only the ratio Q/R
matters.

**Mistake 3: Making M too large.**
Setting $$M = P$$ makes the controller aggressive and slow to solve.
Start with $$M = 3$$ to $$5$$.

**Mistake 4: Setting P shorter than the dead time.**
If the longest dead time is 20 steps and $$P = 15$$, the controller
cannot see the effect of its moves. Set $$P \geq 2 \times$$ longest
dead time.

**Mistake 5: Ignoring noise.**
Real measurements have noise. If the CV weight is too high, the
controller chases noise. Enable simulation noise (CV Noise column) to
test robustness.

---

## 6. Constraint Priority System

### 6.1 Five Priority Levels

Azeotrope APC implements a five-level constraint priority system,
inspired by the DMC3 architecture. When the controller cannot satisfy
all constraints simultaneously, it relaxes them in a defined order:

| Priority | Type | Description | Relaxation order |
|---|---|---|---|
| P1 | MV Hard Limits | Physical equipment limits (valve 0--100%) | Never relaxed |
| P2 | MV Rate Limits | Maximum MV move per sample period | Relaxed fifth |
| P3 | CV Safety Limits | Safety interlock thresholds | Relaxed fourth |
| P4 | CV Operating Limits | Normal operating constraints | Relaxed third |
| P5 | Setpoint Tracking | CV setpoint targets | Relaxed first |

The controller relaxes from the bottom up: it first sacrifices setpoint
tracking (P5), then widens operating limits (P4), then safety limits
(P3), then rate limits (P2). MV hard limits (P1) are never relaxed.

### 6.2 Infeasibility Handling

When the QP is infeasible (no solution satisfies all constraints), the
controller executes the following procedure:

1. **Detect infeasibility.** OSQP returns a primal infeasibility
   certificate.

2. **Relax P5 constraints.** Remove setpoint tracking from the
   objective. Re-solve.

3. **Relax P4 constraints.** If still infeasible, add slack variables to
   the CV operating limits. The slack is penalized by the concern value.
   Re-solve.

4. **Relax P3 constraints.** If still infeasible, add slack to safety
   limits. Re-solve.

5. **Relax P2 constraints.** If still infeasible, widen rate limits by a
   factor of 2. Re-solve.

6. **Emergency fallback.** If still infeasible with all soft constraints
   relaxed, the controller outputs zero moves ($$\Delta u = 0$$) and
   logs a critical alert.

### 6.3 CV Ranks

Within each priority level, CVs are further ordered by **rank**. A CV
with a higher rank is relaxed later (more important). Ranks range from
1 (least important) to 100 (most important).

**Example:** Two CVs both at P4 (operating limits):

- TIT-400 (outlet temperature): rank 50
- XI-490 (excess O2): rank 20

If both constraints cannot be satisfied, the controller relaxes XI-490
first because it has a lower rank. The outlet temperature constraint is
maintained as long as possible.

### 6.4 Soft Constraints and Slack Variables

For P3 and P4 constraints, the controller uses **soft constraints**
implemented via slack variables:

$$
y_{min,i} - s_i^{lo} \leq y_i \leq y_{max,i} + s_i^{hi}
$$

$$
s_i^{lo}, s_i^{hi} \geq 0
$$

The slack variables are added to the objective with a penalty:

$$
J_{slack} = \sum_{i} c_i^2 \left( (s_i^{lo})^2 + (s_i^{hi})^2 \right)
$$

where $$c_i$$ is the concern value. Higher concern means the constraint
is more expensive to violate, so it is violated less.

### 6.5 Interaction Between Priorities and Concerns

Priorities and concerns serve complementary roles:

- **Priorities** determine the relaxation *order* (which constraints
  are sacrificed first in a global sense).
- **Concerns** determine the relaxation *amount* (how much each
  constraint is allowed to be violated once it is eligible for
  relaxation).

A P3 constraint with low concern is relaxed easily once the system needs
to violate P3 constraints. A P3 constraint with high concern is the
last P3 constraint to be relaxed.

### 6.6 Practical Priority Assignment

| Variable type | Typical priority | Rationale |
|---|---|---|
| Valve position (0--100%) | P1 | Physical limit |
| Valve rate of change | P2 | Mechanical limit |
| Safety trip temperature | P3 | Interlock protection |
| Normal operating temperature | P4 | Product quality |
| Temperature setpoint | P5 | Economic target |
| Analyzer (O2, CO) | P4, low rank | Important but noisy |
| Draft pressure | P4, lowest rank | Least critical |

---

## 7. Feedback Filters

### 7.1 The Prediction Error

At every sample period, the controller compares its prediction from the
previous cycle with the actual measurement:

$$
e(k) = y_{meas}(k) - \hat{y}(k|k-1)
$$

This prediction error captures everything the model does not account
for: disturbances, model-plant mismatch, noise, and unmeasured upsets.

The prediction error must be fed back into the prediction engine to
maintain **offset-free control** -- without feedback, persistent
disturbances cause a permanent offset between the setpoint and the
measurement.

### 7.2 Full Feedback

With full feedback, the entire prediction error is applied as an
additive bias to all future predictions:

$$
d(k) = e(k)
$$

$$
\hat{y}(k+p|k) = y_{model}(k+p|k) + d(k) \quad \forall p
$$

**Properties:**

- Fastest disturbance rejection (zero steady-state offset in one step).
- Most sensitive to measurement noise (noise passes directly into
  predictions).
- Best for clean, reliable measurements (e.g., flow, pressure,
  temperature with good sensor).

### 7.3 First-Order Filter

The prediction error is filtered through a first-order exponential
filter:

$$
d(k) = \alpha \, d(k-1) + (1 - \alpha) \, e(k)
$$

where $$\alpha = e^{-T_s / \tau_f}$$ and $$\tau_f$$ is the **prediction
error lag** (filter time constant).

**Properties:**

- Smoother disturbance estimate (noise is attenuated).
- Slower disturbance rejection (takes $$3\tau_f$$ to fully track a step
  disturbance).
- Best for noisy measurements (analyzers, composition, lab values).

**Setting the prediction error lag:**

$$
\tau_f = 3 \times T_s \quad \text{(moderately noisy)}
$$

$$
\tau_f = 10 \times T_s \quad \text{(very noisy, e.g., analyzer)}
$$

$$
\tau_f = 0 \quad \text{(equivalent to full feedback)}
$$

### 7.4 Moving Average Filter

The prediction error is averaged over the last $$H$$ samples:

$$
d(k) = \frac{1}{H} \sum_{j=0}^{H-1} e(k-j)
$$

**Properties:**

- Effective at rejecting periodic noise (e.g., cycle-induced
  oscillations).
- Introduces a phase lag of approximately $$H/2$$ samples.
- Best for measurements with known periodic disturbances.

**Setting the prediction error horizon (H):**

- Set $$H$$ equal to the noise period if known.
- Otherwise, $$H = 5$$ to $$10$$ is a reasonable starting point.

### 7.5 Choosing a Filter

| Measurement quality | Recommended filter | Pred Error Lag |
|---|---|---|
| Clean (flow, pressure) | Full Feedback | -- |
| Moderate noise (temperature) | First Order | $$3 T_s$$ |
| Noisy (analyzer, lab) | First Order | $$10 T_s$$ |
| Periodic noise | Moving Average | Period/$$T_s$$ |
| Intermittent (lab value) | First Order + Intermittent flag | $$10 T_s$$ |

### 7.6 Intermittent Measurements

Some CVs are measured intermittently -- for example, a lab analysis that
arrives every 4 hours while the controller runs every minute. Between
lab updates, the measurement is stale.

When the **Intermittent** flag is set for a CV:

- The feedback filter is only updated when a new measurement arrives.
- Between updates, the disturbance estimate is held constant:
  $$d(k) = d(k_{last})$$.
- The prediction uses the model trajectory plus the last disturbance
  estimate.

This prevents the controller from repeatedly correcting for the same
(stale) prediction error.

### 7.7 Rotation Factor

For **ramp variables** (CVs that change continuously, such as
integrating processes or batch trajectories), the rotation factor
$$\rho \in [0, 1]$$ controls how the prediction error bias is
distributed across the prediction horizon:

- $$\rho = 0$$: Constant bias (same correction at all prediction steps).
- $$\rho = 1$$: Linear extrapolation (correction grows linearly into
  the future).

A rotation factor of 0.3 to 0.5 is typical for integrating processes
like tank levels.

---

## 8. Subcontrollers

### 8.1 What Are Subcontrollers?

A **subcontroller** is a named group of MVs, CVs, and DVs that the
controller treats as a semi-independent unit. Subcontrollers are used
when a large controller has natural partitions -- groups of variables
that interact strongly within the group but weakly between groups.

### 8.2 When to Use Subcontrollers

Subcontrollers are appropriate when:

- The plant has distinct sections (e.g., a heater section and a reactor
  section) that share some MVs but have mostly independent dynamics.
- Some MVs should only affect certain CVs (e.g., a valve that affects
  only local temperatures, not distant compositions).
- You want to shed (disable) a section of the controller during
  maintenance without affecting the rest.
- The controller is large (>20 CVs) and you want to simplify tuning
  by working on one section at a time.

### 8.3 Critical vs. Non-Critical Subcontrollers

A subcontroller can be marked **Critical**:

- A critical subcontroller must have a minimum number of good
  (available) MVs and CVs to continue operating. If too many
  MVs or CVs are bad (sensor failure, manual override), the critical
  subcontroller sheds and the controller enters a degraded mode.
- A non-critical subcontroller can be shed without affecting the
  overall controller status.

### 8.4 Minimum Good MVs and CVs

Each subcontroller has parameters:

- **Min Good MVs:** Minimum number of MVs that must be in AUTO mode for
  the subcontroller to operate. If fewer MVs are available, the
  subcontroller sheds.
- **Min Good CVs:** Minimum number of CVs with valid measurements. If
  fewer CVs have good data, the subcontroller sheds.

**Rule of thumb:** Set Min Good MVs to $$\max(1, n_{mv}/2)$$ and Min
Good CVs to $$\max(1, n_{cv}/2)$$.

### 8.5 Variable Assignment

Each MV, CV, and DV is assigned to exactly one subcontroller. The
assignment is typically based on the physical plant layout:

**Example: Cumene heater with two subcontrollers.**

| Variable | Subcontroller | Rationale |
|---|---|---|
| FCV-410 (fuel valve) | Combustion | Controls fuel |
| SC-400 (damper) | Combustion | Controls airflow |
| FCV-411 (air valve) | Combustion | Controls airflow |
| TIT-400 (outlet temp) | Heat Transfer | Output of heater |
| TIT-402 (bridgewall) | Combustion | Firebox measurement |
| TIT-412 (coil temp) | Heat Transfer | Coil measurement |
| XI-490 (O2) | Combustion | Combustion measurement |
| XI-410 (draft) | Combustion | Stack measurement |
| AIT-410 (CO) | Combustion | Emission measurement |

Note that some MVs (fuel valve) affect both subcontrollers' CVs. The
controller handles this through the cross-coupling terms in the gain
matrix.

### 8.6 Shedding Behavior

When a subcontroller sheds:

1. All MVs in the subcontroller stop receiving MPC moves.
2. CVs in the subcontroller continue to be monitored but are removed
   from the QP.
3. The remaining subcontrollers continue to operate normally.
4. An alarm is raised in the Activity log.

When the shed condition clears (e.g., a sensor is repaired), the
subcontroller can be re-enabled. The controller re-initializes the
prediction engine for that subcontroller's variables and gradually
resumes control.

---

## 9. Disturbance Observer

### 9.1 Output Bias Estimation

The disturbance observer estimates the unknown disturbance acting on
each CV. This disturbance represents everything the model does not
capture: unmeasured upsets, model error, slow process drift, and
sensor bias.

The simplest approach is **output bias estimation**: the disturbance is
modeled as an additive bias on each output:

$$
y(k) = y_{model}(k) + d(k)
$$

where $$d(k)$$ is estimated from the prediction error:

$$
d(k) = y_{meas}(k) - y_{model}(k|k-1)
$$

This is exactly the prediction error discussed in Section 7. The
feedback filter determines how the raw prediction error is smoothed
into the disturbance estimate.

### 9.2 Integrating Disturbance Model

For offset-free control in the presence of persistent (step-like)
disturbances, the disturbance must be modeled as an integrator:

$$
d(k+1) = d(k) + w(k)
$$

where $$w(k)$$ is a zero-mean disturbance innovation. This model says:
"the disturbance is constant plus random walk." The Kalman filter
(below) uses this model to estimate $$d(k)$$.

The integrating disturbance model guarantees that the controller will
eventually eliminate any constant offset between the measurement and the
setpoint, regardless of model error. This is the theoretical foundation
for "offset-free MPC."

### 9.3 Kalman Filter Formulation

The full disturbance observer augments the plant state with the
disturbance:

$$
\underbrace{\begin{bmatrix} x(k+1) \\ d(k+1) \end{bmatrix}}_{\bar{x}(k+1)}
= \underbrace{\begin{bmatrix} A & B_d \\ 0 & I \end{bmatrix}}_{\bar{A}}
\underbrace{\begin{bmatrix} x(k) \\ d(k) \end{bmatrix}}_{\bar{x}(k)}
+ \underbrace{\begin{bmatrix} B \\ 0 \end{bmatrix}}_{\bar{B}} u(k)
+ \bar{w}(k)
$$

$$
y(k) = \underbrace{\begin{bmatrix} C & I \end{bmatrix}}_{\bar{C}} \bar{x}(k) + v(k)
$$

where $$B_d$$ is the disturbance input matrix (often set to $$B_d = 0$$
if disturbances enter only at the output), $$\bar{w}(k)$$ is the
process noise, and $$v(k)$$ is measurement noise.

The steady-state Kalman gain $$\bar{L}$$ is computed offline by solving
the discrete algebraic Riccati equation (DARE):

$$
\bar{P} = \bar{A} \bar{P} \bar{A}^T + \bar{Q}_w
- \bar{A} \bar{P} \bar{C}^T (\bar{C} \bar{P} \bar{C}^T + R_v)^{-1}
\bar{C} \bar{P} \bar{A}^T
$$

$$
\bar{L} = \bar{P} \bar{C}^T (\bar{C} \bar{P} \bar{C}^T + R_v)^{-1}
$$

At each sample, the observer runs:

$$
\text{Predict: } \hat{\bar{x}}^-(k) = \bar{A} \hat{\bar{x}}(k-1) + \bar{B} u(k-1)
$$

$$
\text{Update: } \hat{\bar{x}}(k) = \hat{\bar{x}}^-(k) + \bar{L} \bigl(y(k) - \bar{C} \hat{\bar{x}}^-(k)\bigr)
$$

The disturbance estimate is then extracted:

$$
\hat{d}(k) = [\text{last } n_y \text{ elements of } \hat{\bar{x}}(k)]
$$

### 9.4 Tuning the Kalman Filter

The Kalman filter requires two noise covariance matrices:

- **Process noise** $$\bar{Q}_w$$: how fast the disturbance changes.
  Larger $$\bar{Q}_w$$ makes the observer respond faster to
  disturbances but also amplifies noise.
- **Measurement noise** $$R_v$$: how noisy the measurements are. Larger
  $$R_v$$ makes the observer smoother but slower.

The ratio $$\bar{Q}_w / R_v$$ determines the observer bandwidth, similar
to the prediction error lag in the exponential filter.

**Practical guidance:**

- For most applications, the simple exponential filter (Section 7.3) is
  sufficient and easier to tune.
- The Kalman filter is preferred when the plant has significant state
  dynamics between samples (not captured by step response) or when
  formal optimality is important.
- Start with $$\bar{Q}_w = 0.01 I$$ and $$R_v = I$$, then increase
  $$\bar{Q}_w$$ if disturbance tracking is too slow.

### 9.5 Exponential Filter vs. Kalman Filter

| Property | Exponential filter | Kalman filter |
|---|---|---|
| Tuning complexity | 1 parameter ($$\tau_f$$) per CV | 2 matrices ($$Q_w$$, $$R_v$$) |
| Optimality | Heuristic | Optimal for linear-Gaussian |
| Cross-coupling | No (each CV independent) | Yes (uses plant model) |
| Computation | Trivial | Matrix operations each cycle |
| Recommended for | Most applications | Large MIMO with state dynamics |

---

## 10. Simulation and What-If Testing

### 10.1 The Simulation Engine

The APC Architect simulation engine (`SimEngine`) provides closed-loop
simulation of the controller and plant model. It runs entirely in
software -- no connection to the live process is needed.

Each simulation cycle:

1. Run input calculations (user Python scripts).
2. Read plant measurements (from the simulated plant model).
3. Execute the MPC controller (Layers 1--2, optionally 3).
4. Apply the computed moves to the simulated plant.
5. Run output calculations (user Python scripts).
6. Log results and update plots.

### 10.2 Step Simulation vs. Continuous Run

**Step simulation** (F7 or Step button): Advances one sample period at a
time. Useful for detailed inspection of each cycle's behavior.

**Continuous run** (F5 or Run button): Runs continuously at a
configurable speed (1x to 100x real time). Useful for testing long-term
behavior.

**Auto-run** (Shift+F5): Runs a fixed number of steps (e.g., 60) and
then stops. Useful for automated testing.

### 10.3 Noise Injection

The simulator can inject Gaussian measurement noise on each CV:

$$
y_{noisy}(k) = y_{true}(k) + \sigma_i \, \xi(k)
$$

where $$\sigma_i$$ is the noise standard deviation for CV $$i$$ (set in
the "Simulation Noise" column) and $$\xi(k) \sim \mathcal{N}(0, 1)$$.

Noise injection is essential for testing:

- Whether the controller chases noise (move suppression too low or CV
  weight too high).
- Whether the feedback filter adequately smooths the disturbance
  estimate.
- Whether the control horizon $$M$$ provides sufficient averaging.

### 10.4 What-If Scenarios

The simulator supports interactive what-if testing:

**Setpoint changes:** Click on a CV's setpoint cell and type a new
value. The controller immediately begins tracking the new setpoint.

**Disturbance injection:** Change a DV value to simulate an unmeasured
upset. Observe how quickly the controller rejects the disturbance.

**Constraint tightening:** Change an operating limit (Operator Lo/Hi)
and observe how the controller respects the new constraint.

**MV manual override:** Place an MV in manual mode (Combined Status =
MAN) and set a fixed value. The controller removes that MV from the
optimization and re-optimizes the remaining MVs.

**Open/closed loop:** Toggle between open-loop (no MPC moves) and
closed-loop (full MPC control) to compare controller performance.

### 10.5 What to Check Before Deployment

Before deploying to the live process, verify the following in simulation:

1. **Setpoint tracking:** Step all CV setpoints by 5--10% of their
   engineering range. All CVs should reach the new setpoint within the
   predicted settling time.

2. **Disturbance rejection:** Apply a step disturbance on each DV. The
   controller should return all CVs to their setpoints.

3. **Constraint satisfaction:** Tighten one CV limit until it is active.
   The controller should respect the limit and maintain the best
   feasible performance on other CVs.

4. **MV limits:** Verify that MV moves stay within rate limits and
   absolute limits.

5. **Infeasibility:** Create a deliberately infeasible scenario (e.g.,
   conflicting CV limits) and verify that the constraint priority system
   relaxes in the correct order.

6. **Noise robustness:** Enable noise and verify that MV movements are
   smooth (not chattering).

7. **Economic optimization:** Verify that the Layer 2 SS target drives
   MVs in the correct economic direction.

8. **Startup behavior:** Reset the simulation and observe the first
   10--20 cycles. The controller should smoothly ramp to the target
   without overshooting or oscillating.

---

## 11. Deployment via OPC UA

### 11.1 OPC UA Overview

[OPC UA](https://opcfoundation.org/about/opc-technologies/opc-ua/)
(Open Platform Communications Unified Architecture) is the industrial
standard for process data communication. APC Architect uses OPC UA to:

- **Read** CV measurements, DV values, and MV feedback from the DCS.
- **Write** MV setpoint changes to the DCS.
- **Monitor** loop status, bad-value flags, and manual overrides.

### 11.2 IO Tag Mapping

Each controller variable (MV, CV, DV) is mapped to one or more OPC UA
nodes via **IO tags**. The tag mapping defines which OPC UA node
corresponds to each parameter:

**Input variables (CVs, DVs):**

| Parameter | OPC UA node | Direction |
|---|---|---|
| `.PV` (process value) | Measurement node | Read |
| `.STATUS` | Quality/status node | Read |

**Output variables (MVs):**

| Parameter | OPC UA node | Direction |
|---|---|---|
| `.SP` (setpoint) | Output node | Write |
| `.PV` (feedback) | Measurement node | Read |
| `.STATUS` | Quality/status node | Read |
| `.MODE` | Auto/Manual mode node | Read |

### 11.3 Tag Templates

APC Architect provides tag templates for common DCS platforms:

| Template | Pattern | Example |
|---|---|---|
| DeltaV | `{tag}.{param}` | `FCV-410.SP` |
| Honeywell | `{tag}/{param}` | `FCV-410/SP` |
| Yokogawa | `{tag}:{param}` | `FCV-410:SP` |
| Emerson | `{tag}.{param}` | `FCV-410.SP` |
| Custom | User-defined | Any pattern |

### 11.4 Validation Limits

Before writing an MV value to the DCS, the deployment runtime validates
it against multiple limit levels:

1. **Validity limits:** Absolute physical limits. Values outside this
   range indicate a sensor failure or configuration error. The
   controller rejects the value and enters a safe state.

2. **Engineering limits:** Equipment limits. The controller clamps the
   output to these limits.

3. **Operating limits:** Operator-set limits. The controller uses these
   as soft constraints in the QP.

If an input measurement falls outside its validity limits, the
controller marks that CV as "BAD" and excludes it from the QP. If the
number of good CVs drops below the subcontroller's minimum, the
subcontroller sheds.

### 11.5 Runtime Execution Cycle

The deployment runtime executes the following cycle every sample period:

```
1. Timer fires at T_s interval
2. Read all input tags (CVs, DVs) via OPC UA
3. Validate inputs against limits
4. Run input calculations (user scripts)
5. Execute MPC controller (Layers 1-2-3)
6. Validate outputs against limits
7. Run output calculations (user scripts)
8. Write output tags (MVs) via OPC UA
9. Log cycle data to SQLite database
10. Update monitoring displays
```

### 11.6 Embedded Server for Testing

APC Architect includes an **embedded OPC UA server** that publishes the
simulated plant model's variables. This allows you to test the full
deployment pipeline (tag mapping, validation, read/write cycle) without
connecting to a real DCS.

To use the embedded server:

1. Check "Use embedded server" in the Deployment tab.
2. Click "Connect."
3. Click "Deploy."
4. The controller reads from and writes to the simulated plant via
   OPC UA, exactly as it would with a real DCS.

### 11.7 Monitoring During Operation

The Activity sub-tab in the Deployment view shows real-time status:

- **Per-variable status:** Current value, setpoint, limits, quality
  flag, active/inactive, and any violations.
- **Cycle timing:** Execution time per cycle (should be well below
  $$T_s$$).
- **Solver status:** Optimal, infeasible (with relaxation details), or
  error.
- **Communication status:** OPC UA read/write success rate, timeouts.

### 11.8 Shutdown Procedures

To stop the deployed controller:

1. Click "Stop" in the Deployment tab. This sets all MVs to their
   current values (no more MPC moves).
2. The runtime continues monitoring but does not compute or apply moves.
3. MV outputs remain at their last values -- they do not return to any
   default. The base-layer PIDs continue operating normally.

**Graceful shutdown:** The controller ramps MVs to their current values
over 2--3 cycles to avoid sudden jumps.

**Emergency shutdown:** The controller immediately stops writing to all
MVs. The base-layer PIDs maintain control at whatever setpoints were
last written.

---

## 12. Calculations (Python Scripting)

### 12.1 Overview

Calculations are user-defined Python scripts that run before (input
calculations) or after (output calculations) the MPC controller
executes each cycle. They enable:

- **Data preprocessing:** averaging measurements, applying engineering
  unit conversions, computing derived quantities.
- **Custom constraints:** implementing process-specific logic that
  cannot be expressed as linear constraints.
- **Adaptive tuning:** adjusting weights, limits, or setpoints based on
  operating conditions.
- **External data:** pulling data from databases, calculators, or other
  systems.

### 12.2 Input vs. Output Calculations

**Input calculations** run before the MPC controller:

- Use them to preprocess measurements, compute derived CVs, validate
  data quality, or override bad values.
- They can modify CV values, DV values, limits, and setpoints that the
  controller sees.

**Output calculations** run after the MPC controller:

- Use them to post-process MV outputs, apply additional clamping,
  compute diagnostic metrics, or log custom data.
- They can modify MV values before they are sent to the plant.

### 12.3 Available Variables

Inside a calculation script, the following variables are available:

**Variable accessors:**

| Variable | Type | Description |
|---|---|---|
| `cvs[i]` | object | i-th CV (has `.value`, `.setpoint`, `.limits.*`, `.weight`, etc.) |
| `mvs[i]` | object | i-th MV (has `.value`, `.steady_state`, `.limits.*`, etc.) |
| `dvs[i]` | object | i-th DV (has `.value`, `.steady_state`, `.limits.*`) |
| `cv` | dict | CV values by tag name: `cv["TIT-400.PV"]` |
| `mv` | dict | MV values by tag name |
| `dv` | dict | DV values by tag name |

**Engine state:**

| Variable | Type | Description |
|---|---|---|
| `t` | float | Current simulation time (minutes) |
| `cycle` | int | Current cycle number |
| `dt` | float | Sample period (minutes) |
| `engine` | SimEngine | The simulation engine object |

**User namespace:**

| Variable | Type | Description |
|---|---|---|
| `user` | dict | Persistent user dictionary (survives across cycles) |
| `np` | module | NumPy (pre-imported) |
| `math` | module | Python math module (pre-imported) |
| `log` | function | Logging function: `log("message")` |

### 12.4 Example: Temperature Average

```python
# Input calculation: compute average temperature
avg = (cvs[0].value + cvs[1].value + cvs[2].value) / 3.0
user["avg_temp"] = avg
log(f"Average temperature: {avg:.1f} degF")
```

### 12.5 Example: Adaptive Weight

```python
# Input calculation: increase weight when near limit
cv = cvs[0]
margin = cv.limits.operating_hi - cv.value
if margin < 5.0:
    cv.weight = 50.0  # tighten control near the limit
    log(f"Near upper limit -- weight increased to 50.0")
else:
    cv.weight = 10.0
```

### 12.6 Example: Output Clamping

```python
# Output calculation: rate-limit the fuel valve output
mv = mvs[0]
if "last_fuel" not in user:
    user["last_fuel"] = mv.value
max_rate = 1.5  # %/min
delta = mv.value - user["last_fuel"]
if abs(delta) > max_rate * dt:
    mv.value = user["last_fuel"] + max_rate * dt * (1 if delta > 0 else -1)
    log(f"Fuel valve rate-limited: {delta:.2f} -> {mv.value:.2f}")
user["last_fuel"] = mv.value
```

### 12.7 Example: History Tracking

```python
# Input calculation: track temperature history for trending
if "history" not in user:
    user["history"] = []
user["history"].append(cvs[0].value)
if len(user["history"]) > 1000:
    user["history"] = user["history"][-500:]
```

### 12.8 Testing Calculations

In the Calculations tab, you can:

1. Write or edit the script in the code editor.
2. Click "Test Run" to execute the script once with the current engine
   state. Any errors are displayed in the Activity Log.
3. Click "Apply" (Ctrl+S) to save the script and activate it for all
   future cycles.

The Variables Browser on the left shows all available variables and
their current values. Double-click a variable to insert its accessor
into the editor.

The Live State panel shows the current values of all variables, updated
at 2 Hz. Use this to verify that your script is producing the expected
results.

---

## 13. Performance Monitoring

### 13.1 Key Performance Indicators

After deployment, controller performance should be monitored using
quantitative KPIs:

**MV Utilization:** What fraction of the time each MV is actively
controlled (not at a limit):

$$
\text{Utilization}_q = 1 - \frac{\text{time at limit}}{\text{total time}}
$$

An MV with low utilization (e.g., <20%) is effectively stuck at a
constraint. Either the constraint should be relaxed, or the MV is
redundant and can be removed from the controller.

**CV Compliance:** What fraction of the time each CV stays within its
operating limits:

$$
\text{Compliance}_i = \frac{\text{time within limits}}{\text{total time}}
$$

Target: >95% compliance for P4 constraints, >99.9% for P3 constraints.

**CV Standard Deviation:** The standard deviation of each CV around its
setpoint or target:

$$
\sigma_i = \sqrt{\frac{1}{N} \sum_{k=1}^{N} (y_i(k) - y_{target,i})^2}
$$

Compare with the CV noise level. If $$\sigma_i \gg \sigma_{noise}$$,
the controller is contributing additional variability (possible
oscillation or aggressive tuning).

### 13.2 MV Utilization Analysis

For economic optimization to deliver value, MVs must have room to move.
The MV utilization analysis identifies:

- **Saturated MVs:** Always at a limit. These cannot participate in
  optimization. Consider widening limits or adding new MVs.
- **Under-utilized MVs:** Rarely move. These may have too much move
  suppression or may not be needed.
- **Well-utilized MVs:** Move freely within their range. These
  contribute most to optimization value.

### 13.3 Economic Benefit Estimation

The economic benefit of APC is estimated by comparing the actual
operating point with the "no-controller" baseline:

$$
\text{Benefit} = \sum_{q=1}^{n_u} c_q \, (u_{q,\text{baseline}} - u_{q,\text{actual}})
$$

where $$c_q$$ is the economic cost of MV $$q$$.

For CVs pushed closer to constraints (e.g., throughput maximization):

$$
\text{Benefit} = \sum_{i} v_i \, (y_{i,\text{actual}} - y_{i,\text{baseline}})
$$

where $$v_i$$ is the value per unit of CV $$i$$.

**Practical approach:**

1. Record the operating point before APC activation (baseline).
2. Run APC for several days.
3. Compare average MV and CV values.
4. Compute benefit using known economic costs/values.
5. Account for different operating conditions (feedstock changes,
   ambient temperature) that could confound the comparison.

### 13.4 Model-Plant Mismatch Detection

Model-plant mismatch (MPM) degrades controller performance over time.
Indicators of MPM:

**Prediction error trend:** If the prediction error $$e(k)$$ shows a
persistent trend (not zero-mean), the model gain or dynamics are wrong.

$$
\bar{e}_i = \frac{1}{N} \sum_{k=1}^{N} e_i(k) \neq 0
\quad \Rightarrow \quad \text{gain mismatch}
$$

**Prediction error autocorrelation:** If the prediction error is
autocorrelated (successive errors are correlated), the model dynamics
are wrong (e.g., wrong time constant or dead time):

$$
r_e(\tau) = \frac{1}{N} \sum_{k=1}^{N-\tau} e(k) \, e(k+\tau)
\neq 0 \text{ for } \tau > 0
\quad \Rightarrow \quad \text{dynamic mismatch}
$$

**Increasing move suppression needed:** If the controller requires
progressively higher move suppression to remain stable, the model may
be degrading.

**Response to recommendations:**

- **Mild MPM** (prediction error <10% of CV range): Adjust the
  disturbance observer gain (increase prediction error lag).
- **Moderate MPM** (prediction error 10--30%): Consider re-identifying
  the affected channels.
- **Severe MPM** (prediction error >30% or oscillation): Disable APC on
  the affected subcontroller and re-identify.

### 13.5 Controller Health Dashboard

The runtime logs all cycle data to a SQLite database (see CLAUDE.md for
schema). The following queries provide a health summary:

**Average solve time by layer:**

```sql
SELECT layer, AVG(solve_time_ms) as avg_ms,
       MAX(solve_time_ms) as max_ms
FROM solver_log
WHERE timestamp_ms > ?
GROUP BY layer
```

**CV compliance over last 24 hours:**

```sql
SELECT cv_index,
       SUM(CASE WHEN measured BETWEEN lo_limit AND hi_limit THEN 1 ELSE 0 END)
         * 100.0 / COUNT(*) as compliance_pct
FROM cv_timeseries
WHERE timestamp_ms > ?
GROUP BY cv_index
```

**Infeasibility frequency:**

```sql
SELECT COUNT(*) as infeasible_cycles,
       COUNT(*) * 100.0 / (SELECT COUNT(*) FROM solver_log WHERE layer=1) as pct
FROM solver_log
WHERE layer = 1 AND status != 'OPTIMAL'
```

---

## 14. Recipes

### 14.1 What Is a Recipe?

A **recipe** is a saved set of tuning parameters (weights, move
suppression, concerns, ranks, limits, horizons, preferences) that can
be loaded and applied to the controller. Recipes enable:

- **A/B testing:** Compare two tuning strategies by switching between
  recipes.
- **Operating mode changes:** Different recipes for different feedstocks,
  ambient conditions, or production rates.
- **Rollback:** If a tuning change degrades performance, restore the
  previous recipe.
- **Documentation:** Each recipe serves as a timestamped record of the
  controller configuration.

### 14.2 Recipe Contents

A recipe stores:

| Category | Parameters |
|---|---|
| Horizons | $$P$$, $$M$$, $$N$$ |
| CV tuning | Weight, concern lo/hi, rank lo/hi, noise, filter type, pred error lag |
| MV tuning | Move suppression, rate limit, max move |
| Preferences | Opt type (Minimize/Maximize/None/Min Movement) per MV and CV |
| Economics | LP cost, cost rank per MV |
| Constraints | Operating lo/hi per CV and MV |
| Subcontrollers | Assignment and criticality |
| Calculations | All input and output scripts |

### 14.3 Saving a Recipe

In APC Architect:

1. Configure the controller as desired.
2. File > Save (Ctrl+S) saves the entire project, including the current
   tuning as the "default" recipe.
3. To save a named recipe variant, use File > Save As with a descriptive
   filename (e.g., `heater_conservative.apcproj`,
   `heater_aggressive.apcproj`).

### 14.4 Comparing Recipes

To compare two recipes:

1. Load recipe A and run a simulation with a standard test scenario
   (setpoint step, disturbance, constraint test).
2. Record the performance metrics (settling time, overshoot, MV
   movement, economic benefit).
3. Load recipe B and run the same test scenario.
4. Compare the metrics side by side.

**Quantitative comparison metrics:**

| Metric | Formula | Better = |
|---|---|---|
| IAE (Integrated Absolute Error) | $$\sum |e_i(k)|$$ | Lower |
| ISE (Integrated Squared Error) | $$\sum e_i(k)^2$$ | Lower |
| Total MV movement | $$\sum |\Delta u_q(k)|$$ | Lower (smoother) |
| Settling time (95%) | Time to reach 95% of setpoint | Shorter |
| Overshoot | Max deviation beyond setpoint | Lower |
| Economic benefit | $$c^T u_{avg}$$ | Lower (cost) |

### 14.5 A/B Testing in Production

For live A/B testing:

1. Deploy recipe A and run for a representative period (e.g., 8 hours).
2. Switch to recipe B and run for the same period.
3. Compare performance metrics.
4. Account for operating condition changes between periods.

**Caution:** A/B testing on a live process should be planned carefully.
Both recipes should have been validated in simulation first. The
difference between A and B should be small (e.g., 20% change in move
suppression, not 10x).

---

## Appendix A: QP in Standard Form

The Layer 1 QP, after substituting the prediction equation and
collecting terms, is in the standard OSQP form:

$$
\min_x \quad \tfrac{1}{2} x^T P \, x + q^T x
$$

$$
\text{s.t.} \quad l \leq A x \leq u
$$

where:

$$
x = \boldsymbol{\Delta u} \in \mathbb{R}^{M \cdot n_u}
$$

$$
P = \mathbf{A}_{dyn}^T \mathbf{Q} \, \mathbf{A}_{dyn} + \mathbf{R}
\in \mathbb{R}^{(M n_u) \times (M n_u)}
$$

$$
q = \mathbf{A}_{dyn}^T \mathbf{Q} \, (\mathbf{y}_{free} - \mathbf{y}_{target})
\in \mathbb{R}^{M n_u}
$$

$$
A = \begin{bmatrix}
I \\ -I \\ \mathbf{C}_{sum} \\ -\mathbf{C}_{sum} \\ \mathbf{A}_{dyn} \\ -\mathbf{A}_{dyn}
\end{bmatrix}, \quad
l = \begin{bmatrix}
\boldsymbol{\Delta u}_{min} \\ -\boldsymbol{\Delta u}_{max} \\
\mathbf{u}_{min} - \mathbf{u}_{current} \\ \mathbf{u}_{current} - \mathbf{u}_{max} \\
\mathbf{y}_{min} - \mathbf{y}_{free} \\ \mathbf{y}_{free} - \mathbf{y}_{max}
\end{bmatrix}, \quad
u = \begin{bmatrix}
\boldsymbol{\Delta u}_{max} \\ -\boldsymbol{\Delta u}_{min} \\
\infty \\ \infty \\ \infty \\ \infty
\end{bmatrix}
$$

When soft constraints are used, the decision vector is augmented with
slack variables:

$$
x = \begin{bmatrix} \boldsymbol{\Delta u} \\ \mathbf{s} \end{bmatrix}
$$

and the Hessian includes the slack penalty:

$$
P_{aug} = \begin{bmatrix} P & 0 \\ 0 & \text{diag}(c_1^2, c_2^2, \ldots) \end{bmatrix}
$$

---

## Appendix B: State-Space to Transfer Function

For reference, the transfer function matrix $$G(z)$$ corresponding to
the discrete state-space model is:

$$
G(z) = C (zI - A)^{-1} B + D
$$

The steady-state gain is:

$$
K = G(1) = C (I - A)^{-1} B + D
$$

Note the sign difference from the formula in Section 1.4: here
$$(I - A)^{-1}$$, which equals $$-(A - I)^{-1}$$. The code uses
$$K = -C (A - I)^{-1} B + D$$ equivalently.

---

## Appendix C: Glossary

| Term | Definition |
|---|---|
| **APC** | Advanced Process Control |
| **CSTR** | Continuous Stirred-Tank Reactor |
| **CV** | Controlled Variable (measured output) |
| **DCS** | Distributed Control System |
| **DMC** | Dynamic Matrix Control (original MPC algorithm by Shell) |
| **DV** | Disturbance Variable (measured but uncontrolled input) |
| **ERA** | Eigensystem Realization Algorithm |
| **FIR** | Finite Impulse Response |
| **FOPTD** | First Order Plus Time Delay |
| **HiGHS** | High-performance LP/QP solver |
| **IAE** | Integrated Absolute Error |
| **IPOPT** | Interior Point Optimizer (NLP solver) |
| **ISE** | Integrated Squared Error |
| **LP** | Linear Program |
| **MIMO** | Multiple-Input Multiple-Output |
| **MPC** | Model Predictive Control |
| **MPM** | Model-Plant Mismatch |
| **MV** | Manipulated Variable (controlled input / actuator) |
| **NLP** | Nonlinear Program |
| **OPC UA** | Open Platform Communications Unified Architecture |
| **OSQP** | Operator Splitting Quadratic Program (QP solver) |
| **PID** | Proportional-Integral-Derivative (base-layer controller) |
| **QP** | Quadratic Program |
| **RTO** | Real-Time Optimization |
| **SISO** | Single-Input Single-Output |

---

## References

1. Cutler, C.R. and Ramaker, B.L. "Dynamic Matrix Control -- A Computer
   Control Algorithm." Joint Automatic Control Conference, 1980.

2. Garcia, C.E. and Morari, M. "Internal Model Control." Industrial &
   Engineering Chemistry Process Design and Development, 1982.

3. Qin, S.J. and Badgwell, T.A. "A Survey of Industrial Model
   Predictive Control Technology." Control Engineering Practice, 2003.

4. Rawlings, J.B. and Mayne, D.Q. "Model Predictive Control: Theory,
   Computation, and Design." Nob Hill Publishing, 2017.

5. Stellato, B. et al. "OSQP: An Operator Splitting Solver for
   Quadratic Programs." Mathematical Programming Computation, 2020.

6. Huangfu, Q. and Hall, J.A.J. "Parallelizing the Dual Revised
   Simplex Method." Mathematical Programming Computation, 2018.

7. Andersson, J.A.E. et al. "CasADi: A Software Framework for Nonlinear
   Optimization and Optimal Control." Mathematical Programming
   Computation, 2019.

8. Wachter, A. and Biegler, L.T. "On the Implementation of an
   Interior-Point Filter Line-Search Algorithm for Large-Scale Nonlinear
   Programming." Mathematical Programming, 2006.

9. Pannocchia, G. and Rawlings, J.B. "Disturbance Models for
   Offset-Free Model-Predictive Control." AIChE Journal, 2003.
