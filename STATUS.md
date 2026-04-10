# Azeotrope APC -- Project Status

**Last updated:** 2026-04-10

---

## Current Phase: Phase 1 -- Core Foundation

**Status: SCAFFOLDING COMPLETE, IMPLEMENTATION NOT STARTED**

---

## Phase Overview

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| **Phase 1** | Core Foundation (StepResponseModel, DynamicMatrix, PredictionEngine, DisturbanceObserver) | **Scaffolded** | Headers designed, stubs created, no implementation yet |
| Phase 2 | Layer 1 -- Dynamic QP (OSQP) | Not started | Depends on Phase 1 |
| Phase 3 | Layer 2 -- Steady-State Target (HiGHS) + Constraint Handler | Not started | Depends on Phase 2 |
| Phase 4 | Layer 3 -- Nonlinear Optimizer (CasADi/IPOPT) | Not started | Depends on Phase 3 |
| Phase 5 | Core Integration (MPCController orchestrator, Scaling, config, hardening) | Not started | Depends on Phase 4 |
| Phase 6 | Python Bindings (pybind11) | Not started | Depends on Phase 5 |
| Phase 7 | Model Identification (Python) | Not started | Depends on Phase 6 |
| Phase 8 | Builder Application | Not started | Depends on Phase 7 |
| Phase 9 | Runtime Service | Not started | Depends on Phase 8 |
| Phase 10 | Polish and Advanced Features | Not started | Depends on Phase 9 |

---

## Phase 1: Core Foundation -- Detailed Tracker

| Task | File(s) | Status | Notes |
|------|---------|--------|-------|
| CMake build system compiles | `CMakeLists.txt`, `core/CMakeLists.txt` | Done | Scaffold only, not build-tested yet |
| Eigen + Google Test integration | `core/tests/CMakeLists.txt` | Done | FetchContent configured |
| `StepResponseModel` -- store coefficients | `core/include/azeoapc/step_response_model.h` | Header done | `.cpp` stub, needs implementation |
| `StepResponseModel::fromStateSpace()` | `core/src/step_response_model.cpp` | Not started | Key: S[i] = C * A^i * B cumulative |
| `StepResponseModel::fromFOPTD()` | `core/src/step_response_model.cpp` | Not started | SISO convenience factory |
| `StepResponseModel::fromHDF5()` / `saveHDF5()` | `core/src/step_response_model.cpp` | Not started | Needs HDF5 C++ API |
| `DynamicMatrix` -- Toeplitz construction | `core/include/azeoapc/dynamic_matrix.h` | Header done | `.cpp` stub, needs implementation |
| `DynamicMatrix` -- sparse format | `core/src/dynamic_matrix.cpp` | Not started | For OSQP efficiency |
| `PredictionEngine` -- free/forced response | `core/include/azeoapc/prediction_engine.h` | Header done | `.cpp` stub, needs implementation |
| `PredictionEngine` -- rolling past_moves window | `core/src/prediction_engine.cpp` | Not started | deque of du vectors |
| `DisturbanceObserver` -- exponential filter | `core/include/azeoapc/disturbance_observer.h` | Header done | `.cpp` stub, needs implementation |
| `DisturbanceObserver` -- Kalman filter mode | `core/src/disturbance_observer.cpp` | Not started | Optional, can defer |
| Unit tests: step response | `core/tests/test_step_response.cpp` | Stub only | Needs real test cases |
| Unit tests: dynamic matrix | `core/tests/test_dynamic_matrix.cpp` | Stub only | Needs real test cases |
| Unit tests: prediction | `core/tests/test_prediction.cpp` | Stub only | Needs real test cases |
| **SISO FOPTD closed-loop validation** | `examples/siso_foptd.cpp` | Stub only | Phase 1 gate: must pass before Phase 2 |

### Phase 1 Exit Criteria

- [ ] CMake builds cleanly on Windows (MSVC) and Linux (GCC)
- [ ] `StepResponseModel` stores, loads, and converts from state-space
- [ ] `DynamicMatrix` builds correct Toeplitz matrix (verified against hand calculation)
- [ ] `PredictionEngine` computes correct free and forced responses
- [ ] `DisturbanceObserver` eliminates steady-state offset in closed-loop
- [ ] SISO FOPTD example runs closed-loop and matches expected textbook behavior
- [ ] All Google Test unit tests pass

---

## Phase 2: Layer 1 -- Dynamic QP (Not Started)

| Task | File(s) | Status |
|------|---------|--------|
| `Layer1DynamicQP` -- OSQP integration | `core/src/layer1_dynamic_qp.cpp` | Not started |
| MV absolute bounds (P1) | `layer1_dynamic_qp.cpp` | Not started |
| MV rate-of-change bounds (P2) | `layer1_dynamic_qp.cpp` | Not started |
| CV output constraints soft (P3/P4) | `layer1_dynamic_qp.cpp` | Not started |
| QP warm-starting between cycles | `layer1_dynamic_qp.cpp` | Not started |
| Online weight/bound updates | `layer1_dynamic_qp.cpp` | Not started |
| Performance benchmarks | `core/tests/test_layer1_qp.cpp` | Not started |
| **SISO constrained MPC validation** | | Not started |
| **2x2 MIMO Wood-Berry validation** | | Not started |
| **4x4 MIMO (<10ms) validation** | | Not started |

---

## Phase 3: Layer 2 -- Steady-State Target (Not Started)

| Task | File(s) | Status |
|------|---------|--------|
| `Layer2SSTarget` -- HiGHS LP integration | `core/src/layer2_ss_target.cpp` | Not started |
| `ConstraintHandler` -- 5-level priorities | `core/src/constraint_handler.cpp` | Not started |
| Feasibility detection + sequential relaxation | `constraint_handler.cpp` | Not started |
| QP mode for quadratic SS objectives | `layer2_ss_target.cpp` | Not started |
| Economic cost support | `layer2_ss_target.cpp` | Not started |
| **Two-layer CSTR validation** | | Not started |
| **Infeasibility scenario validation** | | Not started |

---

## Phase 4: Layer 3 -- Nonlinear Optimizer (Not Started)

| Task | File(s) | Status |
|------|---------|--------|
| `Layer3NLP` -- CasADi C++ API | `core/src/layer3_nlp.cpp` | Not started |
| IPOPT integration | `layer3_nlp.cpp` | Not started |
| Code generation workflow (NLP -> C -> .so) | `layer3_nlp.cpp` | Not started |
| Runtime loading of codegen'd solver | `layer3_nlp.cpp` | Not started |
| Re-linearization (update Layer 2 gain) | `layer3_nlp.cpp` | Not started |
| **Three-layer CSTR validation** | | Not started |

---

## Phase 5: Core Integration (Not Started)

| Task | File(s) | Status |
|------|---------|--------|
| `MPCController` orchestrator | `core/src/mpc_controller.cpp` | Not started |
| `Scaling` module | `core/src/scaling.cpp` | Not started |
| YAML config parsing | `core/src/config.cpp` | Not started |
| HDF5 model loading | `step_response_model.cpp` | Not started |
| `Storage` -- SQLite timeseries | `core/src/storage.cpp` | Not started |
| Online configuration API | `mpc_controller.cpp` | Not started |
| Mode switching (MANUAL/AUTO/CASCADE) | `mpc_controller.cpp` | Not started |
| Diagnostics and status reporting | `mpc_controller.cpp` | Not started |
| Thread safety review | | Not started |
| **50x30 MIMO benchmark (<50ms)** | | Not started |
| **Stress tests** | | Not started |

---

## Phase 6: Python Bindings (Not Started)

| Task | File(s) | Status |
|------|---------|--------|
| pybind11 bindings | `bindings/pybind_opendmc.cpp` | Scaffold done |
| NumPy <-> Eigen conversion | `bindings/pybind_opendmc.cpp` | Not started |
| Python unit tests | `python/tests/` | Not started |
| pip-installable package | `pyproject.toml` | Scaffold done |
| **Python results match C++ exactly** | | Not started |

---

## Infrastructure Status

| Item | Status | Notes |
|------|--------|-------|
| Git repository | Initialized | `C:\Users\nazmuh\Documents\dev\azeotrope-apc` |
| Initial commit | **Not done** | Need to commit scaffolding |
| CI/CD pipeline | Not started | GitHub Actions planned |
| Remote repository | Not created | Need to create on GitHub |
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

---

## Blockers / Open Questions

- [ ] Which CI platform? (GitHub Actions vs. other)
- [ ] Should Layer 1 support state-space prediction directly (not just FIR)? Would allow skipping step response generation for small systems.
- [ ] Target platforms: Windows + Linux? Mac?
- [ ] License confirmed as MIT?

---

## Next Action

**Start Phase 1 implementation:** Implement `StepResponseModel::fromStateSpace()` and `StepResponseModel::fromFOPTD()` in `core/src/step_response_model.cpp`, write unit tests, verify against hand calculations.
