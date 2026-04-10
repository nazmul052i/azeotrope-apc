#pragma once

#include <Eigen/Dense>
#include "azeoapc/types.h"
#include "azeoapc/step_response_model.h"
#include "azeoapc/constraint_handler.h"

namespace azeoapc {

/**
 * Layer 2: Steady-State Target Calculator
 *
 * Finds the optimal steady-state operating point within constraints.
 * Feeds targets to Layer 1.
 *
 * LP mode:
 *   minimize:  c^T * u_ss                        (economic cost)
 *   subject to: y_ss = G * u_ss + d_ss           (SS gain model)
 *               u_min <= u_ss <= u_max
 *               y_min <= y_ss <= y_max            (prioritized soft)
 *
 * QP mode:
 *   minimize:  || y_ss - y_sp ||²_Qs + c^T * u_ss
 *   subject to: same as LP
 *
 * Uses HiGHS for LP, OSQP for QP.
 */

struct Layer2Config {
    Eigen::VectorXd ss_cv_weights;   // Q_s diagonal (tracking importance) [ny]
    Eigen::VectorXd ss_mv_costs;     // c vector (economic costs per MV) [nu]
    bool use_lp;                     // true = LP only, false = QP (tracking + economics)
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

    /// Solve for steady-state target
    Layer2Result solve(
        const Eigen::VectorXd& y_setpoint,    // desired CV setpoints [ny]
        const Eigen::VectorXd& disturbance,   // current disturbance estimate [ny]
        const Eigen::VectorXd& dv_values = {} // current DV values (optional)
    );

    /// Update setpoints online
    void updateSetpoints(const Eigen::VectorXd& y_sp);

    /// Update economic costs online
    void updateCosts(const Eigen::VectorXd& mv_costs);

    /// Update gain matrix (e.g., from Layer 3 re-linearization)
    void updateGainMatrix(const Eigen::MatrixXd& G);

    /// Access constraint handler
    ConstraintHandler& constraints() { return constraints_; }

    /// Current gain matrix
    const Eigen::MatrixXd& gainMatrix() const { return G_; }

private:
    Eigen::MatrixXd G_;              // steady-state gain [ny x nu]
    ConstraintHandler constraints_;
    Layer2Config config_;

    Layer2Result solveLP(const Eigen::VectorXd& y_sp,
                         const Eigen::VectorXd& d);
    Layer2Result solveQP(const Eigen::VectorXd& y_sp,
                         const Eigen::VectorXd& d);
};

}  // namespace azeoapc
