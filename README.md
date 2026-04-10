# Azeotrope APC

**Open-Source Advanced Process Control Platform**

A modular, industrial-grade Model Predictive Control (MPC) system with a C++ optimization core and Python application layer.

## Architecture

```
Three-Layer Optimization Engine (C++ core: libazeoapc)

  Layer 3: Nonlinear Optimizer (CasADi/IPOPT)  -- periodic RTO
  Layer 2: Steady-State Target (HiGHS LP/QP)    -- every cycle
  Layer 1: Dynamic Controller (OSQP QP)         -- every cycle

Python Layer:
  - Builder: Model identification, configuration, simulation, deployment
  - Runtime Service: Scheduling, OPC UA, monitoring
  - SQLite timeseries database for all optimizer state, variables, and logs
```

## Building

### Prerequisites

- C++17 compiler (GCC 9+, MSVC 2019+, Clang 10+)
- CMake 3.20+
- Python 3.9+

### Build

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build .
ctest
```

### Python Package

```bash
pip install -e .
```

## Project Status

Phase 1: Core Foundation (in progress)

## License

MIT License -- See [LICENSE](LICENSE)
