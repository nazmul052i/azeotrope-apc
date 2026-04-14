# APC Fundamentals: A Practical Guide to Model Predictive Control

**Audience:** Process engineers and instrument engineers with PID experience who are
implementing Advanced Process Control for the first time.

**Purpose:** This guide connects the theory of MPC and three-layer optimization to
the practical workflow of identifying models, configuring controllers, and deploying
them on real processes. It is written for the Azeotrope APC platform but the concepts
apply to any industrial MPC system.

---

## Table of Contents

1. [What is Advanced Process Control?](#1-what-is-advanced-process-control)
2. [Model Predictive Control (MPC) Theory](#2-model-predictive-control-mpc-theory)
3. [The Three-Layer Architecture](#3-the-three-layer-architecture)
4. [The Role of Identification in APC](#4-the-role-of-identification-in-apc)
5. [From Model to Controller](#5-from-model-to-controller)
6. [Tuning an MPC Controller](#6-tuning-an-mpc-controller)
7. [Disturbance Handling](#7-disturbance-handling)
8. [Performance Monitoring](#8-performance-monitoring)

---

## 1. What is Advanced Process Control?

### 1.1 The Limits of PID Control

Every process engineer knows PID controllers. They are the workhorses of industrial
automation -- reliable, well-understood, and effective for single-loop regulation. A
PID controller measures one process variable (PV), compares it to a setpoint (SP),
and adjusts one output (OP) to drive the error to zero.

For a single tank level, a single temperature loop, or a single flow controller, PID
is usually all you need. The problem arises when loops interact.

Consider a distillation column. You have:

- **Reflux flow** that affects both the overhead composition and the tray temperatures.
- **Reboiler duty** that affects the bottoms composition, the overhead composition,
  and every tray temperature.
- **Feed rate** that disturbs everything.
- **Overhead pressure** that interacts with condenser duty.

If you increase reflux to improve overhead purity, the reboiler sees a disturbance
(more liquid flowing down) and reacts. That reaction changes the temperatures, which
causes the temperature controllers to move, which affects the reflux... and the
whole column oscillates.

This is the **multivariable interaction problem**. PID controllers are designed for
single-input, single-output (SISO) systems. When you have multiple inputs affecting
multiple outputs -- a MIMO system -- PID loops fight each other.

The traditional workaround is detuning: make every loop slow enough that it does not
disturb its neighbors. This works, but at a cost. Detuned loops respond slowly to
disturbances, allow larger deviations from setpoint, and cannot push the process to
its most profitable operating point.

### 1.2 What APC Does Differently

Advanced Process Control, specifically Model Predictive Control (MPC), solves the
multivariable problem by controlling all the interacting variables simultaneously
with a single controller that understands the relationships between them.

An MPC controller:

1. **Knows the model.** It has a mathematical model of how each manipulated variable
   (MV) affects each controlled variable (CV). If increasing reflux by 1% raises
   overhead purity by 0.3% and drops the bottoms temperature by 2 degrees, the
   controller knows this.

2. **Predicts the future.** Using the model and the current measurements, it predicts
   what every CV will do over the next N sample periods (the "prediction horizon").

3. **Optimizes the moves.** It calculates the best set of MV adjustments (moves) over
   the next M sample periods (the "control horizon") that minimize a cost function
   subject to constraints.

4. **Handles constraints explicitly.** Unlike PID, which only knows about setpoints,
   MPC directly enforces constraints on MVs (valve limits, rate limits) and CVs
   (safety limits, operating limits).

5. **Applies only the first move.** After computing the optimal sequence, the
   controller applies only the first move, then re-measures and re-optimizes at the
   next sample. This "receding horizon" approach provides feedback.

### 1.3 The Economic Benefit of APC

The real value of APC is not just better regulation -- it is **pushing the process
to its constraints** to maximize profit.

Consider a crude oil furnace. Without APC, the operator sets the outlet temperature
conservatively -- say 360 degrees C -- because if a disturbance pushes the temperature
above 375 degrees C, the coking rate increases dramatically. The operator leaves a
safety margin of 15 degrees.

With APC, the controller continuously predicts the temperature trajectory and adjusts
fuel to keep the temperature as close to 375 degrees C as possible without exceeding it.
The controller can operate with a much smaller margin -- perhaps 3 degrees instead of
15 -- because it sees disturbances coming and corrects for them before they cause
problems.

That extra 12 degrees of operating margin translates directly into higher throughput
or better heat recovery. On a large furnace, this can be worth millions of dollars per
year.

The same principle applies everywhere:

- **Distillation columns**: Push product purity closer to the minimum specification.
  Every 0.1% of excess purity is wasted energy in the reboiler.

- **Reactors**: Maximize conversion by operating closer to temperature and pressure
  constraints. Higher conversion means more product from the same feedstock.

- **Compressors**: Operate closer to the surge line to maximize throughput. The APC
  controller can predict surge and back off before it happens, whereas the
  anti-surge controller (a PID) must leave a large margin.

- **Boilers**: Minimize excess air while staying above the minimum for complete
  combustion. Less excess air means less heat going up the stack.

Industry studies consistently show APC benefits of 3-6% on energy costs and 2-4%
on throughput. For a unit processing 50,000 barrels per day, even 1% improvement
can be worth several million dollars annually.

### 1.4 Real-World APC Applications

#### Distillation Column Control

A typical distillation APC application has:

| Variable Type | Examples |
|---|---|
| **MVs** | Reflux flow, reboiler duty, overhead pressure setpoint, sidestream flow |
| **CVs** | Overhead composition, bottoms composition, tray temperatures, column differential pressure |
| **DVs** | Feed rate, feed composition, ambient temperature |

The controller adjusts all MVs simultaneously to maintain product specifications
(CV constraints) while minimizing energy (reboiler duty cost function). When feed
composition changes, it predicts the effect on products and adjusts before the
specifications are violated.

#### Reactor Temperature Control

A chemical reactor (e.g., a CSTR -- continuously stirred tank reactor) is a classic
multivariable problem:

| Variable Type | Examples |
|---|---|
| **MVs** | Coolant flow, feed rate, catalyst addition rate |
| **CVs** | Reactor temperature, product concentration, level |
| **DVs** | Feed temperature, feed concentration, coolant supply temperature |

The reaction is often exothermic -- it generates heat. If the temperature rises, the
reaction rate increases, which generates more heat, which raises the temperature
further. This positive feedback (called a "runaway" or "parametric sensitivity")
makes the system nonlinear and challenging for PID. An MPC controller with a good
model can control reactor temperature tightly while maximizing conversion.

#### Fired Heater / Furnace Control

Fired heaters are found in every refinery. The APC application typically includes:

| Variable Type | Examples |
|---|---|
| **MVs** | Fuel gas flow, air damper position, pass balancing valves |
| **CVs** | Coil outlet temperature (COT), tube metal temperatures, stack O2, draft pressure |
| **DVs** | Feed rate, feed inlet temperature, ambient temperature, fuel gas composition |

The controller maximizes COT (more heat recovery) while respecting tube metal
temperature limits (metallurgical constraint), minimum stack O2 (combustion
efficiency), and maximum draft (structural limit). This is a textbook example of
"pushing to constraints" for economic benefit.

#### Compressor Control

Centrifugal compressors must avoid surge (a flow reversal that damages the machine).
Traditional anti-surge control uses a PID controller on a surge margin variable with
a large safety margin. APC can:

| Variable Type | Examples |
|---|---|
| **MVs** | Speed (or guide vanes), recycle valve, suction throttle |
| **CVs** | Discharge pressure, surge margin, power consumption |
| **DVs** | Suction pressure, suction temperature, gas molecular weight |

The MPC controller operates the compressor closer to surge by predicting the surge
margin trajectory and adjusting proactively. This enables higher throughput without
risking machine damage.

---

## 2. Model Predictive Control (MPC) Theory

### 2.1 The Basic Idea

MPC is conceptually simple:

1. At each sample time k, measure all CVs and note the current MV positions.
2. Using a model, predict the future CV trajectories over the next P samples.
3. Find the sequence of MV moves over the next M samples that minimizes a cost
   function (typically: tracking error + move size) subject to constraints.
4. Apply only the first move: du(k).
5. Wait one sample period, measure again, and repeat from step 1.

This is called the **receding horizon** strategy. Even though the optimization
computes M moves into the future, only the first one is applied. At the next sample,
the controller re-measures (getting feedback about model errors and disturbances)
and re-optimizes. The horizon "recedes" by one step each time.

```
Time:    k     k+1    k+2    k+3    ...    k+M    ...    k+P
         |------ control horizon M ------|
         |--------------- prediction horizon P ------------------|

         Apply  Computed but    Zero moves assumed
         du(k)  du(k+1)...     beyond control horizon
                du(k+M-1)
```

The key insight is that MPC converts a control problem into a repeated optimization
problem. At each step, you solve:

```
Choose du(k), du(k+1), ..., du(k+M-1)
to minimize some cost
subject to constraints on MVs and CVs
```

The cost function and constraints are what differentiate MPC from other approaches.

### 2.2 Dynamic Matrix Control (DMC) -- The Step Response Approach

The most common industrial MPC formulation uses **step response models** (also called
finite impulse response, or FIR, models). This is the approach used in systems like
AspenTech DMC3, Honeywell RMPCT, and Yokogawa SMOC.

#### What is a Step Response?

A step response is the simplest possible dynamic model. It answers the question:
"If I make a unit step change in MV_j at time 0, what happens to CV_i over time?"

For example, if you step the reflux flow up by 1% on a distillation column, the
overhead composition might respond like this:

```
Time (min):  0    5   10   15   20   25   30   ...  120
Response:    0  0.02 0.08 0.18 0.30 0.38 0.42  ...  0.50
```

These values -- call them S(1), S(2), ..., S(N) -- are the **step response
coefficients**. They capture the complete dynamic relationship between that MV-CV
pair: the gain, the time constant, the dead time, and any inverse response or
overshoot.

For a system with n_u MVs and n_y CVs, you need n_y x n_u step responses, each of
length N. This gives you a three-dimensional array:

```
S[i, k, j] = response of CV_i at time step k to a unit step in MV_j
```

where:
- i = 1, ..., n_y  (CV index)
- k = 1, ..., N    (time step, N is the model horizon)
- j = 1, ..., n_u  (MV index)

The **steady-state gain** is the final value: G(i,j) = S(i, N, j).

#### The Superposition Principle

The power of step response models comes from the **superposition principle** for
linear systems. If the system is linear (or approximately linear around the current
operating point), the effect of multiple step changes at different times is the sum
of the individual responses.

If MV_j makes moves du_j(k), du_j(k-1), du_j(k-2), ..., then the predicted output
for CV_i at a future time step k+p is:

```
y_pred_i(k+p) = y_free_i(k+p) + sum over j [ sum over m=0 to M-1 [ S_ij(p-m) * du_j(k+m) ] ]
```

where y_free is the "free response" -- what the CV would do if no future moves were
made, based on the effect of past moves still propagating through the system.

#### The Dynamic Matrix

The relationship between future moves and predicted outputs can be written in matrix
form. For a single MV-CV pair:

```
[ y_pred(k+1) ]   [ y_free(k+1) ]   [ S(1)   0      0    ... 0    ] [ du(k)   ]
[ y_pred(k+2) ] = [ y_free(k+2) ] + [ S(2)   S(1)   0    ... 0    ] [ du(k+1) ]
[ y_pred(k+3) ]   [ y_free(k+3) ]   [ S(3)   S(2)   S(1) ... 0    ] [ du(k+2) ]
[   ...        ]   [   ...        ]   [  ...    ...   ...  ...  ... ] [  ...     ]
[ y_pred(k+P) ]   [ y_free(k+P) ]   [ S(P)   S(P-1) S(P-2).. S(P-M+1) ] [ du(k+M-1)]
```

In compact notation:

```
y_pred = y_free + A_dyn * du
```

The matrix A_dyn is called the **dynamic matrix**. It is a lower-triangular block
Toeplitz matrix -- "lower-triangular" because future outputs cannot depend on moves
that have not happened yet (causality), and "Toeplitz" because the same step response
coefficients appear on each diagonal (time-invariance).

For MIMO systems with n_y CVs and n_u MVs, A_dyn has block structure:

```
A_dyn is (n_y * P) x (n_u * M) with blocks A_dyn[i,j] being the P x M
Toeplitz matrix from the step response S[i, :, j].
```

#### Where Do Step Responses Come From?

Step response coefficients can be obtained in two ways:

1. **From plant tests** (identification): You make a step change on the real process,
   record the CV responses, and extract the step response coefficients. This is what
   the Azeotrope Ident application does. The result is stored in the `.apcmodel` file.

2. **From a state-space model** (conversion): If you have a state-space model
   (A, B, C, D matrices), you can compute the step response by simulating the model.
   The step response at time step k is:

   ```
   S(k) = C * (A^0 + A^1 + A^2 + ... + A^(k-1)) * B + D
        = C * (sum_{i=0}^{k-1} A^i) * B + D
   ```

   In Azeotrope APC, this conversion is implemented in
   `StepResponseModel::fromStateSpace()`.

### 2.3 State-Space MPC

An alternative to the step response (FIR) approach is to use a **state-space model**
directly in the MPC formulation:

```
x(k+1) = A * x(k) + B * u(k)
y(k)   = C * x(k) + D * u(k)
```

where:
- x(k) is the state vector (dimension n_x)
- u(k) is the input (MV) vector (dimension n_u)
- y(k) is the output (CV) vector (dimension n_y)
- A, B, C, D are the system matrices

State-space MPC has some advantages:

- **Compact representation**: An n_x-state model is described by four matrices, whereas
  a step response model requires n_y * N * n_u coefficients. For large systems, the
  state-space representation is much more compact.

- **State estimation**: A Kalman filter can estimate the internal states, which gives
  a better prediction than simple output bias correction.

- **Nonlinear extension**: State-space models extend naturally to nonlinear MPC
  (NMPC) where the model is x(k+1) = f(x(k), u(k)).

The disadvantage is that state-space models are harder to obtain from plant data
(requiring subspace identification methods like N4SID) and harder to validate
visually (you cannot simply overlay predicted vs. actual step responses).

**Azeotrope APC uses state-space as its primary internal representation.** When the
Layer 1 QP needs step response coefficients for the dynamic matrix, they are
generated from the state-space model. This gives the best of both worlds: compact
storage, state estimation capability, and nonlinear extension, while still using
the proven DMC-style QP formulation for the real-time controller.

### 2.4 The QP Optimization

At each sample time, the MPC controller solves a **Quadratic Program** (QP). This
is the mathematical heart of MPC.

#### Decision Variables

The decision variables are the future MV moves:

```
du = [ du(k), du(k+1), ..., du(k+M-1) ]^T
```

This is a vector of dimension n_u * M (number of MVs times the control horizon).

#### Cost Function

The standard MPC cost function has two terms:

```
J = || y_pred - y_target ||^2_Q  +  || du ||^2_R
```

Expanded, this is:

```
J = (y_pred - y_target)^T * Q * (y_pred - y_target)  +  du^T * R * du
```

The first term penalizes **tracking error** -- the deviation of the predicted outputs
from their targets. The matrix Q is a diagonal weighting matrix that determines the
relative importance of each CV. Higher weight = tighter control.

The second term penalizes **move size** -- how aggressively the MVs are moved. The
matrix R is a diagonal weighting matrix called the **move suppression** matrix. Higher
weight = smoother, less aggressive control.

Substituting the prediction equation y_pred = y_free + A_dyn * du:

```
J = (y_free + A_dyn * du - y_target)^T * Q * (y_free + A_dyn * du - y_target) + du^T * R * du
```

Let e = y_free - y_target (the predicted error with no future moves). Then:

```
J = (e + A_dyn * du)^T * Q * (e + A_dyn * du) + du^T * R * du
```

Expanding:

```
J = e^T * Q * e
  + 2 * e^T * Q * A_dyn * du
  + du^T * (A_dyn^T * Q * A_dyn + R) * du
```

The first term is constant (does not depend on du) and can be dropped from the
optimization. The remaining terms form a standard QP:

```
minimize    (1/2) * du^T * H * du + f^T * du

where:
    H = 2 * (A_dyn^T * Q * A_dyn + R)       (Hessian, positive definite)
    f = 2 * A_dyn^T * Q * e                  (gradient)
```

Since H is always positive definite (R > 0 ensures this), the QP has a unique global
minimum. This is a **convex optimization problem**, which means:

- It can be solved efficiently (typically in milliseconds).
- The solution is guaranteed to be the global optimum.
- Well-established solvers exist (OSQP, qpOASES, Gurobi).

#### Constraints

The QP includes constraints that reflect physical limitations:

**P1: MV absolute limits** (hard constraints)

These are physical valve limits. A valve cannot go below 0% or above 100%.

```
u_min <= u(k) + C * du <= u_max
```

where C is a cumulative sum matrix that converts incremental moves du to absolute
positions. For a single MV:

```
u(k+m) = u(k) + du(k) + du(k+1) + ... + du(k+m)
```

**P2: MV rate-of-change limits** (hard constraints)

These limit how fast an MV can move in one sample period. A large valve should not
jump from 20% to 80% in one step.

```
du_min <= du <= du_max
```

These are simple box constraints on the decision variables.

**P3: CV safety limits** (soft constraints)

These are alarm or trip limits that should not be violated under normal circumstances,
but may be temporarily violated during severe disturbances.

```
y_safety_lo <= y_pred <= y_safety_hi
```

**P4: CV operating limits** (soft constraints)

These are tighter limits that define the normal operating range.

```
y_operating_lo <= y_pred <= y_operating_hi
```

**P5: CV setpoint tracking** (objective, not constraint)

The setpoint is not a constraint -- it is the target in the cost function. The
controller tries to match the setpoint but will sacrifice tracking accuracy if
needed to satisfy higher-priority constraints.

The distinction between hard and soft constraints is critical. **Soft constraints**
can be violated if the QP would otherwise be infeasible. The constraint handler adds
slack variables with large penalty weights to allow controlled violation. See
Section 6.4 for details.

In matrix form, all constraints are assembled into:

```
l <= A_constraint * du <= u_upper
```

which is the standard form accepted by QP solvers like OSQP.

#### The Full QP

Putting it all together, the Layer 1 QP at each sample time is:

```
minimize    (1/2) * du^T * H * du + f^T * du

subject to: l <= A_constraint * du <= u_upper
```

where:

```
H = 2 * (A_dyn^T * Q * A_dyn + R)

f = 2 * A_dyn^T * Q * (y_free - y_target)

A_constraint = [ I          ]   (rate limits: du_min <= du <= du_max)
               [ C          ]   (MV limits: u_min <= u + C*du <= u_max)
               [ A_dyn      ]   (CV limits: y_min <= y_free + A_dyn*du <= y_max)
```

This QP has:
- n_u * M decision variables
- n_u * M rate constraints + n_u * M absolute MV constraints + n_y * P CV constraints

For a typical industrial application with 5 MVs, M=5, 10 CVs, P=60:
- 25 decision variables
- 25 + 25 + 600 = 650 constraints

This is a small QP by modern standards and can be solved in under 1 millisecond by
OSQP.

### 2.5 Control Horizon vs. Prediction Horizon

Two key design parameters determine the size of the MPC problem:

**Prediction Horizon (P)**

How many sample periods into the future the controller predicts. This should be long
enough to capture the full dynamics of the slowest CV. A rule of thumb: P should be
at least 2-3 times the longest settling time in the system.

For example, if the slowest response takes 60 minutes to settle and the sample time
is 1 minute, then P >= 120 to 180.

A longer prediction horizon gives the controller better foresight but increases the
QP size (more constraint rows) and computation time.

**Control Horizon (M)**

How many future moves the controller computes. After M steps, the MV moves are
assumed to be zero (the MV stays constant). M is always less than or equal to P.

Typical values: M = 3 to 10, regardless of P. This is because the controller only
applies the first move anyway -- the later moves are just there to give the
optimizer enough freedom to find a good first move.

Increasing M:
- Gives the optimizer more degrees of freedom.
- Allows more aggressive control (can make larger corrections spread over more moves).
- Increases the QP size (more decision variables).

Decreasing M:
- Makes control smoother (fewer knobs to turn).
- Reduces computation time.
- May limit the controller's ability to handle tight constraints.

**In practice, M = 3 to 5 works well for most applications.** The controller
performance is much more sensitive to P and the model quality than to M.

### 2.6 Move Suppression (R Weight)

The R matrix (move suppression) is the single most important tuning parameter in MPC.
It controls the trade-off between fast response and smooth control action.

**High R (heavy suppression):**
- MVs move slowly and smoothly.
- CVs take longer to reach their targets.
- The controller is robust to model errors (it does not overreact).
- Good for processes where MV movement is expensive (e.g., large valve actuators,
  compressor speed changes).

**Low R (light suppression):**
- MVs move quickly and aggressively.
- CVs reach their targets faster.
- The controller is more sensitive to model errors (it may oscillate if the model
  is inaccurate).
- Good for processes where fast response is critical (e.g., exothermic reactors,
  safety-related variables).

A useful way to think about R: it is the "cost" of making a move. If moving an MV
is "expensive" (in the optimization sense), the controller will only move it when
there is a significant benefit in CV tracking.

The R matrix is diagonal, with one entry per MV per control horizon step:

```
R = diag(r_1, r_1, ..., r_1, r_2, r_2, ..., r_2, ..., r_nu, ..., r_nu)
         |---- M times ---|  |---- M times ---|       |---- M times ---|
```

where r_j is the move suppression weight for MV_j.

**Initial tuning rule of thumb:** Start with R values that make the MV moves about
1-2% of the MV range per sample time. Adjust based on observed behavior.

### 2.7 CV Weights (Q Matrix)

The Q matrix determines the relative importance of tracking each CV. It is diagonal,
with one entry per CV per prediction horizon step:

```
Q = diag(q_1, q_1, ..., q_1, q_2, q_2, ..., q_2, ..., q_ny, ..., q_ny)
         |---- P times ---|  |---- P times ---|       |---- P times ---|
```

where q_i is the weight for CV_i.

**Higher weight = tighter control.** If CV_1 has weight 10 and CV_2 has weight 1,
the controller will sacrifice CV_2 tracking accuracy by a factor of 10 before it
allows the same deviation on CV_1.

**Practical considerations:**

- **Normalize by engineering range.** If temperature is measured in hundreds of
  degrees and composition in fractions, the raw errors have very different magnitudes.
  Normalize each CV error by its engineering range before applying weights. Azeotrope
  APC does this automatically via the Scaling module.

- **Safety-critical CVs get high weights.** Reactor temperature, pressure -- anything
  that could cause a trip or safety incident.

- **Quality CVs get medium weights.** Product composition, purity -- important for
  product value but not safety-critical.

- **Convenience CVs get low weights.** Levels, pressures that are not quality-related --
  these can float within their operating range.

- **Equal weights are a valid starting point.** If all CVs are equally important after
  normalization, start with equal weights and adjust based on commissioning experience.

---

## 3. The Three-Layer Architecture

Industrial MPC systems use a layered architecture where each layer operates at a
different time scale and solves a different class of optimization problem. Azeotrope
APC implements three layers:

```
+------------------------------------------------------+
|  Layer 3: Nonlinear Optimizer (NLP)                  |
|  Runs: periodically (every 5 min to 1 hour)          |
|  Solver: CasADi + IPOPT                             |
|  Purpose: re-linearize model, update gains            |
+------------------------------------------------------+
         |  updated gain matrix, operating point
         v
+------------------------------------------------------+
|  Layer 2: Steady-State Target (LP/QP)                |
|  Runs: every sample period                           |
|  Solver: HiGHS (LP) or direct KKT (QP)              |
|  Purpose: find optimal steady-state within constraints|
+------------------------------------------------------+
         |  y_target, u_target for each CV and MV
         v
+------------------------------------------------------+
|  Layer 1: Dynamic Controller (QP)                    |
|  Runs: every sample period                           |
|  Solver: OSQP                                        |
|  Purpose: compute MV moves to reach targets          |
+------------------------------------------------------+
         |  du (incremental MV moves)
         v
+------------------------------------------------------+
|  Plant (via OPC UA or DCS interface)                 |
+------------------------------------------------------+
```

### 3.1 Layer 1: Dynamic Controller

Layer 1 is the core MPC engine described in Section 2. It runs every sample period
(typically every 30 seconds to 2 minutes) and computes the actual MV moves that are
sent to the DCS.

#### Step Response Prediction

The prediction equation is:

```
y_pred = y_free + A_dyn * du
```

where:

**y_free** is the **free response** -- what the CVs would do if no future moves are
made. It accounts for:

1. **Past moves still propagating.** If you made a move 5 minutes ago and the process
   has a 20-minute time constant, that move is still affecting the output. The free
   response includes the "tail" of all past moves.

2. **Disturbance estimate.** The difference between what the model predicts and what
   is actually measured is attributed to an unmeasured disturbance. This bias is added
   to the free response prediction. See Section 7.

Computing the free response requires maintaining a history of past MV moves. The
PredictionEngine in Azeotrope APC keeps a rolling window of past moves with length
equal to the model horizon N.

The free response at future time k+p is:

```
y_free(k+p) = sum_{j=1}^{n_u} sum_{m=1}^{past_history}
              [ S_ij(p + m) - S_ij(m) ] * du_j(k - m)   +   d_i(k)
```

where d_i(k) is the estimated disturbance bias on CV_i.

The term S(p+m) - S(m) represents the *incremental* effect of a past move at time
k-m on the output at time k+p, beyond what it has already done by time k.

**A_dyn** is the **dynamic matrix** described in Section 2.2. It encodes the effect
of future moves on future outputs.

**du** is the vector of future MV moves -- the decision variables.

#### Move Calculation

Layer 1 solves the QP described in Section 2.4 and extracts the first move:

```
du*(k) = du[0:n_u]   (first n_u elements of the optimal du vector)
```

This move is applied to the plant. The remaining moves du(k+1), ..., du(k+M-1) are
used for warm-starting the QP at the next sample (shifted by one step).

#### Constraint Handling

Layer 1 enforces all constraints described in Section 2.4 (MV absolute limits, MV
rate limits, CV limits). The ConstraintHandler class in Azeotrope APC builds the
constraint matrices and manages relaxation when the QP is infeasible.

The constraint handling follows a **prioritized relaxation** strategy:

1. First, try to solve with all constraints active.
2. If infeasible, relax the lowest-priority constraints (P5: setpoint tracking is
   always relaxed, as it is in the objective, not constraints).
3. If still infeasible, relax P4 (CV operating limits) by adding slack variables.
4. Continue relaxing up to P3 (CV safety limits) if necessary.
5. P1 (MV hard limits) and P2 (MV rate limits) are never relaxed -- they represent
   physical hardware limitations.

### 3.2 Layer 2: Steady-State Target

Layer 2 answers the question: **"What is the best steady-state operating point?"**

Layer 1 needs targets -- setpoints for each CV and target positions for each MV. In
simple cases, the operator provides these. But in many applications, the optimal
targets depend on economics and current constraints, and should be computed
automatically.

#### Formulation

Layer 2 solves a linear program (LP) or quadratic program (QP):

```
minimize    J_ss = || y_ss - y_sp ||^2_Qs  +  c^T * u_ss
                    \_________________/        \________/
                     setpoint tracking          economic
                                                optimization

subject to:
    y_ss = G * u_ss + d_ss       (steady-state model)
    u_min <= u_ss <= u_max       (MV limits)
    y_min <= y_ss <= y_max       (CV limits, prioritized)
```

where:

- **y_ss** = steady-state CV values (what the CVs will settle to)
- **u_ss** = steady-state MV positions (where the MVs will end up)
- **y_sp** = CV setpoints (operator-specified or from Layer 3)
- **G** = steady-state gain matrix (n_y x n_u), from the model
- **d_ss** = current disturbance estimate (from the disturbance observer)
- **c** = economic cost vector for MVs (e.g., cost of steam, fuel, cooling water)
- **Qs** = CV setpoint tracking weight matrix

#### Economic Optimization

The term c^T * u_ss is what makes Layer 2 powerful. Each MV has an economic cost:

| MV | Cost interpretation |
|---|---|
| Steam to reboiler | Positive cost (minimize energy) |
| Reflux flow | Small positive cost (pumping energy) |
| Product flow rate | Negative cost (maximize throughput) |
| Fuel gas | Positive cost (minimize fuel consumption) |

The LP minimizes the total cost while staying within CV constraints. This is how
APC "pushes to constraints" -- it finds the operating point that satisfies all
specifications at minimum cost.

**Example:** On a distillation column, the LP might find that the optimal operating
point is to run the reboiler at minimum duty while keeping both product
specifications exactly at their lower limits (minimum purity spec). This is the
cheapest way to make on-spec product.

#### Constraint Prioritization (P1-P5)

Layer 2 uses the same priority levels as Layer 1, but applies them to the
steady-state problem:

| Priority | Constraint | Layer 2 Treatment |
|---|---|---|
| P1 | MV hard limits | Always enforced (box constraints on u_ss) |
| P2 | MV rate limits | Not applicable at steady state |
| P3 | CV safety limits | Enforced with large penalty for violation |
| P4 | CV operating limits | Enforced with medium penalty; relaxed if infeasible |
| P5 | CV setpoint tracking | In objective function (Qs term); relaxed freely |

When the LP/QP is infeasible (e.g., conflicting constraints), Layer 2 relaxes
lower-priority constraints first, using slack variables with priority-weighted
penalties.

#### Gain Matrix and Disturbance

The steady-state gain matrix G relates steady-state MV changes to CV changes:

```
G[i,j] = S[i, N, j]   (the final step response coefficient)
```

This is the DC gain of the step response -- the long-term effect of a sustained
unit change in MV_j on CV_i.

The disturbance d_ss captures unmeasured disturbances at steady state:

```
d_ss = y_measured - G * u_current
```

This ensures that the steady-state prediction is consistent with the current
measurements.

#### From Layer 2 to Layer 1

Layer 2 produces:
- **y_target**: the target value for each CV (what Layer 1 should try to reach)
- **u_target**: the target position for each MV (optional; used as a tiebreaker
  when the system is underdetermined)

These targets replace the simple operator setpoints in the Layer 1 cost function:

```
J = || y_pred - y_target ||^2_Q  +  || du ||^2_R
```

If Layer 2 is disabled, y_target equals the operator setpoints and u_target is
not used.

### 3.3 Layer 3: Nonlinear Optimizer

Layer 3 deals with the fundamental limitation of Layers 1 and 2: **they use linear
models.**

Real processes are nonlinear. The gain of a control valve changes with position.
The heat transfer coefficient in a reactor changes with temperature. The relative
volatility in a distillation column changes with composition. A linear model
identified at one operating point becomes less accurate as the process moves away
from that point.

#### What Layer 3 Does

Layer 3 runs periodically (every few minutes to every hour, depending on how fast
the process nonlinearity changes) and performs:

1. **Re-linearization**: Takes a nonlinear model of the process and linearizes it at
   the current operating point. This produces updated A, B, C, D matrices (or
   equivalently, updated step response coefficients and gain matrix G).

2. **Operating point optimization**: Optionally solves a nonlinear optimization to
   find the globally optimal operating point, which becomes the target for Layer 2.

3. **Model update**: Sends the updated linear model to Layers 1 and 2. Layer 2 gets
   a new gain matrix G. Layer 1 gets new step response coefficients (and therefore
   a new dynamic matrix A_dyn).

#### How Linearization Works

Given a nonlinear discrete model:

```
x(k+1) = f(x(k), u(k))
y(k)   = h(x(k), u(k))
```

Linearization at an operating point (x_0, u_0) produces:

```
A = df/dx |_(x_0, u_0)     (Jacobian of f with respect to x)
B = df/du |_(x_0, u_0)     (Jacobian of f with respect to u)
C = dh/dx |_(x_0, u_0)     (Jacobian of h with respect to x)
D = dh/du |_(x_0, u_0)     (Jacobian of h with respect to u)
```

These Jacobians can be computed:

- **Analytically**: If you have the equations, derive the partial derivatives. Tedious
  and error-prone for complex models.

- **Using automatic differentiation (AD)**: CasADi provides this. You define the model
  symbolically and CasADi computes exact Jacobians automatically. This is the
  preferred approach for Layer 3.

- **Numerically**: Using finite differences. Perturb each input, observe the change in
  output, estimate the derivative. Less accurate but works for any model, including
  compiled simulation models. Azeotrope APC uses central finite differences when
  CasADi is not available.

#### CasADi and IPOPT

For the nonlinear optimization, Azeotrope APC uses:

- **CasADi**: A framework for automatic differentiation and optimal control. It
  provides efficient computation of Jacobians and Hessians, which are needed by the
  NLP solver.

- **IPOPT**: An interior-point solver for large-scale nonlinear optimization. It
  finds the optimal operating point subject to nonlinear constraints.

Layer 3 is optional. Many industrial MPC applications run perfectly well with only
Layers 1 and 2, using a fixed linear model. Layer 3 is most valuable when:

- The process operates over a wide range (e.g., different feed rates, different
  product grades).
- The nonlinearity is significant (e.g., chemical reactors, distillation with
  widely varying compositions).
- The economic optimum changes frequently (e.g., varying feed costs, product prices).

### 3.4 How the Three Layers Work Together

Here is the execution sequence at each sample period:

```
1. Read measurements: y_meas(k), u_current(k), dv(k)

2. Disturbance observer update:
   d(k) = alpha * d(k-1) + (1 - alpha) * (y_meas(k) - y_model(k))

3. If Layer 3 interval has elapsed:
   a. Linearize at current operating point: (A, B, C, D)_new
   b. Update step response model
   c. Update Layer 2 gain matrix: G_new
   d. Update Layer 1 dynamic matrix: A_dyn_new

4. Layer 2 (every sample):
   a. Solve LP/QP for optimal steady-state (u_ss*, y_ss*)
   b. Set y_target = y_ss*, u_target = u_ss*

5. Layer 1 (every sample):
   a. Compute free response: y_free
   b. Set up QP: H, f, constraints
   c. Solve QP -> du*
   d. Apply first move: du(k) = du*[0:n_u]

6. Write MV moves to plant:
   u_new(k) = u_current(k) + du(k)

7. Log to storage:
   Record y_meas, u, du, y_pred, solver status, timing, etc.
```

The total execution time for steps 2-7 must be less than the sample period. For a
typical application (5-10 MVs, 10-20 CVs), this takes 5-50 milliseconds -- well
within a 30-second to 2-minute sample period.

---

## 4. The Role of Identification in APC

### 4.1 Why Good Models Matter

The model is the foundation of MPC. Everything the controller does -- predicting
the future, computing optimal moves, enforcing constraints -- depends on the model
being a reasonable representation of the actual process.

**A poor model leads to poor control.** Specifically:

- **Wrong gain**: If the model says a 1% change in reflux changes overhead purity by
  0.5%, but the real gain is 0.3%, the controller will under-correct and leave
  offset, or the disturbance observer will have to work harder, or worst case the
  controller will oscillate.

- **Wrong dynamics**: If the model says the response time is 10 minutes but it is
  actually 30 minutes, the controller will expect the CV to respond faster than it
  does. It will keep making moves, thinking the previous moves are not working,
  leading to oscillation.

- **Wrong dead time**: Dead time (delay) is particularly critical. If the model
  underestimates the dead time, the controller will make moves expecting a response
  that has not started yet, then over-correct when the response finally arrives.
  Dead time errors of more than 20-30% are a common cause of MPC instability.

- **Missing interactions**: If the model does not include an interaction (e.g., the
  effect of reboiler duty on overhead composition), the controller cannot account
  for it. The disturbance observer may partially compensate, but at the cost of
  slower response.

The rule of thumb in APC is: **spend 60% of your project time on identification.**
Get the model right and the controller almost tunes itself. Get the model wrong and
no amount of tuning will save you.

### 4.2 What the Controller Needs from the Model

The controller needs several specific quantities from the model:

#### Step Response Coefficients (FIR)

The dynamic matrix A_dyn is built directly from the step response coefficients. The
controller needs:

```
S[i, k, j]  for  i = 1..n_y,  k = 1..N,  j = 1..n_u
```

This is a 3D array of size n_y x N x n_u. For a 10-CV, 5-MV system with N=120
time steps, this is 6,000 coefficients.

Each step response captures:
- **Gain**: S[i, N, j] -- the final value (steady-state gain)
- **Time constant**: How fast the response reaches steady state
- **Dead time**: How many steps before the response begins
- **Shape**: First-order, second-order, inverse response, integrating, etc.

#### Steady-State Gains

The gain matrix G used by Layer 2:

```
G[i,j] = S[i, N, j]
```

This is the steady-state gain from MV_j to CV_i. Layer 2 uses this to predict the
steady-state effect of MV changes.

#### Dead Times

Dead time (or time delay) for each MV-CV pair. This is the number of sample periods
before the CV begins to respond to a change in the MV.

Dead time information is embedded in the step response (the initial zero-valued
coefficients), but it is also used explicitly for:
- Constraint timing (do not enforce a CV constraint before the MV can affect it)
- Step test design (how long to wait after a step before making another)
- Performance monitoring (detecting model-plant mismatch)

#### State-Space Matrices (for State Estimation)

If the controller uses a Kalman filter for disturbance estimation (rather than a
simple exponential filter), it needs the state-space matrices (A, B, C, D). These
can be obtained from subspace identification methods like N4SID or by fitting a
transfer function and converting to state-space.

### 4.3 Model Quality and Controller Performance

There is a direct relationship between model quality and achievable controller
performance:

| Model Quality | Gain Error | Dynamics Error | Expected MPC Performance |
|---|---|---|---|
| Excellent | < 10% | < 10% of time constant | Near-optimal tracking, tight constraint operation |
| Good | 10-20% | 10-20% of time constant | Good tracking, moderate constraint margin needed |
| Fair | 20-40% | 20-40% of time constant | Adequate tracking with high move suppression, large margins |
| Poor | > 40% | > 40% of time constant | Sluggish or oscillatory, may need to be taken offline |

**Model quality can be quantified** by comparing the model prediction to actual plant
data. The key metrics are:

- **Step response fit**: How well the identified step response matches the actual
  plant step response. Measured as R-squared or normalized mean squared error.

- **Prediction error**: Given a sequence of past MV moves, how well does the model
  predict the CV trajectory? Measured as RMS error relative to the CV range.

- **Cross-validation**: Identify the model on one data set, validate on a different
  data set. This detects overfitting.

### 4.4 When to Re-Identify

Models degrade over time as the process changes. Common causes:

- **Catalyst deactivation**: In reactors, the catalyst activity decreases over time,
  changing the gain from temperature to conversion.

- **Fouling**: Heat exchanger fouling changes heat transfer coefficients, affecting
  gains and time constants.

- **Operating point changes**: If the process moves to a significantly different
  operating point, the linear model may no longer be valid.

- **Equipment changes**: New internals in a distillation column, a rebuilt compressor,
  a new control valve.

- **Feed changes**: Different crude oil, different feedstock composition.

Signs that re-identification is needed:

1. **Increasing disturbance observer corrections.** If the bias estimate keeps growing,
   the model is predicting poorly.

2. **Controller oscillation.** The model gain or dynamics are wrong enough that the
   controller over- or under-corrects.

3. **CV violations.** The controller cannot keep CVs within constraints, despite having
   sufficient MV range.

4. **MV moves not having the expected effect.** Operators notice that the controller's
   moves seem "wrong" -- moving in the right direction but by the wrong amount.

5. **Performance metrics degrading.** Systematic increase in tracking error or
   constraint violations over weeks or months.

---

## 5. From Model to Controller

### 5.1 The Identification-to-Deployment Workflow

Implementing an APC controller is a structured process. Azeotrope APC provides
applications for each step:

```
Step 1: Step Test Design
    |
    v
Step 2: Data Collection (plant tests)
    |
    v
Step 3: Model Identification (Ident App)
    |   Produces: .apcident project
    v
Step 4: Model Validation
    |
    v
Step 5: Controller Configuration (Architect App)
    |   Produces: .apcproj project
    v
Step 6: Simulation Testing
    |
    v
Step 7: Online Deployment (Runtime App)
    |
    v
Step 8: Performance Monitoring
```

#### Step 1: Step Test Design

Before going to the plant, plan the step tests:

- **Which MVs to test**: All MVs that will be in the controller.
- **Step size**: Large enough to produce a measurable response (good signal-to-noise
  ratio) but small enough to stay within operating limits. Typically 5-15% of MV
  range.
- **Step duration**: Long enough for the CV response to reach approximately 63% of
  steady state (one time constant). For a response that takes 30 minutes to settle,
  hold the step for at least 20 minutes.
- **Step direction**: Both up and down steps, to check for nonlinearity. If the
  up-step gain is very different from the down-step gain, the process is nonlinear
  at this operating point.
- **Order of tests**: Test one MV at a time (to separate the effects). Wait for CVs
  to settle between tests. A complete test campaign for a 5-MV system might take
  2-5 shifts.
- **Process conditions**: The process should be at a representative steady state.
  Avoid testing during startups, shutdowns, or major upsets.

#### Step 2: Data Collection

During the plant tests:

- Record all MVs, CVs, and DVs at the controller sample rate or faster.
- Note any disturbances that occur during testing.
- Record the exact times and sizes of each step change.
- Collect data from the DCS historian or a dedicated data collection system.

The data is typically stored as CSV or Excel files with timestamp columns.

#### Step 3: Model Identification (Ident App)

The Azeotrope Ident application (`apc_ident`) provides tools for:

- **Data import**: Load CSV/Excel data, align timestamps, select MVs/CVs/DVs.
- **Preprocessing**: Remove outliers, filter noise, detrend for drift.
- **Step response identification**: Identify the step response coefficients for each
  MV-CV pair. Methods include:
  - Direct step response extraction (from clean step tests)
  - FIR least-squares (from more complex test patterns)
  - ARX model fitting
  - Subspace identification (N4SID) for state-space models
- **Model validation**: Compare model predictions to actual data, compute fit
  statistics.

The output is an `.apcident` project file containing the identified models and all
the test data.

#### Step 4: Model Validation

Before using the model in a controller, validate it:

- **Visual inspection**: Overlay the model prediction on the actual plant data.
  Does the predicted response match the shape, timing, and magnitude of the actual
  response?

- **Cross-validation**: If you have multiple step tests, identify the model on one
  subset and validate on another. A model that fits the identification data but
  fails on validation data is overfit.

- **Physical sanity check**: Do the gains make physical sense? If increasing fuel
  flow should increase temperature, the gain should be positive. If increasing
  reflux should increase overhead purity, is the sign correct?

- **Dead time check**: Does the identified dead time match your process knowledge?
  If you know the transport delay from the valve to the sensor is about 2 minutes,
  the identified dead time should be close to that.

- **Gain matrix check**: For MIMO systems, check the gain matrix for any unexpected
  interactions. If your process knowledge says MV_3 should have no effect on CV_7,
  but the model shows a significant gain, investigate.

#### Step 5: Controller Configuration (Architect App)

The Azeotrope Architect application (`apc_architect`) takes the validated model and
produces a controller configuration:

- **Variable setup**: Define CVs, MVs, DVs with names, tags, units, and engineering
  ranges.
- **Constraint setup**: Set limits for each variable at each priority level (P1-P5).
- **Tuning setup**: Set Q weights (CV importance), R weights (move suppression), and
  horizons (P, M).
- **Economic setup**: Set cost coefficients for MVs (for Layer 2 optimization).
- **Model binding**: Associate the identified model (.apcmodel) with the controller
  configuration.
- **Simulation**: Run closed-loop simulations with the configured controller to
  verify behavior before going to the plant.

The output is an `.apcproj` project file and an `.apcmodel` bundle.

#### Step 6: Simulation Testing

Before deploying to the real plant, test the controller in simulation:

- **Setpoint tracking**: Make setpoint changes and verify the controller tracks them
  smoothly without oscillation.
- **Disturbance rejection**: Introduce disturbances and verify the controller rejects
  them within the expected time.
- **Constraint handling**: Push the controller into situations where constraints are
  active. Verify it respects all limits and relaxes them in the correct priority
  order.
- **Robustness**: Introduce model errors (e.g., multiply all gains by 1.3) and verify
  the controller still performs acceptably.
- **Stress tests**: What happens if a measurement goes bad? What if an MV saturates?
  What if the operator puts a loop in manual?

#### Step 7: Online Deployment (Runtime App)

The Azeotrope Runtime application (`apc_runtime`) deploys the controller to the
real process:

- **Connection**: Connect to the DCS via OPC UA to read measurements and write MV
  outputs.
- **Initialization**: Read current MV positions and CV values. Initialize the
  prediction engine with the current state.
- **Commissioning**: Start in open-loop mode (controller computes moves but does not
  apply them). Compare the controller's recommended moves to what an experienced
  operator would do. If they make sense, switch to closed-loop.
- **Ramp-up**: Start with high move suppression (conservative tuning). Gradually
  reduce R as confidence in the model grows.

#### Step 8: Performance Monitoring

After deployment, monitor the controller continuously:

- Track key performance indicators (see Section 8).
- Watch for signs of model degradation.
- Adjust tuning as needed.
- Re-identify the model when performance degrades.

### 5.2 What the .apcmodel Bundle Contains

The `.apcmodel` file is a bundle (HDF5 format) that contains everything needed
to build the controller:

| Content | Format | Description |
|---|---|---|
| Step response coefficients | float64[n_y, N, n_u] | Full step response matrix |
| Steady-state gain matrix | float64[n_y, n_u] | G = S[:, N, :] |
| CV names | string[n_y] | Names for each controlled variable |
| MV names | string[n_u] | Names for each manipulated variable |
| DV names | string[n_d] | Names for each disturbance variable |
| Sample time | float64 | Controller sample period in seconds |
| Model horizon | int | N -- number of step response coefficients |
| Dead times | int[n_y, n_u] | Dead time in samples for each pair |
| State-space matrices | float64 (optional) | A, B, C, D if available |
| Identification metadata | JSON | Date, method, data source, fit statistics |

The Architect application reads this bundle and uses it to configure the controller.
The Runtime application loads it at startup to initialize the prediction engine.

---

## 6. Tuning an MPC Controller

### 6.1 Move Suppression: The Most Important Tuning Knob

Move suppression (the R weight) is the primary tuning parameter for MPC. It controls
the trade-off between speed and robustness.

**Starting point:** A useful heuristic for the initial R value is:

```
r_j = (typical_CV_error / typical_MV_move)^2 * scale_factor
```

where:
- typical_CV_error is the expected CV deviation in engineering units
- typical_MV_move is the expected MV move size
- scale_factor is 0.1 to 10, depending on desired aggressiveness

Alternatively, start with R values that produce first-move sizes of about 1-2% of the
MV range, then adjust.

**Diagnosing tuning problems:**

| Symptom | Likely Cause | Fix |
|---|---|---|
| CVs oscillate around setpoint | R too low (too aggressive) | Increase R by 2-5x |
| CVs respond too slowly | R too high (too sluggish) | Decrease R by 2-5x |
| MVs "chatter" (small rapid moves) | R too low, or noise in CVs | Increase R; filter CV inputs |
| One MV moves excessively, others idle | R_j too low relative to others | Increase R for the active MV |
| Controller oscillates after a disturbance | Model error + low R | Increase R; check model |

**A well-tuned controller** shows smooth, monotonic MV movements that gradually bring
CVs to their targets without overshoot. The MV moves should be "decisive" -- large
enough to matter but not so large that they cause problems downstream.

### 6.2 CV Weights: Prioritizing Outputs

The Q weight determines how tightly each CV is controlled. In practice, you rarely
tune Q weights in isolation -- you tune the ratio of Q to R.

**Practical approach:**

1. Start with all Q weights equal (after normalization by engineering range).
2. Run the controller in simulation.
3. Observe which CVs are not controlled tightly enough. Increase their Q weights.
4. Observe which CVs the controller is "trying too hard" to control. Decrease their
   Q weights.
5. Iterate.

**Common patterns:**

- **Product quality CVs**: High Q weight. These directly affect product value.
- **Safety CVs**: Very high Q weight. These must be controlled tightly.
- **Level CVs**: Low Q weight. Levels are usually buffers and can float within their
  operating range. The controller should use the level as a degree of freedom to
  improve control of other CVs.
- **Pressure CVs**: Low to medium Q weight, unless pressure directly affects product
  quality or is safety-critical.

**Warning:** Do not set any Q weight to zero unless you truly do not care about that
CV at all. A zero-weight CV is completely ignored by the controller, which means it
can drift to any value. If you want a CV to be loosely controlled, use a small weight
(e.g., 0.1 instead of 0).

### 6.3 Constraint Priority Levels

Azeotrope APC uses five constraint priority levels. Understanding these levels is
essential for proper controller configuration.

#### P1: MV Hard Limits (Never Relaxed)

These are physical limits that cannot be violated:

| Example | Low Limit | High Limit |
|---|---|---|
| Control valve position | 0% | 100% |
| Variable speed drive | Minimum speed | Maximum speed |
| Heater firing rate | Pilot light only | Maximum firing |

P1 limits are hardcoded as box constraints on the MV positions. The QP solver will
never produce a solution that violates them. These constraints are always feasible
(the current MV position is always within P1 limits, and making zero moves is always
an option).

#### P2: MV Rate Limits (Never Relaxed)

These limit how fast an MV can change in one sample period:

| Example | Rate Limit |
|---|---|
| Large control valve | 5% per minute |
| Compressor speed | 2% per minute |
| Fuel gas valve | 3% per minute |
| Temperature setpoint cascade | 1 degree per minute |

Rate limits prevent:
- Mechanical stress on actuators.
- Process upsets from sudden changes.
- Exceeding the dynamic capability of downstream equipment.

P2 limits are box constraints on du (the move size). Like P1, they are always
feasible (zero moves satisfy all rate constraints).

#### P3: CV Safety Limits (Relaxed Only as Last Resort)

Safety limits are "hard" CV limits that should not be violated under normal
operation. Violations may trigger alarms or, in extreme cases, safety system trips.

| Example | Safety Low | Safety High |
|---|---|---|
| Reactor temperature | 250 degC | 400 degC |
| Column differential pressure | 0 kPa | 50 kPa |
| Compressor surge margin | 5% | N/A |

P3 constraints are soft constraints implemented with slack variables and a very large
penalty weight. The controller will violate other constraints and accept poor setpoint
tracking before it will violate P3 limits. But if the situation is truly infeasible
(e.g., a massive disturbance with all MVs saturated), the slack variables allow the
QP to remain feasible while signaling that safety limits are being violated.

#### P4: CV Operating Limits (Relaxed When Needed)

Operating limits define the normal operating envelope:

| Example | Operating Low | Operating High |
|---|---|---|
| Reactor temperature | 330 degC | 370 degC |
| Product purity | 99.5% | N/A |
| Column pressure | 150 kPa | 180 kPa |

P4 limits are narrower than P3 limits and represent the "comfortable" operating range.
The controller tries to stay within P4 limits but will violate them if necessary to
satisfy higher-priority constraints or if the system is temporarily infeasible at P4.

P4 limits are where economic optimization happens. Layer 2 pushes the operating point
to the most profitable P4 boundary. For example, if minimizing energy means running
product purity at the minimum spec of 99.5%, Layer 2 will set the target at 99.5%.

#### P5: CV Setpoint Tracking (Always in the Objective)

Setpoint tracking is not a constraint -- it is part of the cost function. The
controller tries to bring CVs to their setpoints (or the targets computed by Layer 2)
but will sacrifice tracking to satisfy constraints.

The setpoint is the "ideal" operating point for each CV. When no constraints are
active, the controller drives all CVs to their setpoints. When constraints conflict,
the Q weights determine which CVs are tracked more tightly.

### 6.4 Infeasibility Handling

When the QP is infeasible -- meaning no set of MV moves can satisfy all constraints
simultaneously -- the controller must handle the situation gracefully.

Infeasibility can occur when:

- A large disturbance pushes CVs beyond what the MVs can correct.
- An MV reaches its limit (valve fully open or closed).
- Constraint limits conflict with each other (the feasible region is empty).
- The model is inaccurate and predicts constraint violations that will not actually
  occur.

Azeotrope APC handles infeasibility by **prioritized constraint relaxation**:

1. Start with all constraints active.
2. Solve the QP.
3. If infeasible, relax P4 constraints (add slack variables with penalty).
4. Re-solve.
5. If still infeasible, relax P3 constraints.
6. Re-solve.
7. P1 and P2 are never relaxed.

The slack variables are penalized in the cost function with weights that decrease
with priority:

```
J = original_cost + w_P3 * ||s_P3||^2 + w_P4 * ||s_P4||^2
```

where w_P3 >> w_P4, so P3 constraints are only violated when P4 relaxation alone
is not enough.

### 6.5 The Bias Update and Why It Matters

The bias update (disturbance observer) is what gives MPC its feedback mechanism.
Without it, MPC would be pure feedforward -- predicting the future based on the model
alone, with no correction for reality.

At each sample, the controller compares what the model predicted with what actually
happened:

```
bias(k) = y_measured(k) - y_model(k)
```

This difference is attributed to an "unmeasured disturbance" and is added to all
future predictions:

```
y_pred(k+p) = y_model(k+p) + bias(k)     for all p = 1, ..., P
```

This ensures **offset-free control**: even if the model has a gain error or there is
a persistent disturbance, the bias correction drives the steady-state error to zero.

The bias update is filtered (not used raw) to avoid amplifying measurement noise:

```
bias(k) = alpha * bias(k-1) + (1 - alpha) * (y_measured(k) - y_model(k))
```

where alpha is the filter coefficient (typically 0.5 to 0.9). Higher alpha = slower
but smoother bias updates. Lower alpha = faster but noisier.

**Tuning the bias filter:**

| Situation | Recommended alpha |
|---|---|
| Low noise, frequent disturbances | 0.3 to 0.5 (fast response) |
| High noise, infrequent disturbances | 0.8 to 0.95 (heavy filtering) |
| Default starting point | 0.7 |

If the bias is changing rapidly, the model is struggling. Either the model needs
updating or there is an unmeasured disturbance that should be included as a DV.

---

## 7. Disturbance Handling

### 7.1 Output Bias Estimation

The simplest disturbance model assumes that all model-plant mismatch can be
represented as a constant additive bias on each CV output. This is the approach
described in Section 6.5:

```
y_true(k) = y_model(k) + d(k)
```

where d(k) is the bias (disturbance) estimated by the disturbance observer.

**Exponential filter approach:**

```
d(k) = alpha * d(k-1) + (1 - alpha) * (y_measured(k) - y_model_pred(k))
```

This is a first-order exponential filter on the prediction error. It converges to
the true disturbance if the disturbance is constant or slowly varying. The parameter
alpha controls the convergence speed.

Physical interpretation: the disturbance observer is asking "what constant value do
I need to add to my prediction to match reality?" and updating that estimate
gradually.

**Kalman filter approach:**

A more sophisticated approach models the disturbance as a random walk:

```
d(k+1) = d(k) + w(k),     w(k) ~ N(0, Q_d)
y(k)   = C * x(k) + d(k) + v(k),   v(k) ~ N(0, R_v)
```

The Kalman filter jointly estimates the state x(k) and the disturbance d(k). This
approach is optimal in the minimum-variance sense when the noise statistics are
known, and it naturally handles MIMO interactions in the disturbance estimation.

Azeotrope APC supports both approaches:
- Exponential filter (default): simpler, fewer parameters, works well in practice.
- Kalman filter: better for MIMO systems with correlated disturbances.

### 7.2 Measured Disturbances (DVs / Feedforward)

Some disturbances can be measured. Examples:

| Disturbance | Measurement |
|---|---|
| Feed rate change | Flow meter on feed line |
| Feed temperature change | Thermocouple on feed |
| Ambient temperature | Weather station |
| Upstream unit upset | Composition analyzer on feed |
| Fuel gas composition | Calorimeter |

When a disturbance is measured, the controller can compensate for it **before** it
affects the CVs. This is **feedforward control** -- the MPC version.

In the step response framework, DVs are treated like additional MVs that the
controller cannot adjust but can use for prediction:

```
y_pred(k+p) = y_free(k+p) + A_dyn_u * du + A_dyn_d * dd
```

where:
- A_dyn_u is the dynamic matrix for MVs (the controller can optimize over du)
- A_dyn_d is the dynamic matrix for DVs (dd is measured, not optimized)

The DV step responses are identified in the same way as MV step responses: make
a step change in the DV (or observe a natural step) and record the CV responses.

**Feedforward is extremely valuable** when:
- The DV has a large effect on the CVs.
- The DV changes frequently and unpredictably.
- The DV can be measured before it affects the CVs (transport delay provides advance
  warning).

Example: Feed rate changes to a distillation column. If the feed flow meter shows
a 10% increase, the MPC controller can immediately increase reboiler duty (knowing
from the model that a 10% feed increase requires approximately 8% more reboiler
duty), rather than waiting for the temperature to drop and then correcting.

### 7.3 Unmeasured Disturbances (Feedback Correction)

Most disturbances in a real plant are unmeasured. You do not know the exact ambient
temperature at every point, the exact heat transfer coefficient in every exchanger,
or the exact catalyst activity in the reactor.

Unmeasured disturbances are handled through the **feedback mechanism**:

1. The disturbance affects a CV.
2. The CV measurement changes.
3. The disturbance observer detects the difference between prediction and measurement.
4. The bias is updated.
5. The updated bias is included in the free response prediction.
6. Layer 1 computes corrective MV moves.

The speed of this correction depends on:
- The disturbance observer filter constant (alpha).
- The model quality (accurate models mean smaller bias corrections).
- The controller tuning (Q and R weights).
- The process dynamics (slow processes take longer to correct).

Unmeasured disturbance rejection is inherently slower than feedforward because the
controller must wait for the disturbance to affect the measurements before it can
act.

### 7.4 Integrating Disturbance Models for Offset-Free Control

A subtle but important point: for MPC to achieve **offset-free tracking** (zero
steady-state error), the disturbance model must have the same dimension as the
number of controlled outputs.

The standard output bias model (one disturbance per CV) satisfies this requirement.
Each CV has its own bias estimate that is adjusted to eliminate the steady-state
prediction error.

For state-space MPC with a Kalman filter, the disturbance model is typically an
**integrating disturbance** (random walk) appended to the plant model:

```
Augmented state:  x_aug = [x; d]

Augmented model:
    [x(k+1)]   [A  0] [x(k)]   [B]
    [d(k+1)] = [0  I] [d(k)] + [0] * u(k)

    y(k)     = [C  I] * x_aug(k)
```

The identity block in the A_aug matrix makes the disturbance an integrator (it holds
its value unless perturbed). The [C I] output equation means the disturbance adds
directly to the output.

The Kalman filter estimates both x(k) and d(k), and the estimated d(k) is included
in the prediction. Because the disturbance model is integrating, the estimator
drives the steady-state prediction error to zero, guaranteeing offset-free control.

This is mathematically equivalent to the exponential filter with alpha approaching
1.0, but the Kalman filter provides optimal filtering and handles MIMO coupling.

---

## 8. Performance Monitoring

### 8.1 Key Performance Indicators for APC

Once the controller is deployed, ongoing monitoring ensures it continues to deliver
value. The following KPIs should be tracked:

#### MV Utilization

**What it measures:** How much of the available MV range is being used.

```
MV_utilization_j = (u_max_j - u_min_j_used) / (u_max_j - u_min_j) * 100%
```

where u_max_j_used and u_min_j_used are the maximum and minimum MV positions observed
over a monitoring period.

**What it tells you:**
- High utilization (70-90%): The MV is being used effectively. The controller has
  enough range to handle disturbances and push to constraints.
- Low utilization (< 30%): The MV is barely moving. Either the MV is not needed (the
  process is easy to control), the move suppression is too high, or the MV's model
  is inaccurate (the controller does not trust it).
- 100% utilization: The MV is hitting its limits frequently. This may indicate that
  the controller needs more MV range or that the constraints are too tight.

#### CV Constraint Compliance

**What it measures:** The percentage of time each CV stays within its operating limits.

```
compliance_i = (time_within_limits / total_time) * 100%
```

**Target:** > 95% for P4 limits, > 99.5% for P3 limits.

**What it tells you:**
- High compliance: The controller is keeping the process within bounds. Good.
- Low compliance on one CV: The model for that CV may be inaccurate, the MV range
  may be insufficient, or the limits may be too tight.
- Low compliance on many CVs: The controller may be poorly tuned, the model may need
  updating, or the process conditions may have changed significantly.

#### Economic Benefit Tracking

**What it measures:** The monetary value generated by the APC controller compared to
a base case (typically the pre-APC operation or a period with the controller off).

```
benefit = sum over all CVs and MVs of:
    (value_with_APC - value_without_APC) * economic_coefficient
```

For example:
- If APC reduces reboiler steam by 2 t/hr at $15/t, the benefit is $30/hr.
- If APC increases product purity by 0.1%, and that purity is worth $2/bbl on
  50,000 bbl/day, the benefit is approximately $100/hr.

**The most common method** is to compare the controller-on periods with
controller-off periods (or with a moving baseline), accounting for differences in
feed rate, ambient conditions, and other external factors.

**What it tells you:**
- Positive and stable benefit: The controller is delivering value. Maintain it.
- Declining benefit: The model may be degrading, or operating conditions may have
  changed. Consider re-tuning or re-identification.
- Negative benefit: The controller is performing worse than manual operation.
  Investigate immediately -- this usually indicates a bad model or incorrect
  constraint configuration.

#### Controller Uptime

**What it measures:** The percentage of time the controller is running in automatic
mode (closed-loop).

```
uptime = (time_in_auto / total_time) * 100%
```

**Target:** > 90% for a well-maintained controller.

**What it tells you:**
- High uptime (> 90%): The controller is trusted by operators and engineers.
- Medium uptime (60-90%): The controller is being taken offline periodically. Find
  out why -- is it for maintenance, process transitions, or because operators do not
  trust it?
- Low uptime (< 60%): The controller has serious issues. It may need re-tuning,
  re-identification, or redesign. Every hour offline is lost benefit.

### 8.2 When the Controller is Not Working

#### Model-Plant Mismatch

**Symptoms:**
- Disturbance observer bias is large and growing.
- CVs oscillate or take much longer to settle than the model predicts.
- The controller's predicted trajectories do not match actual behavior.

**Diagnosis:**
1. Collect a period of operating data with varied MV moves.
2. Run the model prediction on this data and compare to actual CV responses.
3. Compute the prediction error. If it exceeds 20-30% of the CV range, the model
   needs updating.

**Fix:**
- If the gain has changed but the dynamics are similar: adjust the gain matrix in
  Layer 2 and the step response scaling.
- If the dynamics have changed significantly: re-identify the model using new
  step test data.
- If the operating point has changed: Layer 3 re-linearization (if available) or
  manual re-identification at the new operating point.

#### Constraint Conflicts

**Symptoms:**
- The QP solver returns infeasible status frequently.
- Slack variables on P4 or P3 constraints are nonzero.
- MVs are at their limits (saturated).

**Diagnosis:**
1. Check which constraints are active (at their limits) and which have slack.
2. Look at the constraint priority levels. Are the right constraints being relaxed?
3. Check if the MV ranges are sufficient to handle the current disturbances.

**Fix:**
- Widen CV operating limits (P4) if they are unnecessarily tight.
- Increase MV ranges if possible (wider valve travel, higher speed range).
- Add MVs to give the controller more degrees of freedom.
- Review priority levels to ensure the most important constraints have the highest
  priority.

#### Bad Measurements

**Symptoms:**
- Sudden spikes or step changes in the disturbance bias.
- Controller makes large, inappropriate moves in response to measurement noise.
- CVs show step changes that do not correspond to any process event.

**Diagnosis:**
1. Check the raw measurement signals for spikes, dropouts, or stuck values.
2. Compare redundant measurements (if available).
3. Check transmitter calibration and wiring.

**Fix:**
- Fix the measurement (calibrate, repair, or replace the transmitter).
- Temporarily exclude the bad CV from the controller (set its Q weight to zero
  or remove it).
- Increase the disturbance observer filter constant (higher alpha) to reduce
  sensitivity to measurement noise.
- Add measurement validation logic (rate-of-change limits on inputs, frozen
  signal detection).

#### Operator Overrides

**Symptoms:**
- MVs suddenly change to values not recommended by the controller.
- Controller output and actual MV position diverge.
- The controller's prediction becomes incorrect because the assumed MV position
  does not match reality.

**Diagnosis:**
1. Check the DCS for operator manual overrides on MVs.
2. Check if any MV has been switched to local manual mode.
3. Check if a downstream controller is rejecting the MPC output.

**Fix:**
- Coordinate with operators. If they are overriding because the controller is
  making bad moves, fix the underlying issue (model, tuning, or constraints).
- If an MV must be in manual temporarily, mark it as "clamped" in the controller
  so it is removed from the optimization.
- Add readback logic: read the actual MV position from the DCS and use that
  (not the controller's commanded position) for prediction.

---

## Appendix A: Mathematical Notation Reference

| Symbol | Meaning |
|---|---|
| n_y | Number of controlled variables (CVs) |
| n_u | Number of manipulated variables (MVs) |
| n_d | Number of disturbance variables (DVs) |
| n_x | Number of states (state-space model) |
| N | Model horizon (number of step response coefficients) |
| P | Prediction horizon |
| M | Control horizon |
| k | Current time step index |
| T_s | Sample time (seconds) |
| y(k) | CV measurement vector at time k, dimension n_y |
| u(k) | MV position vector at time k, dimension n_u |
| du(k) | MV move (increment) at time k: du(k) = u(k) - u(k-1) |
| dv(k) | DV measurement vector at time k, dimension n_d |
| S[i,k,j] | Step response coefficient: response of CV_i at step k to unit step in MV_j |
| G | Steady-state gain matrix, dimension n_y x n_u; G[i,j] = S[i,N,j] |
| A_dyn | Dynamic matrix (Toeplitz), dimension (n_y*P) x (n_u*M) |
| C | Cumulative sum matrix for absolute MV constraints |
| y_free | Free response vector (prediction with zero future moves) |
| y_pred | Predicted output vector: y_pred = y_free + A_dyn * du |
| y_target | Target output vector (from Layer 2 or operator setpoints) |
| y_sp | CV setpoint vector (operator-specified) |
| Q | CV error weight matrix (diagonal, positive semi-definite) |
| R | Move suppression weight matrix (diagonal, positive definite) |
| H | QP Hessian: H = 2*(A_dyn^T * Q * A_dyn + R) |
| f | QP gradient: f = 2*A_dyn^T * Q * (y_free - y_target) |
| d(k) | Disturbance bias estimate at time k |
| alpha | Disturbance observer filter constant (0 < alpha < 1) |
| A, B, C, D | State-space model matrices |
| x(k) | State vector at time k (state-space model) |
| J | Cost function value |
| J_ss | Steady-state cost function (Layer 2) |
| u_ss | Steady-state MV position (Layer 2 target) |
| y_ss | Steady-state CV value (Layer 2 target) |
| c | Economic cost vector for MVs |

## Appendix B: Typical Parameter Ranges

| Parameter | Typical Range | Notes |
|---|---|---|
| Sample time (T_s) | 15 s to 5 min | Faster for reactor control; slower for distillation |
| Model horizon (N) | 30 to 200 steps | Must capture full settling time |
| Prediction horizon (P) | 30 to 200 steps | Usually equals N, or slightly less |
| Control horizon (M) | 3 to 10 steps | Diminishing returns above 5-7 |
| Move suppression (R) | 0.01 to 100 | Depends heavily on scaling |
| CV weight (Q) | 0.1 to 100 | After normalization by engineering range |
| Bias filter (alpha) | 0.3 to 0.95 | Lower = faster adaptation; higher = more filtering |
| Bias filter (Kalman Q_d) | 0.01 to 1.0 | Process noise covariance for random walk |
| Bias filter (Kalman R_v) | 0.1 to 10.0 | Measurement noise covariance |

## Appendix C: Comparison of MPC Formulations

| Feature | DMC (Step Response) | State-Space MPC | Nonlinear MPC |
|---|---|---|---|
| Model type | FIR coefficients | A, B, C, D matrices | x(k+1) = f(x, u) |
| Identification | Step tests + FIR fitting | Subspace (N4SID) | First principles |
| Model size | n_y * N * n_u coefficients | n_x^2 + n_x*n_u + ... | Arbitrary ODEs |
| QP size | (n_u * M) variables | Same | NLP (much larger) |
| State estimation | Output bias only | Kalman filter | EKF or MHE |
| Nonlinearity | Linear only | Linear only | Fully nonlinear |
| Constraint handling | QP constraints | QP constraints | NLP constraints |
| Solver | OSQP, qpOASES | OSQP, qpOASES | IPOPT, CasADi |
| Computation time | < 1 ms (typical) | < 1 ms (typical) | 10 ms to 10 s |
| Industrial adoption | Very high (DMC3, RMPCT) | Growing | Specialized apps |
| Ease of commissioning | High (visual step response validation) | Medium | Low |

## Appendix D: Glossary

| Term | Definition |
|---|---|
| **APC** | Advanced Process Control. Any control strategy beyond PID, typically MPC. |
| **ARX** | AutoRegressive with eXogenous input. A linear model structure: y(k) = a_1*y(k-1) + ... + b_1*u(k-d) + ... |
| **Bias** | The difference between model prediction and measurement, attributed to unmeasured disturbances. |
| **CasADi** | A framework for automatic differentiation and nonlinear optimization. Used in Layer 3. |
| **Control horizon (M)** | The number of future MV moves optimized by the controller. |
| **CV** | Controlled Variable. A process variable that the controller tries to keep at a target or within limits. |
| **DCS** | Distributed Control System. The plant automation system that runs PID loops and interfaces with field instruments. |
| **Dead time** | The time delay between an MV change and the first measurable effect on a CV. Also called transport delay. |
| **DMC** | Dynamic Matrix Control. An MPC formulation that uses step response (FIR) models. Originated at Shell Oil in the 1970s. |
| **DV** | Disturbance Variable. A measured variable that affects CVs but is not controlled by the MPC. Used for feedforward. |
| **Dynamic matrix (A_dyn)** | The lower-triangular block Toeplitz matrix that relates future MV moves to predicted CV changes. |
| **EKF** | Extended Kalman Filter. A Kalman filter for nonlinear systems, using linearization at each step. |
| **Engineering range** | The normal operating range of a variable, used for normalization. E.g., [200, 500] degC. |
| **Feedforward** | Using a measured disturbance to compute a corrective action before the disturbance affects the CVs. |
| **FIR** | Finite Impulse Response. A model represented by a sequence of step response coefficients. |
| **Free response** | The predicted CV trajectory with no future MV moves, accounting for past moves and disturbances. |
| **Gain** | The steady-state ratio of CV change to MV change. G = delta_y / delta_u at steady state. |
| **HiGHS** | An open-source solver for linear programming (LP) and quadratic programming (QP). Used in Layer 2. |
| **IPOPT** | Interior Point Optimizer. An open-source solver for nonlinear programming (NLP). Used in Layer 3. |
| **Infeasible** | A QP/LP has no solution that satisfies all constraints simultaneously. |
| **Integrating** | A process whose output keeps changing as long as the input is nonzero (e.g., tank level with flow imbalance). |
| **Kalman filter** | An optimal state estimator for linear systems with Gaussian noise. Used for disturbance estimation. |
| **LP** | Linear Program. An optimization with a linear cost function and linear constraints. |
| **MIMO** | Multiple-Input, Multiple-Output. A system with more than one MV and more than one CV. |
| **Model horizon (N)** | The number of step response coefficients. Must be long enough to capture the full settling time. |
| **Move suppression (R)** | The penalty weight on MV moves in the QP cost function. Higher R = smoother, slower control. |
| **MPC** | Model Predictive Control. A control strategy that uses a model to predict future behavior and optimizes control moves. |
| **MV** | Manipulated Variable. A process variable that the controller can adjust (typically a valve or setpoint). |
| **N4SID** | Numerical algorithms for Subspace State-Space System IDentification. A method for identifying state-space models from data. |
| **NLP** | Nonlinear Program. An optimization with nonlinear cost function and/or constraints. |
| **NMPC** | Nonlinear Model Predictive Control. MPC using a nonlinear model. |
| **Offset-free** | A controller that achieves zero steady-state error despite model mismatch or persistent disturbances. |
| **OPC UA** | Open Platform Communications Unified Architecture. An industrial communication protocol for reading/writing plant data. |
| **OSQP** | Operator Splitting Quadratic Program. An open-source QP solver used in Layer 1. |
| **Prediction horizon (P)** | The number of future time steps over which the controller predicts CV behavior. |
| **QP** | Quadratic Program. An optimization with a quadratic cost function and linear constraints. |
| **Receding horizon** | The MPC strategy of solving over a future horizon, applying only the first move, then shifting the horizon forward. |
| **Relaxation** | Allowing a constraint to be violated (by adding a slack variable with a penalty) when the problem is otherwise infeasible. |
| **RTO** | Real-Time Optimization. The economic optimization layer (Layer 3) that runs periodically. |
| **Sample time (T_s)** | The time interval between consecutive controller executions. |
| **SISO** | Single-Input, Single-Output. A system with one MV and one CV. |
| **Slack variable** | An auxiliary variable added to a constraint to allow controlled violation. Penalized in the cost function. |
| **State-space** | A model representation using matrices A, B, C, D: x(k+1) = Ax + Bu; y = Cx + Du. |
| **Steady-state gain** | The final value of the step response. G[i,j] = S[i, N, j]. |
| **Step response** | The output trajectory of a system in response to a unit step input. |
| **Subspace identification** | A class of methods that identify state-space models directly from input-output data. |
| **Toeplitz matrix** | A matrix with constant values along each diagonal. The dynamic matrix has this structure. |
| **Warm-starting** | Initializing an optimization solver with the solution from the previous sample to speed up convergence. |

---

*This guide is part of the Azeotrope APC documentation. For implementation details,
see the source code in `core/` (C++ engine), `bindings/` (Python bindings), and
`apps/` (applications). For the system architecture proposal, see
`docs/dmc-system-proposal.md`.*
