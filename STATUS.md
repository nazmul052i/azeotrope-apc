# Azeotrope APC -- Project Status

**Last updated:** 2026-04-10

---

## Current Phase: Phase 6 -- Python Bindings & Logging

**Status: PHASE 6 COMPLETE -- 9 C++ test suites + 34 Python tests, all passing**

---

## Phase Overview

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| **Phase 1** | Core Foundation (StepResponseModel, DynamicMatrix, PredictionEngine, DisturbanceObserver) | **Done** | All implementations, tests, and CSTR validation passing |
| **Phase 2** | Layer 1 -- Dynamic QP (OSQP) + ConstraintHandler | **Done** | OSQP integrated, constrained QP solving, 6 test suites passing |
| **Phase 3** | Layer 2 -- Steady-State Target (HiGHS LP + KKT QP) | **Done** | HiGHS LP for economic opt, direct KKT solve for QP tracking |
| **Phase 4** | Layer 3 -- Numerical Linearization + Re-linearization | **Done** | Numerical Jacobians via finite differences, CasADi deferred |
| **Phase 5** | Core Integration (MPCController, Scaling, Storage stub) | **Done** | 3-layer orchestrator, online config, mode switching, 9 test suites |
| **Phase 6** | Python Bindings (pybind11) + spdlog logging | **Done** | 34 Python tests pass, all classes exposed, log level control |
| Phase 7 | Model Identification (Python) | Not started | Depends on Phase 6 |
| Phase 8 | Builder Application | Not started | Depends on Phase 7 |
| Phase 9 | Runtime Service | Not started | Depends on Phase 8 |
| Phase 10 | Polish and Advanced Features | Not started | Depends on Phase 9 |

---

## Phase 1: Core Foundation -- Detailed Tracker

| Task | File(s) | Status | Notes |
|------|---------|--------|-------|
| CMake build system compiles | `CMakeLists.txt`, `core/CMakeLists.txt` | **Done** | Builds with MSVC 2022, Eigen3 + GTest via FetchContent |
| Eigen + Google Test integration | `core/tests/CMakeLists.txt` | **Done** | FetchContent with gtest_force_shared_crt for Windows |
| `types.cpp` -- solverStatusStr | `core/src/types.cpp` | **Done** | Enum to string conversion |
| `StepResponseModel` -- store coefficients | `core/src/step_response_model.cpp` | **Done** | Flat storage S[ny*N*nu], cache-friendly layout |
| `StepResponseModel::fromStateSpace()` | `core/src/step_response_model.cpp` | **Done** | Iterative A^k*B accumulation, validated against hand calc |
| `StepResponseModel::fromFOPTD()` | `core/src/step_response_model.cpp` | **Done** | Direct FOPTD formula, SISO convenience |
| `StepResponseModel::fromFOPTDMatrix()` | `core/src/step_response_model.cpp` | **Done** | MIMO from per-channel FOPTD parameters |
| `StepResponseModel::predictFree()` | `core/src/step_response_model.cpp` | **Done** | Free response from past moves history |
| `StepResponseModel::predictForced()` | `core/src/step_response_model.cpp` | **Done** | Forced response matching Toeplitz multiplication |
| `StepResponseModel::fromHDF5()` / `saveHDF5()` | `core/src/step_response_model.cpp` | Stub | Throws runtime_error until HDF5 enabled |
| `DynamicMatrix` -- Toeplitz construction | `core/src/dynamic_matrix.cpp` | **Done** | Lower-triangular block Toeplitz from step response |
| `DynamicMatrix` -- sparse format | `core/src/dynamic_matrix.cpp` | **Done** | Eigen::SparseMatrix via sparseView() |
| `DynamicMatrix` -- cumulative matrix C | `core/src/dynamic_matrix.cpp` | **Done** | Lower-triangular identity blocks for absolute MV constraints |
| `PredictionEngine` -- free/forced response | `core/src/prediction_engine.cpp` | **Done** | Combines model predictFree + DynamicMatrix forced |
| `PredictionEngine` -- rolling past_moves window | `core/src/prediction_engine.cpp` | **Done** | deque with auto-trimming to model horizon |
| `DisturbanceObserver` -- exponential filter | `core/src/disturbance_observer.cpp` | **Done** | Configurable alpha, converges to true bias |
| `DisturbanceObserver` -- Kalman filter mode | `core/src/disturbance_observer.cpp` | **Done** | Random walk model, converges for MIMO |
| Unit tests: step response | `core/tests/test_step_response.cpp` | **Done** | 17 tests: FOPTD, state-space, MIMO, prediction, metadata |
| Unit tests: dynamic matrix | `core/tests/test_dynamic_matrix.cpp` | **Done** | 11 tests: Toeplitz, sparse, cumulative, MIMO, rebuild |
| Unit tests: prediction | `core/tests/test_prediction.cpp` | **Done** | 8 tests: history, superposition, MIMO, trimming |
| Unit tests: disturbance observer | `core/tests/test_disturbance_observer.cpp` | **Done** | 11 tests: exp filter, Kalman, reset, MIMO, validation |
| **CSTR closed-loop validation** | `examples/cstr_closed_loop.cpp` | **Done** | 2x2 MIMO CSTR from mpc-tools-casadi reference, concentration RMSE=0.037, level RMSE=0.166 |

### Phase 1 Exit Criteria

- [x] CMake builds cleanly on Windows (MSVC 2022)
- [x] `StepResponseModel` stores, loads, and converts from state-space
- [x] `DynamicMatrix` builds correct Toeplitz matrix (verified against predictForced)
- [x] `PredictionEngine` computes correct free and forced responses
- [x] `DisturbanceObserver` converges to true bias (exponential filter + Kalman)
- [x] CSTR example runs closed-loop 2x2 MIMO and tracks setpoint changes
- [x] All 47 Google Test unit tests pass (4 test suites)
- [ ] CMake builds cleanly on Linux (GCC) -- not tested yet

---

## Phase 2: Layer 1 -- Dynamic QP

| Task | File(s) | Status | Notes |
|------|---------|--------|-------|
| `ConstraintHandler` -- 5-level priorities | `core/src/constraint_handler.cpp` | **Done** | P1-P4 bounds, QP matrix builder, relaxation |
| `Layer1DynamicQP` -- OSQP integration | `core/src/layer1_dynamic_qp.cpp` | **Done** | Full OSQP v0.6.3 integration, warm-starting, pimpl wrapper |
| MV absolute bounds (P1) | `constraint_handler.cpp` | **Done** | Via cumulative matrix C |
| MV rate-of-change bounds (P2) | `constraint_handler.cpp` | **Done** | Identity block in constraint matrix |
| CV output constraints (P3/P4) | `constraint_handler.cpp` | **Done** | Via A_dyn block, relaxation support |
| QP warm-starting between cycles | `layer1_dynamic_qp.cpp` | **Done** | Shifted warm-start from previous solution |
| Online weight/bound updates | `layer1_dynamic_qp.cpp` | **Done** | updateWeights rebuilds H and OSQP workspace |
| Unit tests: constraint handler | `core/tests/test_constraint_handler.cpp` | **Done** | 12 tests: bounds, structure, feasibility, online updates |
| Unit tests: Layer 1 QP | `core/tests/test_layer1_qp.cpp` | **Done** | 9 tests: unconstrained, constrained, MIMO, weight update |
| **SISO constrained MPC validation** | `test_layer1_qp.cpp` | **Done** | Move limits verified |
| **2x2 MIMO validation** | `test_layer1_qp.cpp` | **Done** | FOPTD MIMO tracking |
| **4x4 MIMO (<10ms) validation** | | Not started | |

---

## Phase 3: Layer 2 -- Steady-State Target

| Task | File(s) | Status | Notes |
|------|---------|--------|-------|
| `Layer2SSTarget` -- HiGHS LP integration | `core/src/layer2_ss_target.cpp` | **Done** | Economic LP with MV bounds via HiGHS v1.7.0 |
| QP mode for quadratic SS objectives | `layer2_ss_target.cpp` | **Done** | Direct KKT solve via SVD (small system, robust) |
| Economic cost support | `layer2_ss_target.cpp` | **Done** | c' * u_ss linear cost in LP/QP |
| Constraint handler bound accessors | `constraint_handler.h` | **Done** | Raw bound getters for Layer 2 integration |
| Gain matrix update (from Layer 3) | `layer2_ss_target.cpp` | **Done** | updateGainMatrix() for re-linearization |
| Online setpoint/cost updates | `layer2_ss_target.cpp` | **Done** | updateSetpoints(), updateCosts() |
| Unit tests: Layer 2 | `core/tests/test_layer2_lp.cpp` | **Done** | 8 tests: LP, QP tracking, disturbance, MIMO, gain update |

---

## Phase 4: Layer 3 -- Nonlinear Optimizer

| Task | File(s) | Status | Notes |
|------|---------|--------|-------|
| `Layer3NLP` -- codegen constructor | `core/src/layer3_nlp.cpp` | **Done** | Stores config, prepares for numerical linearization |
| `setModelFunction()` | `layer3_nlp.h/cpp` | **Done** | Accept std::function for discrete model x_next=f(x,u) |
| Numerical linearization | `layer3_nlp.cpp` | **Done** | Central finite differences for A,B; C=I, D=0 |
| Re-linearization → Layer 2 gain update | `layer3_nlp.cpp` | **Done** | linearizeAt() returns StateSpaceModel for gain update |
| Unit tests: Layer 3 | `core/tests/test_layer3_nlp.cpp` | **Done** | 8 tests: linear, nonlinear, MIMO, CSTR, re-linearization |
| CasADi C++ API integration | `layer3_nlp.cpp` | Deferred | Requires CasADi installed (AZEOAPC_HAS_CASADI) |
| IPOPT NLP solve | `layer3_nlp.cpp` | Deferred | solve() returns current point without CasADi |
| Code generation workflow | `layer3_nlp.cpp` | Deferred | generateCode() requires CasADi |

---

## Phase 5: Core Integration

| Task | File(s) | Status | Notes |
|------|---------|--------|-------|
| `MPCController` orchestrator | `core/src/mpc_controller.cpp` | **Done** | 3-layer execute loop: prediction → Layer 2 → Layer 1, warm-starting |
| `Scaling` module | `core/src/scaling.cpp` | **Done** | CV/MV normalization [0,1], increment scaling, bound scaling |
| `Storage` stub | `core/src/storage.cpp` | **Done** | Pimpl with no-op methods; SQLite deferred |
| Online configuration API | `mpc_controller.cpp` | **Done** | setSetpoints, setCVBounds, setMVBounds, setCVWeight, setMVWeight |
| Mode switching (MANUAL/AUTO) | `mpc_controller.cpp` | **Done** | MANUAL returns zero du; AUTO runs full 3-layer |
| Diagnostics and status | `mpc_controller.cpp` | **Done** | DiagnosticsInfo, ControllerStatus, PerformanceMetrics |
| ControllerStatus forward decl fix | `mpc_controller.h` | **Done** | Moved before MPCController class |
| Unit tests: MPCController | `core/tests/test_mpc_controller.cpp` | **Done** | 10 tests: construction, tracking, MIMO, manual mode, online config, diagnostics |
| YAML config parsing | `core/src/config.cpp` | Deferred | Requires yaml-cpp |
| HDF5 model loading | `step_response_model.cpp` | Deferred | Requires HDF5 |
| SQLite timeseries | `storage.cpp` | Deferred | Requires SQLite |
| Thread safety review | | Deferred | |
| **50x30 MIMO benchmark (<50ms)** | | Not started | |

---

## Phase 6: Python Bindings & Logging

| Task | File(s) | Status | Notes |
|------|---------|--------|-------|
| spdlog integration (CMake) | `CMakeLists.txt`, `core/CMakeLists.txt` | **Done** | v1.12.0 via FetchContent |
| spdlog logging in MPCController | `core/src/mpc_controller.cpp` | **Done** | debug/warn for execute loop |
| spdlog logging in Layer 1 | `core/src/layer1_dynamic_qp.cpp` | **Done** | trace after OSQP solve |
| spdlog logging in Layer 2 | `core/src/layer2_ss_target.cpp` | **Done** | trace for LP and QP |
| spdlog logging in Layer 3 | `core/src/layer3_nlp.cpp` | **Done** | debug/trace in linearizeAt |
| pybind11 bindings (all classes) | `bindings/pybind_opendmc.cpp` | **Done** | All layers, configs, results, enums, logging control |
| NumPy <-> Eigen conversion | `bindings/pybind_opendmc.cpp` | **Done** | pybind11/eigen.h automatic |
| Python package update | `python/azeoapc/__init__.py` | **Done** | All classes imported, setup_logging() convenience |
| Python unit tests | `python/tests/test_core.py` | **Done** | 9 test classes: model, matrix, prediction, observer, L1, L2, L3, controller, logging |
| pip-installable package | `pyproject.toml` | Scaffold done | |
| **Build verification** | | **Done** | MSVC 2022, Python 3.13, pybind11 2.12.0, spdlog 1.12.0 |
| **Python results match C++ exactly** | | **Done** | 34 pytest tests verify NumPy<->Eigen conversion |

---

## Infrastructure Status

| Item | Status | Notes |
|------|--------|-------|
| Git repository | Initialized | Initial commit + Phase 1 implementation |
| CMake build (MSVC) | **Working** | Visual Studio 2022, Release config |
| CMake build (GCC) | Not tested | MinGW available, not validated |
| CI/CD pipeline | Not started | GitHub Actions planned |
| Remote repository | Created | GitHub |
| CLAUDE.md | Done | Full project context for Claude Code |
| Proposal document | Done | `docs/dmc-system-proposal.md` |

---

## Design Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-10 | Use MPC naming, not DMC | System supports multiple MPC formulations beyond DMC |
| 2026-04-10 | State-space as primary model, FIR derived from SS | CasADi uses state-space; FIR is just a view for QP layer |
| 2026-04-10 | YAML + HDF5 (not pure JSON/YAML) | YAML for human-readable config, HDF5 for large numerical arrays |
| 2026-04-10 | SQLite for timeseries storage | All optimizer variables, states, logs persisted every cycle |
| 2026-04-10 | C++ core with pybind11 | Performance for real-time QP; Python for tooling |
| 2026-04-10 | Core-first development order | Algorithms must be correct before building apps on top |
| 2026-04-10 | ETHZ Control Toolbox (ct) as C++ reference | SS/TF conversions, control utilities design patterns |
| 2026-04-10 | Three-layer architecture (NLP + LP + QP) | Full industrial capability matching DMC3 |
| 2026-04-10 | CSTR from mpc-tools-casadi as validation plant | Nonlinear 3-state model with integrating level; realistic MIMO test |
| 2026-04-10 | Phase 1 deps: Eigen + GTest only | OSQP/HiGHS/yaml-cpp deferred to Phase 2/3/5 via CMake options |
| 2026-04-10 | Numerical linearization in examples | Finite-difference Jacobian + RK4 for discrete (A,B); avoids CasADi dependency in Phase 1 |
| 2026-04-10 | OSQP MAX_ITER macro conflict | OSQP constants.h defines MAX_ITER macro, must #undef before using SolverStatus::MAX_ITER |
| 2026-04-10 | HiGHS for LP, KKT for QP in Layer 2 | HiGHS QP API unreliable with incremental/model APIs; direct KKT solve (SVD) is robust for small SS target systems |
| 2026-04-10 | Layer 3 numerical linearization without CasADi | setModelFunction() accepts std::function for discrete model; central differences for Jacobians; CasADi deferred |
| 2026-04-10 | spdlog for C++ logging | Lightweight, header-only-capable, fmt-based; log scalar values not Eigen matrices to avoid formatter issues |
| 2026-04-10 | pybind11 bindings expose all core classes | Full API: StepResponseModel, DynamicMatrix, PredictionEngine, Observer, Layers 1-3, MPCController, Scaling, configs |

---

## Blockers / Open Questions

- [ ] Which CI platform? (GitHub Actions vs. other)
- [ ] Should Layer 1 support state-space prediction directly (not just FIR)? Would allow skipping step response generation for small systems.
- [ ] Target platforms: Windows + Linux? Mac?
- [ ] License confirmed as MIT?
- [x] Level variable (integrating) poorly served by truncated FIR model -- consider velocity-form or augmented integrating model for Phase 2

---

## Simulator Application

| Task | File(s) | Status | Notes |
|------|---------|--------|-------|
| SimConfig + YAML loader | `simulator/models/config_loader.py` | **Done** | Loads MVs/CVs/DVs/plant from YAML |
| StateSpacePlant / FOPTDPlant | `simulator/models/plant.py` | **Done** | c2d, step, get_output |
| Variable definitions (MV/CV/DV) | `simulator/models/variables.py` | **Done** | Limits, steady_state, plot ranges |
| SimEngine (plant + MPC) | `simulator/sim_engine.py` | **Done** | C++ core integration, closed-loop stepping |
| TrendStrip (pyqtgraph) | `simulator/widgets/trend_strip.py` | **Done** | History + now + prediction |
| WhatIfSimulator (standalone) | `simulator/whatif_window.py` | **Done** | Tables + plots + step sim + activity log |
| app.py entry point | `simulator/app.py` | **Done** | Launches WhatIfSimulator from YAML |
| Fired heater example config | `simulator/examples/fired_heater.yaml` | **Done** | 3 MV, 5 CV, 2 DV, 10-state SS model |

---

## Next Action

**Start Phase 7:** Implement Python model identification (step test analysis, FIR least-squares, subspace ID). Build on the C++ core + Python bindings.
