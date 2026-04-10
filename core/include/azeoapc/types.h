#pragma once

#include <Eigen/Dense>
#include <string>
#include <vector>

namespace azeoapc {

// ============================================================================
// Solver status
// ============================================================================
enum class SolverStatus {
    OPTIMAL,
    INFEASIBLE,
    MAX_ITER,
    TIME_LIMIT,
    NUMERICAL_ERROR,
    NOT_SOLVED
};

const char* solverStatusStr(SolverStatus s);

// ============================================================================
// Controller mode
// ============================================================================
enum class ControllerMode {
    MANUAL,     // No optimization, operator controls MVs directly
    AUTO,       // Full three-layer optimization
    CASCADE     // Receives setpoints from upstream controller
};

// ============================================================================
// Variable configurations
// ============================================================================
struct CVConfig {
    std::string name;
    std::string tag;           // OPC UA / DCS tag
    std::string units;
    double setpoint;
    double lo_limit;           // operating low
    double hi_limit;           // operating high
    double safety_lo;          // safety low (higher priority)
    double safety_hi;          // safety high (higher priority)
    double engineering_lo;     // engineering range low (for scaling)
    double engineering_hi;     // engineering range high
    double weight;             // Q diagonal element
    int priority;              // constraint priority (3 or 4 typically)
    bool enabled = true;
};

struct MVConfig {
    std::string name;
    std::string tag;
    std::string units;
    double lo_limit;
    double hi_limit;
    double rate_limit;         // max |du| per sample period
    double move_suppress;      // R diagonal element
    double cost;               // economic cost (Layer 2 LP)
    double engineering_lo;
    double engineering_hi;
    bool enabled = true;
};

struct DVConfig {
    std::string name;
    std::string tag;
    std::string units;
};

// ============================================================================
// Diagnostics
// ============================================================================
struct DiagnosticsInfo {
    SolverStatus layer1_status;
    SolverStatus layer2_status;
    SolverStatus layer3_status;
    double layer1_solve_ms;
    double layer2_solve_ms;
    double layer3_solve_ms;
    double total_solve_ms;
    int layer1_iterations;
    int layer2_iterations;
    std::vector<int> relaxed_priorities;
    std::vector<int> active_mv_constraints;  // indices of MVs at bounds
    std::vector<int> active_cv_constraints;  // indices of CVs at bounds
    std::string message;
};

struct PerformanceMetrics {
    double cv_tracking_rmse;       // RMS CV tracking error
    double mv_utilization;         // fraction of time MVs at limits
    int constraint_violations;     // count in window
    double avg_solve_time_ms;
    double max_solve_time_ms;
    double service_factor;         // fraction of cycles on time
    int total_cycles;
    int infeasible_cycles;
};

}  // namespace azeoapc
