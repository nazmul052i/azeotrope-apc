#include "azeoapc/mpc_controller.h"
#include <chrono>
#include <stdexcept>
#include <spdlog/spdlog.h>

// Undefine problematic macros from OSQP/HiGHS
#ifdef MAX_ITER
#undef MAX_ITER
#endif

namespace azeoapc {

// ===========================================================================
// MPCConfig::fromYAML (stub -- requires yaml-cpp)
// ===========================================================================
MPCConfig MPCConfig::fromYAML(const std::string& /*path*/)
{
    throw std::runtime_error("MPCConfig::fromYAML: YAML support not compiled");
}

// ===========================================================================
// Constructor
// ===========================================================================
MPCController::MPCController(const MPCConfig& config, const StepResponseModel& model)
    : config_(config), model_(model), mode_(ControllerMode::AUTO), cycle_count_(0)
{
    int ny = model_.ny();
    int nu = model_.nu();
    int P = config_.layer1.prediction_horizon;
    int M = config_.layer1.control_horizon;

    // Initialize setpoints to zero (deviation variables)
    y_setpoints_ = Eigen::VectorXd::Zero(ny);

    // Build sub-components
    prediction_ = std::make_unique<PredictionEngine>(model_, P, M);
    observer_ = std::make_unique<DisturbanceObserver>(ny);

    // Layer 1: Dynamic QP
    layer1_ = std::make_unique<Layer1DynamicQP>(model_, config_.layer1);

    // Layer 2: Steady-State Target
    layer2_ = std::make_unique<Layer2SSTarget>(model_, config_.layer2);

    // Layer 3: optional
    if (config_.enable_layer3) {
        layer3_ = std::make_unique<Layer3NLP>(
            config_.layer3.codegen_path, config_.layer3);
    }

    // Apply CV/MV constraints from config
    if (!config_.cvs.empty()) {
        Eigen::VectorXd cv_lo(ny), cv_hi(ny), cv_slo(ny), cv_shi(ny);
        for (int i = 0; i < ny && i < static_cast<int>(config_.cvs.size()); ++i) {
            cv_lo[i] = config_.cvs[i].lo_limit;
            cv_hi[i] = config_.cvs[i].hi_limit;
            cv_slo[i] = config_.cvs[i].safety_lo;
            cv_shi[i] = config_.cvs[i].safety_hi;
        }
        layer1_->constraints().setCVOperatingBounds(cv_lo, cv_hi);
        layer1_->constraints().setCVSafetyBounds(cv_slo, cv_shi);
        layer2_->constraints().setCVOperatingBounds(cv_lo, cv_hi);
    }

    if (!config_.mvs.empty()) {
        Eigen::VectorXd mv_lo(nu), mv_hi(nu), du_lo(nu), du_hi(nu);
        for (int i = 0; i < nu && i < static_cast<int>(config_.mvs.size()); ++i) {
            mv_lo[i] = config_.mvs[i].lo_limit;
            mv_hi[i] = config_.mvs[i].hi_limit;
            du_lo[i] = -config_.mvs[i].rate_limit;
            du_hi[i] = config_.mvs[i].rate_limit;
        }
        layer1_->constraints().setMVBounds(mv_lo, mv_hi);
        layer1_->constraints().setMVRateBounds(du_lo, du_hi);
        layer2_->constraints().setMVBounds(mv_lo, mv_hi);
    }

    // Scaling (optional)
    if (!config_.cvs.empty() && !config_.mvs.empty()) {
        Eigen::VectorXd cv_elo(ny), cv_ehi(ny), mv_elo(nu), mv_ehi(nu);
        bool has_ranges = true;
        for (int i = 0; i < ny && i < static_cast<int>(config_.cvs.size()); ++i) {
            cv_elo[i] = config_.cvs[i].engineering_lo;
            cv_ehi[i] = config_.cvs[i].engineering_hi;
            if (cv_ehi[i] <= cv_elo[i]) has_ranges = false;
        }
        for (int i = 0; i < nu && i < static_cast<int>(config_.mvs.size()); ++i) {
            mv_elo[i] = config_.mvs[i].engineering_lo;
            mv_ehi[i] = config_.mvs[i].engineering_hi;
            if (mv_ehi[i] <= mv_elo[i]) has_ranges = false;
        }
        if (has_ranges)
            scaling_ = std::make_unique<Scaling>(cv_elo, cv_ehi, mv_elo, mv_ehi);
    }
}

MPCController MPCController::fromFiles(const std::string& /*config_yaml*/,
                                        const std::string& /*model_hdf5*/)
{
    throw std::runtime_error("fromFiles: YAML/HDF5 loading not compiled");
}

MPCController::~MPCController() = default;

// ===========================================================================
// Main execution loop
// ===========================================================================
MPCController::ControlOutput MPCController::execute(
    const Eigen::VectorXd& y_measured,
    const Eigen::VectorXd& u_current,
    const Eigen::VectorXd& /*dv_values*/)
{
    auto t_start = std::chrono::high_resolution_clock::now();
    spdlog::debug("MPCController::execute cycle={}", cycle_count_);

    int ny = model_.ny();
    int nu = model_.nu();

    ControlOutput out;
    out.du = Eigen::VectorXd::Zero(nu);
    out.u_new = u_current;
    out.layer1_status = SolverStatus::NOT_SOLVED;
    out.layer2_status = SolverStatus::NOT_SOLVED;

    if (mode_ == ControllerMode::MANUAL) {
        // Manual mode: no optimization, just pass through
        out.disturbance = observer_->estimate();
        out.y_predicted = Eigen::VectorXd::Zero(
            config_.layer1.prediction_horizon * ny);

        auto t_end = std::chrono::high_resolution_clock::now();
        out.total_solve_time_ms =
            std::chrono::duration<double, std::milli>(t_end - t_start).count();
        cycle_count_++;
        return out;
    }

    // ---- Step 1: Free response from prediction engine ----
    Eigen::VectorXd y_free = prediction_->freeResponse();

    // ---- Step 2: Disturbance observer ----
    Eigen::VectorXd y_pred_1step = y_free.head(ny);
    Eigen::VectorXd d = observer_->update(y_measured, y_pred_1step);

    // ---- Step 3: Layer 2 -- Steady-state target ----
    auto l2_result = layer2_->solve(y_setpoints_, d);
    out.layer2_status = l2_result.status;
    out.y_ss_target = l2_result.y_ss;
    out.u_ss_target = l2_result.u_ss;

    spdlog::debug("  Layer 2: status={}, obj={:.6f}, time={:.2f}ms",
                  solverStatusStr(l2_result.status), l2_result.objective, l2_result.solve_time_ms);
    if (l2_result.status != SolverStatus::OPTIMAL)
        spdlog::warn("Layer 2 returned {}", solverStatusStr(l2_result.status));

    // Use Layer 2 targets, falling back to setpoints if infeasible
    Eigen::VectorXd y_target = (l2_result.status == SolverStatus::OPTIMAL)
                                ? l2_result.y_ss : y_setpoints_;

    // ---- Step 4: Layer 1 -- Dynamic QP ----
    auto l1_result = layer1_->solve(y_free, y_target, u_current, d);
    out.layer1_status = l1_result.status;
    out.y_predicted = l1_result.y_predicted;

    spdlog::debug("  Layer 1: status={}, obj={:.6f}, iter={}, time={:.2f}ms",
                  solverStatusStr(l1_result.status), l1_result.objective,
                  l1_result.iterations, l1_result.solve_time_ms);
    if (l1_result.status != SolverStatus::OPTIMAL)
        spdlog::warn("Layer 1 returned {}", solverStatusStr(l1_result.status));

    // Extract first move
    out.du = l1_result.du.head(nu);
    out.u_new = u_current + out.du;
    out.disturbance = d;

    // ---- Step 5: Update prediction engine ----
    prediction_->update(y_measured, out.du);

    // ---- Step 6: Warm start for next cycle ----
    layer1_->warmStart(l1_result.du);

    // ---- Diagnostics ----
    auto t_end = std::chrono::high_resolution_clock::now();
    out.total_solve_time_ms =
        std::chrono::duration<double, std::milli>(t_end - t_start).count();

    out.diagnostics.layer1_status = l1_result.status;
    out.diagnostics.layer2_status = l2_result.status;
    out.diagnostics.layer3_status = SolverStatus::NOT_SOLVED;
    out.diagnostics.layer1_solve_ms = l1_result.solve_time_ms;
    out.diagnostics.layer2_solve_ms = l2_result.solve_time_ms;
    out.diagnostics.layer1_iterations = l1_result.iterations;
    out.diagnostics.total_solve_ms = out.total_solve_time_ms;

    spdlog::debug("  Total: {:.2f}ms", out.total_solve_time_ms);

    cycle_count_++;
    return out;
}

// ===========================================================================
// Layer 3 RTO (periodic)
// ===========================================================================
void MPCController::executeRTO(const Eigen::VectorXd& /*plant_state*/)
{
    if (!layer3_) return;
    // Re-linearization would happen here:
    // 1. layer3_->linearizeAt(plant_state, u_current)
    // 2. Generate new step response from linearized model
    // 3. layer2_->updateGainMatrix(new_G)
    // 4. Rebuild Layer 1 dynamic matrix
}

// ===========================================================================
// Online configuration
// ===========================================================================
void MPCController::setSetpoints(const Eigen::VectorXd& y_sp)
{
    y_setpoints_ = y_sp;
}

void MPCController::setSetpoint(int cv_idx, double sp)
{
    y_setpoints_[cv_idx] = sp;
}

void MPCController::setCVBounds(int cv_idx, double lo, double hi)
{
    layer1_->constraints().updateCVOperatingBound(cv_idx, lo, hi);
    layer2_->constraints().updateCVOperatingBound(cv_idx, lo, hi);
}

void MPCController::setMVBounds(int mv_idx, double lo, double hi)
{
    layer1_->constraints().updateMVBound(mv_idx, lo, hi);
    layer2_->constraints().updateMVBound(mv_idx, lo, hi);
}

void MPCController::setMVRateLimit(int mv_idx, double rate)
{
    layer1_->constraints().updateMVRateLimit(mv_idx, rate);
}

void MPCController::setCVWeight(int cv_idx, double weight)
{
    Eigen::VectorXd Q = config_.layer1.cv_weights;
    Q[cv_idx] = weight;
    layer1_->updateWeights(Q, config_.layer1.mv_weights);
    config_.layer1.cv_weights = Q;
}

void MPCController::setMVWeight(int mv_idx, double weight)
{
    Eigen::VectorXd R = config_.layer1.mv_weights;
    R[mv_idx] = weight;
    layer1_->updateWeights(config_.layer1.cv_weights, R);
    config_.layer1.mv_weights = R;
}

void MPCController::setCVConcern(int cv_idx, double concern_lo, double concern_hi)
{
    layer1_->constraints().updateCVConcern(cv_idx, concern_lo, concern_hi);
    layer2_->constraints().updateCVConcern(cv_idx, concern_lo, concern_hi);
    // Concerns affect Hessian -> rebuild Layer 1 QP
    layer1_->updateWeights(config_.layer1.cv_weights, config_.layer1.mv_weights);
}

void MPCController::setCVRank(int cv_idx, int rank_lo, int rank_hi)
{
    layer1_->constraints().updateCVRank(cv_idx, rank_lo, rank_hi);
    layer2_->constraints().updateCVRank(cv_idx, rank_lo, rank_hi);
}

void MPCController::setMVCostRank(int mv_idx, int rank)
{
    layer1_->constraints().updateMVCostRank(mv_idx, rank);
    layer2_->constraints().updateMVCostRank(mv_idx, rank);
}

void MPCController::setMVCost(int mv_idx, double cost)
{
    Eigen::VectorXd costs = config_.layer2.ss_mv_costs;
    if (costs.size() != model_.nu()) {
        costs = Eigen::VectorXd::Zero(model_.nu());
    }
    costs[mv_idx] = cost;
    config_.layer2.ss_mv_costs = costs;
    layer2_->updateCosts(costs);
}

void MPCController::updateGainMatrix(const Eigen::MatrixXd& G)
{
    layer2_->updateGainMatrix(G);
}

void MPCController::enableMV(int /*mv_idx*/, bool /*enabled*/)
{
    // TODO: implement MV enable/disable (set rate limit to 0 when disabled)
}

void MPCController::enableCV(int /*cv_idx*/, bool /*enabled*/)
{
    // TODO: implement CV enable/disable (set weight to 0 when disabled)
}

void MPCController::setMode(ControllerMode mode)
{
    mode_ = mode;
}

// ===========================================================================
// Status & diagnostics
// ===========================================================================
ControllerMode MPCController::mode() const { return mode_; }

ControllerStatus MPCController::status() const
{
    ControllerStatus s;
    s.mode = mode_;
    s.is_running = (mode_ != ControllerMode::MANUAL);
    s.cycle_count = cycle_count_;
    s.total_cvs = model_.ny();
    s.total_mvs = model_.nu();
    s.active_cvs = model_.ny();
    s.active_mvs = model_.nu();
    return s;
}

PerformanceMetrics MPCController::metrics() const
{
    PerformanceMetrics m{};
    m.total_cycles = static_cast<int>(cycle_count_);
    return m;
}

const StepResponseModel& MPCController::model() const { return model_; }
const Storage* MPCController::storage() const { return nullptr; }
int MPCController::ny() const { return model_.ny(); }
int MPCController::nu() const { return model_.nu(); }
int MPCController::ndv() const { return static_cast<int>(config_.dvs.size()); }
int64_t MPCController::cycleCount() const { return cycle_count_; }

}  // namespace azeoapc
