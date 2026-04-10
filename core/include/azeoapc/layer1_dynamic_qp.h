#pragma once

#include <Eigen/Dense>
#include <memory>
#include "azeoapc/types.h"
#include "azeoapc/step_response_model.h"
#include "azeoapc/dynamic_matrix.h"
#include "azeoapc/constraint_handler.h"

namespace azeoapc {

/**
 * Layer 1: Dynamic QP Controller
 *
 * The fast inner loop of MPC. Computes optimal MV moves to track
 * the steady-state targets from Layer 2.
 *
 * minimize:
 *   J = || y_pred - y_target ||²_Q  +  || du ||²_R
 *
 * subject to:
 *   y_pred = y_free + A_dyn * du           (prediction equation)
 *   du_min <= du <= du_max                  (move size limits)
 *   u_min <= u_current + C * du <= u_max   (absolute MV limits)
 *   y_min <= y_pred <= y_max               (CV limits, soft)
 *
 * Uses OSQP with warm-starting for fast sequential solves.
 */

struct Layer1Config {
    int prediction_horizon;          // P
    int control_horizon;             // M
    Eigen::VectorXd cv_weights;      // Q diagonal [ny]
    Eigen::VectorXd mv_weights;      // R diagonal (move suppression) [nu]
};

struct Layer1Result {
    Eigen::VectorXd du;              // optimal moves [M*nu], apply du[0:nu]
    Eigen::VectorXd y_predicted;     // predicted CV trajectory [P*ny]
    SolverStatus status;
    double objective;
    double solve_time_ms;
    int iterations;
    std::vector<int> relaxed_priorities;
};

class Layer1DynamicQP {
public:
    Layer1DynamicQP(const StepResponseModel& model, const Layer1Config& config);
    ~Layer1DynamicQP();

    /// Solve the dynamic QP
    Layer1Result solve(
        const Eigen::VectorXd& y_free,        // free response [P*ny]
        const Eigen::VectorXd& y_target,       // targets from Layer 2 [ny]
        const Eigen::VectorXd& u_current,      // current MV values [nu]
        const Eigen::VectorXd& disturbance     // estimated bias [ny]
    );

    /// Warm-start from previous solution
    void warmStart(const Eigen::VectorXd& du_prev);

    /// Update tuning online
    void updateWeights(const Eigen::VectorXd& Q, const Eigen::VectorXd& R);

    /// Access constraint handler for online updates
    ConstraintHandler& constraints() { return constraints_; }
    const ConstraintHandler& constraints() const { return constraints_; }

    /// Access dynamic matrix
    const DynamicMatrix& dynamicMatrix() const { return dynmat_; }

private:
    StepResponseModel model_;
    DynamicMatrix dynmat_;
    ConstraintHandler constraints_;
    Layer1Config config_;

    // QP matrices (pre-built, updated when weights change)
    Eigen::MatrixXd H_;    // Hessian: A'QA + R
    Eigen::VectorXd g_;    // gradient: -A'Q(y_target - y_free)

    // OSQP workspace
    struct OSQPData;
    std::unique_ptr<OSQPData> osqp_data_;

    void buildQPMatrices();
    void setupOSQP();
};

}  // namespace azeoapc
