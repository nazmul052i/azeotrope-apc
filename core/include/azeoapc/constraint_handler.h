#pragma once

#include <Eigen/Dense>
#include <Eigen/Sparse>
#include <vector>
#include "azeoapc/dynamic_matrix.h"

namespace azeoapc {

/**
 * Constraint Handler
 *
 * Implements prioritized constraint management for industrial MPC.
 *
 * Priority levels:
 *   P1 (highest): MV hard limits (valve range)       -- NEVER relaxed
 *   P2:           MV rate-of-change limits            -- Relaxed only if P1 infeasible
 *   P3:           CV safety limits                    -- Relaxed after P1-P2
 *   P4:           CV operating limits                 -- Relaxed after P1-P3
 *   P5 (lowest):  CV setpoint tracking                -- Always soft (in objective)
 *
 * When constraints make the QP infeasible, lower-priority constraints
 * are sequentially relaxed until a feasible solution is found.
 */
class ConstraintHandler {
public:
    ConstraintHandler(int nu, int ny, int M, int P);

    // ---- Set constraints ----

    /// P1: MV absolute bounds [nu]
    void setMVBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);

    /// P2: MV rate-of-change bounds [nu] (max |du| per step)
    void setMVRateBounds(const Eigen::VectorXd& du_lb, const Eigen::VectorXd& du_ub);

    /// P3: CV safety bounds [ny]
    void setCVSafetyBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);

    /// P4: CV operating bounds [ny]
    void setCVOperatingBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);

    // ---- Build QP constraints ----

    struct QPConstraints {
        Eigen::SparseMatrix<double> A;   // constraint matrix
        Eigen::VectorXd lb;              // lower bounds
        Eigen::VectorXd ub;              // upper bounds
        int num_constraints;
        std::vector<int> relaxed_priorities;  // which levels were relaxed
    };

    /// Build constraint matrices for the QP
    /// u_current: current MV values [nu]
    /// y_free: free response prediction [P*ny]
    /// dynmat: dynamic matrix for output prediction
    QPConstraints buildForQP(
        const DynamicMatrix& dynmat,
        const Eigen::VectorXd& u_current,
        const Eigen::VectorXd& y_free) const;

    /// Build with feasibility check: relax lower priorities if infeasible
    QPConstraints buildWithRelaxation(
        const DynamicMatrix& dynmat,
        const Eigen::VectorXd& u_current,
        const Eigen::VectorXd& y_free,
        int max_relax_priority = 4) const;

    // ---- Online updates ----

    void updateMVBound(int mv_idx, double lb, double ub);
    void updateMVRateLimit(int mv_idx, double rate);
    void updateCVOperatingBound(int cv_idx, double lb, double ub);
    void updateCVSafetyBound(int cv_idx, double lb, double ub);

    // ---- Query ----

    struct FeasibilityReport {
        bool feasible;
        int highest_infeasible_priority;
        std::string message;
    };

    FeasibilityReport checkFeasibility(
        const Eigen::VectorXd& u_current) const;

private:
    int nu_, ny_, M_, P_;

    // P1: MV absolute bounds
    Eigen::VectorXd mv_lb_, mv_ub_;

    // P2: MV rate bounds
    Eigen::VectorXd du_lb_, du_ub_;

    // P3: CV safety bounds
    Eigen::VectorXd cv_safety_lb_, cv_safety_ub_;

    // P4: CV operating bounds
    Eigen::VectorXd cv_oper_lb_, cv_oper_ub_;
};

}  // namespace azeoapc
