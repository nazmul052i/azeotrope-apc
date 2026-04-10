#pragma once

#include <Eigen/Dense>
#include <memory>
#include <string>
#include "azeoapc/types.h"
#include "azeoapc/step_response_model.h"
#include "azeoapc/prediction_engine.h"
#include "azeoapc/disturbance_observer.h"
#include "azeoapc/layer1_dynamic_qp.h"
#include "azeoapc/layer2_ss_target.h"
#include "azeoapc/layer3_nlp.h"
#include "azeoapc/scaling.h"
#include "azeoapc/storage.h"

namespace azeoapc {

/**
 * MPC Controller: Three-Layer Orchestrator
 *
 * The main class that ties all three optimization layers together.
 * This is the primary API for the C++ core.
 *
 * Usage:
 *   auto ctrl = MPCController::fromFiles("config.yaml", "model.hdf5");
 *   while (running) {
 *       auto out = ctrl.execute(y_measured, u_current, dv_values);
 *       applyToPlant(out.u_new);
 *   }
 */

struct MPCConfig {
    // Model
    std::string model_path;         // HDF5 model file
    double sample_time;

    // Layer 1
    Layer1Config layer1;

    // Layer 2
    Layer2Config layer2;

    // Layer 3 (optional)
    bool enable_layer3 = false;
    Layer3Config layer3;

    // Variables
    std::vector<CVConfig> cvs;
    std::vector<MVConfig> mvs;
    std::vector<DVConfig> dvs;

    // Storage
    bool enable_storage = true;
    std::string storage_path;       // SQLite database path
    bool log_predictions = false;   // Log full prediction trajectories (large)

    // Load from YAML file
    static MPCConfig fromYAML(const std::string& path);
};

class MPCController {
public:
    MPCController(const MPCConfig& config, const StepResponseModel& model);

    /// Create from config file + model file
    static MPCController fromFiles(const std::string& config_yaml,
                                   const std::string& model_hdf5);

    ~MPCController();

    // ===== MAIN EXECUTION (called every sample period) =====

    struct ControlOutput {
        Eigen::VectorXd du;                // recommended MV moves [nu]
        Eigen::VectorXd u_new;             // new MV values: u_current + du [nu]
        Eigen::VectorXd y_predicted;       // predicted CV trajectory [P*ny]
        Eigen::VectorXd y_ss_target;       // steady-state CV targets [ny]
        Eigen::VectorXd u_ss_target;       // steady-state MV targets [nu]
        Eigen::VectorXd disturbance;       // current disturbance estimate [ny]
        SolverStatus layer1_status;
        SolverStatus layer2_status;
        double total_solve_time_ms;
        DiagnosticsInfo diagnostics;
    };

    ControlOutput execute(
        const Eigen::VectorXd& y_measured,     // current CV readings [ny]
        const Eigen::VectorXd& u_current,      // current MV values [nu]
        const Eigen::VectorXd& dv_values = {}  // current DV values [ndv]
    );

    // ===== LAYER 3 (called periodically, can be in separate thread) =====

    void executeRTO(const Eigen::VectorXd& plant_state);

    // ===== ONLINE CONFIGURATION =====

    void setSetpoints(const Eigen::VectorXd& y_sp);
    void setSetpoint(int cv_idx, double sp);
    void setCVBounds(int cv_idx, double lo, double hi);
    void setMVBounds(int mv_idx, double lo, double hi);
    void setMVRateLimit(int mv_idx, double rate);
    void setCVWeight(int cv_idx, double weight);
    void setMVWeight(int mv_idx, double weight);
    void enableMV(int mv_idx, bool enabled);
    void enableCV(int cv_idx, bool enabled);
    void setMode(ControllerMode mode);

    // ===== STATUS & DIAGNOSTICS =====

    ControllerMode mode() const;
    ControllerStatus status() const;
    PerformanceMetrics metrics() const;
    const StepResponseModel& model() const;

    // ===== STORAGE ACCESS =====

    /// Get reference to storage for querying historical data
    const Storage* storage() const;

    int ny() const;
    int nu() const;
    int ndv() const;
    int64_t cycleCount() const;

private:
    MPCConfig config_;
    StepResponseModel model_;
    std::unique_ptr<Scaling> scaling_;
    std::unique_ptr<PredictionEngine> prediction_;
    std::unique_ptr<DisturbanceObserver> observer_;
    std::unique_ptr<Layer1DynamicQP> layer1_;
    std::unique_ptr<Layer2SSTarget> layer2_;
    std::unique_ptr<Layer3NLP> layer3_;
    std::unique_ptr<Storage> storage_;

    ControllerMode mode_;
    Eigen::VectorXd y_setpoints_;
    int64_t cycle_count_;

    // Log one complete cycle to storage
    void logCycle(int64_t timestamp_ms,
                  const Eigen::VectorXd& y_measured,
                  const Eigen::VectorXd& u_current,
                  const Eigen::VectorXd& dv_values,
                  const ControlOutput& output);
};

// ============================================================================
// Controller status (for monitoring)
// ============================================================================
struct ControllerStatus {
    std::string name;
    ControllerMode mode;
    bool is_running;
    int64_t cycle_count;
    double last_solve_time_ms;
    SolverStatus last_layer1_status;
    SolverStatus last_layer2_status;
    int active_cvs;
    int active_mvs;
    int total_cvs;
    int total_mvs;
};

}  // namespace azeoapc
