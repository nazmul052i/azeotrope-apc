#pragma once

#include <Eigen/Dense>
#include <Eigen/Sparse>
#include <vector>
#include "azeoapc/dynamic_matrix.h"

namespace azeoapc {

/**
 * Constraint Handler with DMC3-style concerns and ranks.
 *
 * Hard constraints (always enforced):
 *   - MV bounds [u_min, u_max]
 *   - MV rate limits [du_min, du_max]
 *
 * Soft constraints (enforced via slack variables in objective):
 *   - CV operating limits [y_oper_lo, y_oper_hi]
 *     - Penalty cost: cv_concern_lo[i]^2 * s_lo[i]^2 (and similar for hi)
 *     - Higher concern -> harder constraint (less violation)
 *     - Lower concern -> softer constraint (more violation tolerated)
 *   - CV safety limits [y_safety_lo, y_safety_hi]
 *     - Tighter than operating, used when operating relaxed
 *
 * Per-CV rank (cv_lo_rank, cv_hi_rank):
 *   - Used for sequential constraint relaxation in Layer 2 LP
 *   - Lower rank value = relaxed first
 *
 * Per-MV cost rank (mv_cost_rank):
 *   - Tie-breaker for Layer 2 LP economic optimization
 *   - Higher rank = higher priority for hitting bound
 */
class ConstraintHandler {
public:
    ConstraintHandler(int nu, int ny, int M, int P);

    // ---- Set hard constraints ----

    void setMVBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);
    void setMVRateBounds(const Eigen::VectorXd& du_lb, const Eigen::VectorXd& du_ub);
    void setCVSafetyBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);
    void setCVOperatingBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub);

    // ---- DMC3-style soft constraint tuning ----

    /// Set CV concern values [ny]. Penalty cost = concern^2 per unit slack.
    /// Default = 1.0 (moderate softness). Use 100+ for "near-hard" constraints.
    void setCVConcerns(const Eigen::VectorXd& concern_lo,
                       const Eigen::VectorXd& concern_hi);

    /// Set per-CV rank for relaxation order [ny].
    /// Lower rank value = relaxed first when infeasible.
    void setCVRanks(const Eigen::VectorXi& rank_lo,
                    const Eigen::VectorXi& rank_hi);

    /// Set per-MV cost rank [nu] (priority for economic optimization).
    void setMVCostRanks(const Eigen::VectorXi& mv_cost_rank);

    // ---- Build QP constraints ----

    struct QPConstraints {
        Eigen::SparseMatrix<double> A;   // constraint matrix
        Eigen::VectorXd lb;              // lower bounds
        Eigen::VectorXd ub;              // upper bounds
        int num_constraints;
        int n_du;                        // number of move variables (M*nu)
        int n_slack;                     // number of slack variables (2*P*ny)
        std::vector<int> relaxed_priorities;
    };

    /// Build constraint matrices with soft CV bounds via slack variables.
    /// Decision vector layout: [du (M*nu); s_lo (P*ny); s_hi (P*ny)]
    ///
    /// Constraints:
    ///   du_min <= du <= du_max                              (M*nu rows, hard)
    ///   u_min - u_current <= C*du <= u_max - u_current      (M*nu rows, hard)
    ///   y_oper_lo - y_free <= A_dyn*du + s_lo               (P*ny rows, soft via s_lo)
    ///   A_dyn*du - s_hi <= y_oper_hi - y_free               (P*ny rows, soft via s_hi)
    ///   s_lo, s_hi >= 0                                     (2*P*ny rows, hard)
    QPConstraints buildSoftQP(
        const DynamicMatrix& dynmat,
        const Eigen::VectorXd& u_current,
        const Eigen::VectorXd& y_free) const;

    /// Legacy: hard constraint build (used by tests).
    QPConstraints buildForQP(
        const DynamicMatrix& dynmat,
        const Eigen::VectorXd& u_current,
        const Eigen::VectorXd& y_free) const;

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
    void updateCVConcern(int cv_idx, double concern_lo, double concern_hi);
    void updateCVRank(int cv_idx, int rank_lo, int rank_hi);
    void updateMVCostRank(int mv_idx, int rank);

    // ---- Query ----

    struct FeasibilityReport {
        bool feasible;
        int highest_infeasible_priority;
        std::string message;
    };

    FeasibilityReport checkFeasibility(
        const Eigen::VectorXd& u_current) const;

    // ---- Raw accessors ----
    const Eigen::VectorXd& mvLowerBound() const { return mv_lb_; }
    const Eigen::VectorXd& mvUpperBound() const { return mv_ub_; }
    const Eigen::VectorXd& cvOperLowerBound() const { return cv_oper_lb_; }
    const Eigen::VectorXd& cvOperUpperBound() const { return cv_oper_ub_; }
    const Eigen::VectorXd& cvConcernLo() const { return cv_concern_lo_; }
    const Eigen::VectorXd& cvConcernHi() const { return cv_concern_hi_; }
    const Eigen::VectorXi& cvRankLo() const { return cv_rank_lo_; }
    const Eigen::VectorXi& cvRankHi() const { return cv_rank_hi_; }
    const Eigen::VectorXi& mvCostRank() const { return mv_cost_rank_; }

    int nu() const { return nu_; }
    int ny() const { return ny_; }
    int M() const { return M_; }
    int P() const { return P_; }

private:
    int nu_, ny_, M_, P_;

    Eigen::VectorXd mv_lb_, mv_ub_;
    Eigen::VectorXd du_lb_, du_ub_;
    Eigen::VectorXd cv_safety_lb_, cv_safety_ub_;
    Eigen::VectorXd cv_oper_lb_, cv_oper_ub_;

    // DMC3 soft constraint tuning
    Eigen::VectorXd cv_concern_lo_, cv_concern_hi_;
    Eigen::VectorXi cv_rank_lo_, cv_rank_hi_;
    Eigen::VectorXi mv_cost_rank_;
};

}  // namespace azeoapc
