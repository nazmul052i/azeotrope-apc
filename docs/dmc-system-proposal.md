# Proposal: Open-Source DMC System

**Project:** OpenDMC -- An Open-Source Dynamic Matrix Control Platform  
**Date:** 2026-04-10  
**Context:** Build an industrial-grade MPC/DMC system inspired by AspenTech DMC3, with a C++ optimization core and Python application layer

---

## 1. Vision

Build a modular, open-source Dynamic Matrix Control (DMC) platform that replicates the core functionality of industrial MPC systems like AspenTech DMC3. The system will consist of three main deliverables:

1. **Core Optimization Engine (C++)** -- Three-layer optimizer: NLP (CasADi/IPOPT), LP (steady-state target), QP (dynamic control), plus step response models, prediction engine, constraint handling, and state estimation
2. **Builder Application (Python)** -- Desktop/web tool for model identification, controller configuration, tuning, simulation, and deployment
3. **Runtime Service (Python + C++ core)** -- A long-running service that executes dynamic optimization on deployed controllers in real-time

**Priority: The entire core engine (all three optimization layers) must be completed and validated before building the Builder or Runtime Service.**

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Builder App (Python)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Model ID │ │ MPC      │ │Optimizer │ │  Simulation   │  │
│  │ Module   │ │ Config   │ │ Config   │ │  Environment  │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬───────┘  │
│       └─────────────┴────────────┴───────────────┘          │
│                          │ Deploy                           │
└──────────────────────────┼──────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   Controller Repository                      │
│           config.yaml          (human-readable metadata)     │
│           model.hdf5           (step response matrices)      │
│           rto_solver.so        (codegen'd NLP, optional)     │
└──────────────────────────┬───────────────────────────────────┘
                           │ Load
                           ▼
┌──────────────────────────────────────────────────────────────┐
│               Runtime Service (Python orchestration)         │
│  ┌───────────────────────────────────────────────────────┐   │
│  │            libopendmc (C++ Core Engine)                │   │
│  │                                                       │   │
│  │  Layer 3: NLP (CasADi C++ → IPOPT)                   │   │
│  │    Economic RTO, nonlinear model update               │   │
│  │    Runs: periodic (minutes to hours)                  │   │
│  │              │ updated targets / linearized model      │   │
│  │              ▼                                        │   │
│  │  Layer 2: LP/QP (HiGHS / OSQP)                       │   │
│  │    Steady-state target calculation                    │   │
│  │    Constraint prioritization & relaxation             │   │
│  │    Runs: every sample period                          │   │
│  │              │ SS targets (u_ss, y_ss)                │   │
│  │              ▼                                        │   │
│  │  Layer 1: QP (OSQP / qpOASES)                        │   │
│  │    Dynamic matrix control (step response model)       │   │
│  │    Move calculation, tracking, constraints            │   │
│  │    Runs: every sample period                          │   │
│  │              │ du[k] (optimal moves)                  │   │
│  │              ▼                                        │   │
│  │  Shared: StepResponseModel, PredictionEngine,         │   │
│  │          DisturbanceObserver, ConstraintHandler        │   │
│  └───────────────────────────────────────────────────────┘   │
│                          │                                   │
│  Python: Scheduling, OPC UA, Monitoring, REST API            │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Plant / Simulator                          │
│              (OPC UA Server, DCS, SCADA)                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Repository Structure

```
opendmc/
├── README.md
├── CMakeLists.txt                      # Top-level CMake build
├── pyproject.toml                      # Python package build
├── docs/
│   ├── architecture.md
│   ├── algorithms.md
│   ├── api-reference.md
│   └── tutorials/
│
├── core/                               # ===== C++ CORE ENGINE (libopendmc) =====
│   ├── CMakeLists.txt
│   │
│   ├── include/opendmc/                # Public headers
│   │   ├── opendmc.h                   # Master include
│   │   ├── types.h                     # CV, MV, DV, SolverStatus, etc.
│   │   ├── step_response_model.h       # FIR step response storage & prediction
│   │   ├── dynamic_matrix.h            # Toeplitz matrix construction
│   │   ├── prediction_engine.h         # Free/forced response computation
│   │   ├── disturbance_observer.h      # Output bias estimation
│   │   ├── constraint_handler.h        # Prioritized constraint management
│   │   ├── scaling.h                   # Variable scaling/normalization
│   │   │
│   │   ├── layer1_dynamic_qp.h         # Layer 1: Dynamic QP controller
│   │   ├── layer2_ss_target.h          # Layer 2: Steady-state target LP/QP
│   │   ├── layer3_nlp.h               # Layer 3: Nonlinear optimizer (CasADi)
│   │   │
│   │   ├── dmc_controller.h            # Orchestrates all three layers
│   │   └── config.h                    # Controller configuration struct
│   │
│   ├── src/                            # Implementation
│   │   ├── step_response_model.cpp
│   │   ├── dynamic_matrix.cpp
│   │   ├── prediction_engine.cpp
│   │   ├── disturbance_observer.cpp
│   │   ├── constraint_handler.cpp
│   │   ├── scaling.cpp
│   │   │
│   │   ├── layer1_dynamic_qp.cpp       # OSQP / qpOASES integration
│   │   ├── layer2_ss_target.cpp        # HiGHS / OSQP integration
│   │   ├── layer3_nlp.cpp             # CasADi C++ API + IPOPT
│   │   │
│   │   ├── dmc_controller.cpp          # Full three-layer orchestration
│   │   └── config.cpp                  # Config parsing (YAML + HDF5)
│   │
│   ├── third_party/                    # Vendored or fetched dependencies
│   │   ├── eigen/                      # Matrix library
│   │   ├── osqp/                       # QP solver
│   │   ├── highs/                      # LP solver
│   │   └── yaml-cpp/                   # YAML parsing
│   │
│   └── tests/                          # C++ unit tests (Google Test)
│       ├── test_step_response.cpp
│       ├── test_dynamic_matrix.cpp
│       ├── test_prediction.cpp
│       ├── test_layer1_qp.cpp
│       ├── test_layer2_lp.cpp
│       ├── test_layer3_nlp.cpp
│       ├── test_constraint_handler.cpp
│       ├── test_dmc_controller.cpp     # Full integration tests
│       └── test_data/                  # Test fixtures (HDF5 models, etc.)
│
├── bindings/                           # ===== PYTHON BINDINGS =====
│   ├── CMakeLists.txt
│   ├── pybind_opendmc.cpp              # pybind11 wrapper for libopendmc
│   └── tests/
│       └── test_bindings.py
│
├── python/                             # ===== PYTHON LAYER =====
│   ├── opendmc/
│   │   ├── __init__.py
│   │   │
│   │   ├── identification/             # Model identification (Python, offline)
│   │   │   ├── __init__.py
│   │   │   ├── step_test.py            # Step test design and execution
│   │   │   ├── fir_id.py               # FIR model ID from data (least-squares)
│   │   │   ├── subspace_id.py          # Subspace ID (N4SID, MOESP)
│   │   │   ├── arx_id.py              # ARX model identification
│   │   │   ├── ss_to_step.py           # State-space → step response conversion
│   │   │   └── validation.py           # Model fit metrics, cross-validation
│   │   │
│   │   ├── config/                     # Controller configuration
│   │   │   ├── __init__.py
│   │   │   ├── controller_config.py    # CV/MV/DV definitions, horizons, weights
│   │   │   ├── constraint_config.py    # Bounds, priorities, soft constraint setup
│   │   │   ├── tuning.py               # Tuning parameter management
│   │   │   └── schema.py               # YAML schema validation
│   │   │
│   │   ├── simulation/                 # Offline simulation
│   │   │   ├── __init__.py
│   │   │   ├── closed_loop_sim.py      # Closed-loop sim (calls C++ core)
│   │   │   ├── plant_model.py          # Plant model wrappers
│   │   │   ├── disturbance_gen.py      # Disturbance/noise generators
│   │   │   └── scenario.py             # Scenario management
│   │   │
│   │   ├── connectivity/               # Data I/O
│   │   │   ├── __init__.py
│   │   │   ├── opcua_client.py         # OPC UA read/write
│   │   │   ├── historian.py            # Time-series data interface
│   │   │   └── api.py                  # REST API for external integration
│   │   │
│   │   └── utils/                      # Shared Python utilities
│   │       ├── __init__.py
│   │       ├── plotting.py             # Visualization (matplotlib/plotly)
│   │       └── hdf5_io.py              # HDF5 model read/write
│   │
│   └── tests/
│       ├── test_identification/
│       ├── test_config/
│       ├── test_simulation/
│       └── test_connectivity/
│
├── builder/                            # ===== BUILDER APPLICATION =====
│   ├── __init__.py
│   ├── app.py                          # Main application entry
│   ├── ui/                             # UI layer (Qt / web)
│   └── controllers/                    # UI logic
│
├── service/                            # ===== RUNTIME SERVICE =====
│   ├── __init__.py
│   ├── main.py                         # Service entry point
│   ├── engine.py                       # Control loop (calls C++ core)
│   ├── scheduler.py                    # Execution timing
│   ├── monitor.py                      # Performance metrics
│   └── server.py                       # gRPC / REST API server
│
├── examples/
│   ├── siso_foptd.cpp                  # C++ SISO DMC example
│   ├── mimo_wood_berry.cpp             # C++ MIMO DMC example
│   ├── cstr_three_layer.cpp            # C++ full three-layer example
│   ├── siso_foptd.py                   # Python SISO DMC via bindings
│   ├── cstr_dmc.py                     # Python CSTR DMC example
│   ├── distillation_dmc.py             # Python distillation column
│   └── step_test_example.py            # Model identification workflow
│
└── tests/
    └── integration/
        ├── test_siso_closed_loop.py
        ├── test_mimo_closed_loop.py
        └── test_three_layer.py
```

---

## 4. Core Engine: Three-Layer Optimizer (C++)

The core engine is a standalone C++ library (`libopendmc`) that implements all three optimization layers. It depends on Eigen, OSQP, HiGHS, and optionally CasADi.

### 4.1 Step Response Model

The foundation of DMC. Stores FIR coefficients and computes predictions.

```
y[k] = sum_{i=1}^{N} S[i] * delta_u[k-i] + d[k]

where:
  S[i]     = step response coefficient at sample i
  delta_u  = input increment (MV move)
  d[k]     = estimated disturbance (bias correction)
  N        = model horizon (truncation length, typically 30-120 steps)
```

**MIMO extension:** For `ny` CVs and `nu` MVs, each (CV_i, MV_j) pair has its own step response vector. Full model: `S[ny][N][nu]`.

```cpp
// core/include/opendmc/step_response_model.h
class StepResponseModel {
public:
    StepResponseModel(int ny, int nu, int model_horizon, double sample_time);

    // Load from HDF5 file
    static StepResponseModel fromHDF5(const std::string& path);

    // Convert state-space (A,B,C,D) to step response
    static StepResponseModel fromStateSpace(
        const Eigen::MatrixXd& A, const Eigen::MatrixXd& B,
        const Eigen::MatrixXd& C, const Eigen::MatrixXd& D,
        int model_horizon, double sample_time);

    // Core predictions
    Eigen::VectorXd predictFree(const Eigen::MatrixXd& past_moves, int P) const;
    Eigen::VectorXd predictForced(const Eigen::VectorXd& future_moves) const;

    // Accessors
    double coefficient(int cv, int step, int mv) const;
    Eigen::MatrixXd steadyStateGain() const;  // G = S[:, N-1, :]
    int ny() const;
    int nu() const;
    int modelHorizon() const;
    double sampleTime() const;

private:
    Eigen::Tensor<double, 3> S_;  // [ny, N, nu]
    double dt_;
};
```

### 4.2 Dynamic Matrix Construction

Builds the lower-triangular Toeplitz prediction matrix from step response coefficients.

```
A_dyn = | S[1]    0      0    ... 0       |    size: (P*ny) x (M*nu)
        | S[2]    S[1]   0    ... 0       |    P = prediction horizon
        | S[3]    S[2]   S[1] ... 0       |    M = control horizon
        | ...     ...    ...  ... ...     |
        | S[P]    S[P-1] ...  ... S[P-M+1]|
```

```cpp
// core/include/opendmc/dynamic_matrix.h
class DynamicMatrix {
public:
    // Build from step response model
    DynamicMatrix(const StepResponseModel& model, int P, int M);

    const Eigen::MatrixXd& matrix() const;          // A_dyn
    const Eigen::SparseMatrix<double>& sparse() const; // Sparse version for QP

    // Cumulative move matrix (for absolute MV constraint: u = u_prev + C * du)
    const Eigen::MatrixXd& cumulativeMatrix() const;

    int predictionHorizon() const;
    int controlHorizon() const;

private:
    Eigen::MatrixXd A_dyn_;
    Eigen::SparseMatrix<double> A_sparse_;
    Eigen::MatrixXd C_cumulative_;
};
```

### 4.3 Prediction Engine

Manages the rolling prediction: free response from past moves, forced response from future moves, disturbance correction.

```cpp
// core/include/opendmc/prediction_engine.h
class PredictionEngine {
public:
    PredictionEngine(const StepResponseModel& model, int P, int M);

    // Update with new measurement and applied move
    void update(const Eigen::VectorXd& y_measured,
                const Eigen::VectorXd& du_applied);

    // Get current free response (prediction with zero future moves)
    Eigen::VectorXd freeResponse() const;

    // Get predicted output for given future moves
    Eigen::VectorXd predict(const Eigen::VectorXd& du_future) const;

    // Reset internal state
    void reset();

private:
    StepResponseModel model_;
    DynamicMatrix dynmat_;
    std::deque<Eigen::VectorXd> past_moves_;  // rolling window of past du
    Eigen::VectorXd y_free_;
};
```

### 4.4 Disturbance Observer

Estimates output bias for offset-free tracking.

```cpp
// core/include/opendmc/disturbance_observer.h
class DisturbanceObserver {
public:
    enum class Method { EXPONENTIAL_FILTER, KALMAN_FILTER };

    DisturbanceObserver(int ny, Method method = Method::EXPONENTIAL_FILTER);

    // Update with prediction error
    Eigen::VectorXd update(const Eigen::VectorXd& y_measured,
                           const Eigen::VectorXd& y_predicted);

    // Current disturbance estimate
    const Eigen::VectorXd& estimate() const;

    // Set filter parameters
    void setFilterGain(double alpha);              // for exponential filter
    void setKalmanTuning(const Eigen::MatrixXd& Q,
                         const Eigen::MatrixXd& R); // for Kalman filter

private:
    Eigen::VectorXd d_;
    double alpha_;
    Method method_;
};
```

### 4.5 Constraint Handler

Implements prioritized constraint relaxation -- the key differentiator of industrial DMC.

```
Priority levels:
  P1 (highest): MV hard limits (valve range)         -- NEVER relaxed
  P2:           MV rate-of-change limits              -- Relaxed only if P1 infeasible
  P3:           CV safety limits                      -- Relaxed after P1-P2
  P4:           CV operating limits                   -- Relaxed after P1-P3
  P5 (lowest):  CV setpoint tracking                  -- Always soft (in objective)
```

```cpp
// core/include/opendmc/constraint_handler.h
struct ConstraintSet {
    Eigen::VectorXd lb;       // lower bound
    Eigen::VectorXd ub;       // upper bound
    int priority;             // 1-5
    bool is_soft;             // allow slack variables
    double slack_penalty;     // penalty weight for violation
};

class ConstraintHandler {
public:
    ConstraintHandler();

    void addMVBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);
    void addMVRateBounds(const Eigen::VectorXd& du_lb, const Eigen::VectorXd& du_ub);
    void addCVSafetyBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);
    void addCVOperatingBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);

    // Build QP constraint matrices respecting priorities
    // If infeasible at priority N, relaxes N+1..5 constraints
    struct QPConstraints {
        Eigen::SparseMatrix<double> A;   // constraint matrix
        Eigen::VectorXd lb;              // lower bounds
        Eigen::VectorXd ub;              // upper bounds
        std::vector<int> relaxed;        // which priorities were relaxed
    };

    QPConstraints buildConstraints(
        const DynamicMatrix& dynmat,
        const Eigen::VectorXd& u_current,
        const Eigen::VectorXd& y_free) const;

    // Check feasibility at each priority level
    FeasibilityReport checkFeasibility() const;
};
```

### 4.6 Layer 1: Dynamic QP Controller

The fast inner loop -- computes optimal MV moves to track steady-state targets.

```
minimize:
    J = || y_pred - y_target ||²_Q  +  || du ||²_R

subject to:
    y_pred = y_free + A_dyn * du              (prediction equation)
    du_min <= du <= du_max                     (move size limits)
    u_min <= u_current + C * du <= u_max      (absolute MV limits)
    y_min <= y_pred <= y_max                   (CV limits, soft via P3/P4)
```

```cpp
// core/include/opendmc/layer1_dynamic_qp.h
struct Layer1Config {
    int prediction_horizon;    // P
    int control_horizon;       // M
    Eigen::VectorXd cv_weights;    // Q diagonal (ny)
    Eigen::VectorXd mv_weights;    // R diagonal (nu)
};

struct Layer1Result {
    Eigen::VectorXd du;               // optimal moves [M*nu]
    Eigen::VectorXd y_predicted;      // predicted CV trajectory [P*ny]
    SolverStatus status;              // optimal / infeasible / time_limit
    double objective;
    double solve_time_ms;
    std::vector<int> relaxed_priorities;
};

class Layer1DynamicQP {
public:
    Layer1DynamicQP(const StepResponseModel& model, const Layer1Config& config);

    Layer1Result solve(
        const Eigen::VectorXd& y_free,        // free response [P*ny]
        const Eigen::VectorXd& y_target,       // from Layer 2 [P*ny] or [ny] broadcast
        const Eigen::VectorXd& u_current,      // current MV values [nu]
        const Eigen::VectorXd& disturbance     // estimated bias [ny]
    );

    // Warm-start from previous solution
    void warmStart(const Eigen::VectorXd& du_prev);

    // Update tuning online
    void updateWeights(const Eigen::VectorXd& Q, const Eigen::VectorXd& R);

private:
    StepResponseModel model_;
    DynamicMatrix dynmat_;
    ConstraintHandler constraints_;
    Layer1Config config_;
    // OSQP workspace (persistent for warm-starting)
    std::unique_ptr<OSQPWorkspace> qp_workspace_;
};
```

### 4.7 Layer 2: Steady-State Target Calculator

Finds the optimal steady-state operating point within constraints. Feeds targets to Layer 1.

```
minimize:
    J_ss = || y_ss - y_sp ||²_Qs  +  c^T * u_ss    (tracking + economics)

subject to:
    y_ss = G * u_ss + d_ss        (steady-state gain model)
    u_min <= u_ss <= u_max         (MV bounds)
    y_min <= y_ss <= y_max         (CV bounds, prioritized soft)
```

```cpp
// core/include/opendmc/layer2_ss_target.h
struct Layer2Config {
    Eigen::VectorXd ss_cv_weights;   // Q_s diagonal (tracking importance)
    Eigen::VectorXd ss_mv_costs;     // c vector (economic costs per MV)
    bool use_lp;                     // true = LP (linear cost), false = QP
};

struct Layer2Result {
    Eigen::VectorXd u_ss;            // optimal steady-state MVs [nu]
    Eigen::VectorXd y_ss;            // predicted steady-state CVs [ny]
    SolverStatus status;
    double objective;
    double solve_time_ms;
    std::vector<int> active_constraints;
    std::vector<int> relaxed_priorities;
};

class Layer2SSTarget {
public:
    Layer2SSTarget(const StepResponseModel& model, const Layer2Config& config);

    Layer2Result solve(
        const Eigen::VectorXd& y_setpoint,    // desired CV setpoints [ny]
        const Eigen::VectorXd& disturbance,   // current disturbance estimate [ny]
        const Eigen::VectorXd& dv_values      // current disturbance variable values
    );

    // Update setpoints online
    void updateSetpoints(const Eigen::VectorXd& y_sp);

    // Update economics online
    void updateCosts(const Eigen::VectorXd& mv_costs);

private:
    Eigen::MatrixXd G_;               // steady-state gain matrix
    ConstraintHandler constraints_;
    Layer2Config config_;
};
```

### 4.8 Layer 3: Nonlinear Optimizer (CasADi/IPOPT)

The slow outer loop -- performs real-time optimization (RTO) or nonlinear MPC when the plant is far from the linear operating region.

```cpp
// core/include/opendmc/layer3_nlp.h
struct Layer3Config {
    std::string model_source;         // "casadi_function" or "codegen_so"
    double execution_interval_sec;    // how often to run (e.g., 3600 = hourly)
    int nlp_max_iter;
    double nlp_tolerance;
};

struct Layer3Result {
    Eigen::VectorXd u_optimal;        // economically optimal MVs
    Eigen::VectorXd y_optimal;        // predicted CVs at optimum
    Eigen::MatrixXd updated_gain;     // re-linearized gain matrix (optional)
    SolverStatus status;
    double objective;
    double solve_time_ms;
};

class Layer3NLP {
public:
    // Option A: Build NLP from CasADi C++ API
    Layer3NLP(const casadi::Function& model,
              const casadi::Function& objective,
              const Layer3Config& config);

    // Option B: Load code-generated solver (no CasADi dependency at runtime)
    Layer3NLP(const std::string& codegen_path, const Layer3Config& config);

    Layer3Result solve(
        const Eigen::VectorXd& x_current,     // current plant state estimate
        const Eigen::VectorXd& u_current,      // current MVs
        const Eigen::VectorXd& parameters      // model parameters
    );

    // Re-linearize the nonlinear model around current operating point
    // Returns updated (A,B,C,D) for Layer 2 gain matrix update
    StateSpaceModel linearizeAt(const Eigen::VectorXd& x_op,
                                const Eigen::VectorXd& u_op);

private:
    casadi::Function solver_;
    Layer3Config config_;
};
```

**CasADi code generation workflow:**

```
Builder (offline):                          Runtime (online):
┌──────────────────────┐                   ┌──────────────────────┐
│ CasADi C++ API       │                   │ Layer3NLP loads      │
│ Define NLP           │  codegen    .so   │ compiled solver      │
│ model + objective    │ ────────→  ─────→ │ No CasADi dependency │
│ Generate C code      │                   │ Fast, deterministic  │
└──────────────────────┘                   └──────────────────────┘
```

### 4.9 DMC Controller: Three-Layer Orchestrator

The main class that ties all three layers together.

```cpp
// core/include/opendmc/dmc_controller.h
struct DMCConfig {
    // Model
    std::string model_path;            // path to model.hdf5
    double sample_time;

    // Layer 1 (Dynamic QP)
    Layer1Config layer1;

    // Layer 2 (SS Target)
    Layer2Config layer2;

    // Layer 3 (NLP) -- optional
    bool enable_layer3;
    Layer3Config layer3;

    // Variables
    std::vector<CVConfig> cvs;
    std::vector<MVConfig> mvs;
    std::vector<DVConfig> dvs;
};

class DMCController {
public:
    DMCController(const DMCConfig& config);

    // Load from YAML config + HDF5 model
    static DMCController fromFiles(const std::string& config_yaml,
                                   const std::string& model_hdf5);

    // ===== MAIN EXECUTION (called every sample period) =====
    struct ControlOutput {
        Eigen::VectorXd du;                // recommended MV moves [nu]
        Eigen::VectorXd u_new;             // new MV values [nu]
        Eigen::VectorXd y_predicted;       // predicted CV trajectory
        Eigen::VectorXd y_ss_target;       // steady-state targets
        Eigen::VectorXd u_ss_target;       // steady-state MV targets
        SolverStatus layer1_status;
        SolverStatus layer2_status;
        double total_solve_time_ms;
        DiagnosticsInfo diagnostics;
    };

    ControlOutput execute(
        const Eigen::VectorXd& y_measured,     // current CV readings
        const Eigen::VectorXd& u_current,      // current MV values
        const Eigen::VectorXd& dv_values        // current DV values
    );

    // ===== LAYER 3 (called periodically, separate thread) =====
    void executeRTO(const Eigen::VectorXd& plant_state);

    // ===== ONLINE CONFIGURATION =====
    void setSetpoints(const Eigen::VectorXd& y_sp);
    void setCVBounds(int cv_idx, double lo, double hi);
    void setMVBounds(int mv_idx, double lo, double hi);
    void setMVRateLimit(int mv_idx, double rate);
    void setWeights(const Eigen::VectorXd& Q, const Eigen::VectorXd& R);
    void enableMV(int mv_idx, bool enabled);
    void enableCV(int cv_idx, bool enabled);
    void setMode(ControllerMode mode);  // MANUAL / AUTO / CASCADE

    // ===== DIAGNOSTICS =====
    ControllerStatus status() const;
    PerformanceMetrics metrics() const;

private:
    StepResponseModel model_;
    PredictionEngine prediction_;
    DisturbanceObserver observer_;
    Layer1DynamicQP layer1_;
    Layer2SSTarget layer2_;
    std::unique_ptr<Layer3NLP> layer3_;  // optional
    DMCConfig config_;
};
```

### 4.10 Variable Scaling

Industrial controllers require proper scaling to handle variables with different engineering units and ranges.

```cpp
// core/include/opendmc/scaling.h
class Scaling {
public:
    // Scale to [0, 1] range based on engineering limits
    static Eigen::VectorXd normalize(const Eigen::VectorXd& raw,
                                      const Eigen::VectorXd& lo,
                                      const Eigen::VectorXd& hi);

    static Eigen::VectorXd denormalize(const Eigen::VectorXd& scaled,
                                        const Eigen::VectorXd& lo,
                                        const Eigen::VectorXd& hi);

    // Scale step response model coefficients
    static StepResponseModel scaleModel(const StepResponseModel& model,
                                         const Eigen::VectorXd& cv_range,
                                         const Eigen::VectorXd& mv_range);
};
```

---

## 5. Data Storage: Hybrid Format

| Data Type | Format | Why |
|-----------|--------|-----|
| Controller config (CV/MV names, tags, limits, tuning) | **YAML** | Human-readable, git-diffable, engineers edit by hand |
| Step response models (large numerical matrices) | **HDF5** | Fast binary I/O, native array support, metadata fields |
| Code-generated NLP solvers | **Compiled .so/.dll** | No CasADi dependency at runtime, maximum speed |
| Runtime state (past moves, estimates) | **In-memory + SQLite** | Fast writes, crash recovery, queryable |
| Service API (Builder <-> RTE) | **Protobuf/gRPC** | Typed schemas, fast serialization |

### Controller Repository Layout

```
controllers/
├── CSTR_DMC/
│   ├── config.yaml           # Human-readable: CV/MV defs, tuning, horizons
│   ├── model.hdf5            # Binary: step response S[ny, N, nu], metadata
│   ├── rto_solver.so         # Optional: code-generated Layer 3 NLP
│   └── state.db              # Runtime: SQLite for crash recovery
│
├── Distillation_01/
│   ├── config.yaml
│   ├── model.hdf5
│   └── ...
```

### HDF5 Model File Structure

```
model.hdf5
├── attrs:
│   ├── sample_time: 60.0
│   ├── model_horizon: 120
│   ├── ny: 4
│   └── nu: 3
├── step_response: float64[4, 120, 3]     # S[ny, N, nu]
├── cv_names: ["Temp", "Conc", "Level", "Pressure"]
├── mv_names: ["CoolantFlow", "FeedRate", "SteamValve"]
├── steady_state_gain: float64[4, 3]       # G = S[:, -1, :]
└── metadata:
    ├── identified_date: "2026-04-10"
    ├── identification_method: "step_test"
    └── plant_operating_point: float64[...]
```

---

## 6. Builder Application (Python)

### 6.1 Model Identification Module

| Method | Input | Output | Use Case |
|--------|-------|--------|----------|
| Plant step test | Raw I/O data from step tests | Step response coefficients | Greenfield commissioning |
| FIR least-squares | Historical I/O data | FIR coefficients | Re-ID from operations data |
| Subspace ID (N4SID) | Historical I/O data | State-space -> step response | Complex MIMO systems |
| From first principles | ODE model (via CasADi linearization) | Linearize -> step response | When physics model exists |
| Manual entry | Gains, time constants, delays | Step response via FOPTD/SOPTD | Simple loops |

### 6.2 MPC Configuration Module

```yaml
# config.yaml
controller:
  name: "CSTR_DMC"
  sample_time: 60
  prediction_horizon: 60
  control_horizon: 5
  model_horizon: 120

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

    - name: "Product_Conc"
      tag: "AI-201.PV"
      units: "mol/L"
      setpoint: 0.88
      hi_limit: 0.95
      lo_limit: 0.75
      priority: 4
      weight: 5.0
      engineering_range: [0, 2]

  manipulated_variables:
    - name: "Coolant_Flow"
      tag: "FV-101.OP"
      units: "%"
      hi_limit: 100.0
      lo_limit: 0.0
      rate_limit: 5.0
      cost: 0.0
      move_suppress: 1.0

  disturbance_variables:
    - name: "Feed_Temp"
      tag: "TI-100.PV"
      units: "degC"

  layer2:
    ss_cv_weights: [10.0, 5.0]
    ss_mv_costs: [0.0]

  layer3:
    enabled: false
    execution_interval: 3600
    model_path: "rto_solver.so"
```

### 6.3 Simulation Module

Calls the C++ `DMCController` via pybind11 for accurate simulation performance.

### 6.4 Deployment Module

1. Validate config completeness and model compatibility
2. Write `config.yaml` + `model.hdf5` to controller repository
3. Optionally compile Layer 3 NLP via CasADi code generation
4. Notify runtime service to load/reload

---

## 7. Runtime Service

### 7.1 Control Loop

```
┌─────────────────────────────────────────────────────────┐
│              Every sample_time:                          │
│                                                          │
│  1. READ plant data (CVs, MVs, DVs via OPC UA)          │
│           │                                              │
│  2. CALL controller.execute(y, u, dv)  ← C++ core       │
│           │  Internally:                                 │
│           │  a. Update disturbance estimate              │
│           │  b. Compute free response                    │
│           │  c. Solve Layer 2 LP/QP (SS target)          │
│           │  d. Solve Layer 1 QP (dynamic moves)         │
│           │                                              │
│  3. APPLY: u_new = u_current + du[0]                     │
│           │                                              │
│  4. WRITE to plant (MV setpoints via OPC UA)             │
│           │                                              │
│  5. LOG diagnostics and performance metrics              │
│                                                          │
│  Periodically (Layer 3, separate thread):                │
│  6. CALL controller.executeRTO(plant_state)              │
│           Updates Layer 2 gain matrix if needed           │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Performance Monitoring

| Metric | Description |
|--------|-------------|
| CV tracking error | RMS deviation from setpoint |
| MV utilization | % of time MVs are at limits |
| Constraint violations | Count and duration |
| Solver status | Optimal / infeasible / time limit |
| Solve time | L1 + L2 execution time per cycle |
| Service factor | % of cycles completed on time |
| Economic benefit | Cost function improvement vs. base case |

---

## 8. Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **C++ core: matrix ops** | Eigen 3.x | Industry standard, header-only, vectorized |
| **C++ core: Layer 1 QP** | OSQP (primary), qpOASES (fallback) | Fast, warm-startable, open-source |
| **C++ core: Layer 2 LP** | HiGHS | Fast open-source LP/MIP solver |
| **C++ core: Layer 3 NLP** | CasADi C++ API + IPOPT | Automatic differentiation, code generation |
| **C++ core: config parsing** | yaml-cpp + HDF5 C++ API | YAML config + binary model data |
| **C++ core: testing** | Google Test | Standard C++ testing framework |
| **C++ build** | CMake | Cross-platform build system |
| **Python bindings** | pybind11 | Seamless C++ <-> Python bridge |
| **Python: identification** | NumPy + SciPy (lstsq, SVD) | Offline, iteration speed matters |
| **Python: connectivity** | asyncua | OPC UA client library |
| **Python: Builder UI** | PySide6 (Qt) or FastAPI + React | Desktop or web (later phase) |
| **Python: Runtime** | asyncio + threading | Service orchestration |
| **Python: API** | FastAPI + gRPC | Service communication |
| **Python: plotting** | Matplotlib / Plotly | Visualization |
| **Python: testing** | pytest | Unit and integration tests |

---

## 9. Relationship to mpc-tools-casadi

| Existing Feature | Reuse In OpenDMC |
|-----------------|------------------|
| `getCasadiFunc()` | Reference for CasADi C++ function construction in Layer 3 |
| `getLinearizedModel()` | Reference for Jacobian-based linearization in Layer 3 |
| `c2d()` | Reference for continuous-to-discrete conversion |
| `DiscreteSimulator` | Reference for plant simulator pattern |
| `nmpc()` | Reference for NLP formulation structure |
| `sstarg()` | Reference for Layer 2 steady-state target formulation |
| `ekf()` | Reference for Kalman filter in disturbance observer |
| `mpcplot()` | Trajectory visualization (reuse directly in Python layer) |
| QP solver integration | Reference for OSQP/qpOASES integration patterns |

**Key difference:** mpc-tools-casadi uses state-space models + CasADi NLP for everything. OpenDMC uses step response models + dedicated QP/LP for Layers 1-2, with CasADi only in Layer 3.

---

## 10. Development Phases -- Core First

**Principle: Complete and validate the entire C++ core engine (all three layers) before building the Builder or Runtime Service.**

### Phase 1: Core Foundation (Weeks 1-3)

**Goal:** Step response model and basic SISO dynamic control.

- [ ] Project scaffold: CMake build, Eigen, Google Test
- [ ] `StepResponseModel` class (store, load HDF5, convert from state-space)
- [ ] `DynamicMatrix` builder (Toeplitz construction, sparse format)
- [ ] `PredictionEngine` (free response, forced response, rolling window)
- [ ] `DisturbanceObserver` (exponential filter)
- [ ] Unit tests for all above
- [ ] **Validation: SISO FOPTD closed-loop** (compare to analytical DMC)

### Phase 2: Layer 1 -- Dynamic QP (Weeks 4-6)

**Goal:** Working Layer 1 QP with constraints.

- [ ] `Layer1DynamicQP` class with OSQP integration
- [ ] MV bounds (absolute + rate-of-change)
- [ ] CV output constraints (soft)
- [ ] QP warm-starting between cycles
- [ ] Online weight / bound updates
- [ ] Unit tests + performance benchmarks
- [ ] **Validation: SISO constrained DMC** (MV saturation, CV limits)
- [ ] **Validation: 2x2 MIMO DMC** (Wood-Berry distillation column)
- [ ] **Validation: 4x4 MIMO DMC** (<10ms solve time target)

### Phase 3: Layer 2 -- Steady-State Target (Weeks 7-9)

**Goal:** Two-layer optimizer (LP/QP + dynamic QP) with constraint prioritization.

- [ ] `Layer2SSTarget` class with HiGHS LP integration
- [ ] Steady-state gain matrix extraction from step response
- [ ] `ConstraintHandler` with 5-level priority system
- [ ] Feasibility detection and sequential constraint relaxation
- [ ] Optional QP mode for quadratic SS objectives
- [ ] Economic cost support (linear MV costs)
- [ ] Unit tests for feasibility/infeasibility scenarios
- [ ] **Validation: Two-layer CSTR control** (setpoint tracking + constraint handling)
- [ ] **Validation: Infeasibility scenarios** (verify correct priority relaxation)

### Phase 4: Layer 3 -- Nonlinear Optimizer (Weeks 10-13)

**Goal:** Full three-layer optimizer with CasADi NLP.

- [ ] `Layer3NLP` class with CasADi C++ API
- [ ] IPOPT integration for NLP solve
- [ ] CasADi code generation workflow (NLP -> C code -> .so)
- [ ] Runtime loading of code-generated solver (no CasADi dependency)
- [ ] Re-linearization: update Layer 2 gain matrix from NLP solution
- [ ] Periodic execution support (separate thread, configurable interval)
- [ ] Unit tests (NLP solve, code generation, gain matrix update)
- [ ] **Validation: CSTR three-layer** (RTO updates SS targets, DMC tracks)
- [ ] **Validation: Nonlinear operating region transition**

### Phase 5: Core Integration & Hardening (Weeks 14-16)

**Goal:** Complete `DMCController` orchestrator, robustness, and performance.

- [ ] `DMCController` class (ties all three layers)
- [ ] `Scaling` module (engineering units normalization)
- [ ] Online configuration API (setpoints, bounds, weights, MV/CV on/off)
- [ ] Controller mode switching (MANUAL / AUTO / CASCADE)
- [ ] YAML config parsing (yaml-cpp)
- [ ] HDF5 model loading (HDF5 C++ API)
- [ ] Diagnostics and status reporting
- [ ] Memory and thread safety review
- [ ] **Performance benchmark suite** (SISO through 50x30 MIMO)
- [ ] **Stress tests** (infeasibility, NaN inputs, rapid config changes)
- [ ] **Validation: Full three-layer on industrial-scale example** (20+ CVs, 15+ MVs)

### Phase 6: Python Bindings (Weeks 17-18)

**Goal:** Expose C++ core to Python via pybind11.

- [ ] pybind11 bindings for `DMCController`, `StepResponseModel`, all layers
- [ ] NumPy <-> Eigen automatic conversion
- [ ] Python unit tests mirroring C++ tests
- [ ] pip-installable package (`opendmc`)
- [ ] **Validation: Python closed-loop simulation matches C++ results exactly**

### Phase 7: Model Identification (Weeks 19-22)

**Goal:** Identify step response models from plant data (Python).

- [ ] Step test data import and preprocessing
- [ ] FIR identification (least-squares)
- [ ] Subspace identification (N4SID)
- [ ] State-space to step response conversion
- [ ] FOPTD/SOPTD fitting
- [ ] Model validation and fit metrics
- [ ] Step response visualization
- [ ] Export to HDF5 model format
- [ ] **Validation: Identify model from noisy CSTR step test data**

### Phase 8: Builder Application (Weeks 23-28)

**Goal:** Configuration, simulation, and deployment tool.

- [ ] Controller configuration data model and YAML schema
- [ ] Model import/visualization (from ID module or manual entry)
- [ ] Tuning parameter configuration
- [ ] Closed-loop simulation (calls C++ core via bindings)
- [ ] Scenario management (setpoint changes, disturbances, constraints)
- [ ] Tuning assistant (suggest initial weights from model properties)
- [ ] Deploy to controller repository
- [ ] CLI interface first, then Qt or web UI
- [ ] **Validation: End-to-end CSTR** (data -> model ID -> config -> simulate -> deploy)

### Phase 9: Runtime Service (Weeks 29-34)

**Goal:** Online execution engine with plant connectivity.

- [ ] Service event loop with scheduling
- [ ] OPC UA client integration (asyncua)
- [ ] Controller load/unload/reload from repository
- [ ] Online parameter changes via API
- [ ] Performance monitoring and logging
- [ ] REST/gRPC API for external access
- [ ] SQLite crash recovery for runtime state
- [ ] **Validation: Continuous operation with OPC UA simulator plant**
- [ ] **Validation: Hot-reload controller config without service restart**

### Phase 10: Polish and Advanced Features (Weeks 35+)

- [ ] Feedforward / disturbance variable support in all layers
- [ ] Gain-scheduled DMC (multiple models, blending)
- [ ] Web-based monitoring dashboard
- [ ] Comprehensive documentation and tutorials
- [ ] CI/CD pipeline (CMake build + pytest + Google Test)
- [ ] Packaging and distribution (pip, conda, conan)

---

## 11. Success Criteria

### Core Engine (must pass before moving to Builder/Service)

1. **SISO DMC** matches textbook step response control (zero steady-state error, correct constraint handling)
2. **MIMO DMC** (4x4+) solves Layer 1 QP in **<10ms** per cycle
3. **Two-layer optimizer** correctly relaxes constraints by priority when infeasible
4. **Three-layer optimizer** updates SS targets from NLP and Layer 1 tracks them
5. **Code-generated NLP** runs without CasADi dependency at runtime
6. **50x30 MIMO** controller completes full cycle (L2 + L1) in **<50ms**
7. **Python bindings** produce identical results to C++ within floating point tolerance

### Full System

8. **Model identification** from step test data produces accurate step response models
9. **Builder workflow**: raw data -> model ID -> configure -> simulate -> deploy
10. **Runtime service**: runs continuously with OPC UA, handles config changes live

---

## 12. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Core language | C++ with Python bindings (pybind11) | Performance for real-time QP, Python for tooling |
| Step response vs state-space | Step response primary, state-space as import | Industry standard for DMC, operators understand it |
| Layer 1 QP solver | OSQP (primary), qpOASES (fallback) | Open-source, fast, warm-startable |
| Layer 2 LP solver | HiGHS | Open-source, fast, handles LP and QP |
| Layer 3 NLP | CasADi C++ + IPOPT, with code generation | Auto-diff, codegen eliminates runtime dependency |
| Matrix library | Eigen | Header-only, vectorized, industry standard |
| Config format | YAML (metadata) + HDF5 (numerical) | Right tool for each data type |
| Build system | CMake | Cross-platform, handles C++ dependencies well |
| Three-layer vs two-layer | Three-layer (NLP + LP + QP) | Full industrial capability |
| Development order | Complete C++ core first | Algorithms must be correct before building apps on top |

---

## 13. LLM Prompt for Implementation

When you're ready to start building, use this prompt with an LLM:

---

> **System prompt for implementation:**
>
> You are building an open-source Dynamic Matrix Control (DMC) system called "OpenDMC". The core optimization engine is written in **C++** with **Python bindings** (pybind11). The system implements a **three-layer optimization architecture** inspired by AspenTech DMC3.
>
> ## Architecture
>
> The C++ core library (`libopendmc`) contains:
>
> **Shared components:**
> - `StepResponseModel`: stores S[ny][N][nu] step response (FIR) coefficients in Eigen tensors, loads from HDF5, converts from state-space (A,B,C,D). Computes free/forced response predictions.
> - `DynamicMatrix`: builds the lower-triangular Toeplitz prediction matrix A_dyn from step response coefficients. Provides both dense (Eigen::MatrixXd) and sparse (Eigen::SparseMatrix) formats.
> - `PredictionEngine`: manages rolling prediction window -- free response from past moves, forced response from future moves, disturbance correction.
> - `DisturbanceObserver`: estimates output bias d[k] for offset-free tracking. Supports exponential filter and Kalman filter modes.
> - `ConstraintHandler`: implements 5-level prioritized constraint relaxation (P1: MV hard limits, P2: MV rate limits, P3: CV safety, P4: CV operating, P5: setpoint tracking). Builds QP constraint matrices. Sequentially relaxes lower-priority constraints when infeasible.
> - `Scaling`: normalizes variables to [0,1] based on engineering ranges for numerical conditioning.
>
> **Layer 1 -- Dynamic QP (runs every sample period):**
> - `Layer1DynamicQP`: formulates and solves: min ||y_pred - y_target||²_Q + ||du||²_R, subject to MV bounds, MV rate limits, and CV output constraints (soft via priority system). Uses OSQP with warm-starting.
>
> **Layer 2 -- Steady-State Target (runs every sample period):**
> - `Layer2SSTarget`: solves LP or QP: min ||y_ss - y_sp||²_Qs + c^T·u_ss, subject to steady-state gain model y_ss = G·u_ss + d_ss, MV bounds, CV bounds (prioritized). Uses HiGHS for LP mode.
>
> **Layer 3 -- Nonlinear Optimizer (runs periodically, e.g., hourly):**
> - `Layer3NLP`: uses CasADi C++ API to formulate and solve NLP via IPOPT. Supports code generation (NLP -> C code -> .so) so runtime has no CasADi dependency. Can re-linearize the plant model to update Layer 2's gain matrix.
>
> **Orchestrator:**
> - `DMCController`: ties all three layers together. Main API: `execute(y_measured, u_current, dv_values) -> ControlOutput`. Handles online config changes (setpoints, bounds, weights, MV/CV enable/disable, mode switching).
>
> ## Technical requirements
> - C++17, CMake build system
> - Eigen 3.x for matrix operations
> - OSQP for Layer 1 QP (with warm-starting workspace)
> - HiGHS for Layer 2 LP
> - CasADi C++ API + IPOPT for Layer 3 NLP (optional, compile-time flag)
> - yaml-cpp for YAML config parsing
> - HDF5 C++ API for model storage (step response matrices)
> - Google Test for C++ unit tests
> - pybind11 for Python bindings (NumPy <-> Eigen conversion)
>
> ## Data storage
> - YAML for controller config (CV/MV definitions, tuning, horizons)
> - HDF5 for numerical model data (step response S[ny, N, nu])
> - Compiled .so/.dll for code-generated Layer 3 NLP solvers
>
> ## Reference
> The `mpc-tools-casadi` repo (Rawlings Group, Python/CasADi) provides reference implementations for: steady-state target formulation (`sstarg()`), linearization (`util.getLinearizedModel`), EKF (`util.ekf`), and simulator patterns (`DiscreteSimulator`). OpenDMC reimplements these concepts in C++ with step-response-based DMC.
>
> ## Development order (COMPLETE CORE FIRST)
> 1. **Phase 1** (Weeks 1-3): StepResponseModel, DynamicMatrix, PredictionEngine, DisturbanceObserver. Validate with SISO FOPTD closed-loop.
> 2. **Phase 2** (Weeks 4-6): Layer1DynamicQP with OSQP. Validate with constrained SISO, 2x2 MIMO (Wood-Berry), 4x4 MIMO.
> 3. **Phase 3** (Weeks 7-9): Layer2SSTarget with HiGHS + ConstraintHandler. Validate two-layer CSTR control and infeasibility scenarios.
> 4. **Phase 4** (Weeks 10-13): Layer3NLP with CasADi C++. Validate three-layer CSTR with RTO.
> 5. **Phase 5** (Weeks 14-16): DMCController orchestrator, Scaling, config loading, hardening. Benchmark 50x30 MIMO.
> 6. **Phase 6** (Weeks 17-18): pybind11 Python bindings.
> 7. **Phases 7-10**: Model identification (Python), Builder app, Runtime service.
>
> **Start with Phase 1:** Implement `StepResponseModel`, `DynamicMatrix`, `PredictionEngine`, and `DisturbanceObserver` in C++ with Google Test unit tests and a SISO FOPTD closed-loop example.

---
