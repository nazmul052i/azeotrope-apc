#include "azeoapc/constraint_handler.h"
#include <algorithm>
#include <stdexcept>
#include <sstream>
#include <cmath>

namespace azeoapc {

ConstraintHandler::ConstraintHandler(int nu, int ny, int M, int P)
    : nu_(nu), ny_(ny), M_(M), P_(P),
      mv_lb_(Eigen::VectorXd::Constant(nu, -1e20)),
      mv_ub_(Eigen::VectorXd::Constant(nu, 1e20)),
      du_lb_(Eigen::VectorXd::Constant(nu, -1e20)),
      du_ub_(Eigen::VectorXd::Constant(nu, 1e20)),
      cv_safety_lb_(Eigen::VectorXd::Constant(ny, -1e20)),
      cv_safety_ub_(Eigen::VectorXd::Constant(ny, 1e20)),
      cv_oper_lb_(Eigen::VectorXd::Constant(ny, -1e20)),
      cv_oper_ub_(Eigen::VectorXd::Constant(ny, 1e20)),
      cv_concern_lo_(Eigen::VectorXd::Constant(ny, 1.0)),
      cv_concern_hi_(Eigen::VectorXd::Constant(ny, 1.0)),
      cv_rank_lo_(Eigen::VectorXi::Constant(ny, 20)),
      cv_rank_hi_(Eigen::VectorXi::Constant(ny, 20)),
      mv_cost_rank_(Eigen::VectorXi::Constant(nu, 0))
{
}

// ---------------------------------------------------------------------------
// Setters: hard constraints
// ---------------------------------------------------------------------------
void ConstraintHandler::setMVBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub)
{
    if (lb.size() != nu_ || ub.size() != nu_)
        throw std::invalid_argument("setMVBounds: size must equal nu");
    mv_lb_ = lb;
    mv_ub_ = ub;
}

void ConstraintHandler::setMVRateBounds(const Eigen::VectorXd& du_lb, const Eigen::VectorXd& du_ub)
{
    if (du_lb.size() != nu_ || du_ub.size() != nu_)
        throw std::invalid_argument("setMVRateBounds: size must equal nu");
    du_lb_ = du_lb;
    du_ub_ = du_ub;
}

void ConstraintHandler::setCVSafetyBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub)
{
    if (lb.size() != ny_ || ub.size() != ny_)
        throw std::invalid_argument("setCVSafetyBounds: size must equal ny");
    cv_safety_lb_ = lb;
    cv_safety_ub_ = ub;
}

void ConstraintHandler::setCVOperatingBounds(const Eigen::VectorXd& lb, const Eigen::VectorXd& ub)
{
    if (lb.size() != ny_ || ub.size() != ny_)
        throw std::invalid_argument("setCVOperatingBounds: size must equal ny");
    cv_oper_lb_ = lb;
    cv_oper_ub_ = ub;
}

// ---------------------------------------------------------------------------
// Setters: soft constraint tuning (concerns and ranks)
// ---------------------------------------------------------------------------
void ConstraintHandler::setCVConcerns(const Eigen::VectorXd& concern_lo,
                                      const Eigen::VectorXd& concern_hi)
{
    if (concern_lo.size() != ny_ || concern_hi.size() != ny_)
        throw std::invalid_argument("setCVConcerns: size must equal ny");
    cv_concern_lo_ = concern_lo;
    cv_concern_hi_ = concern_hi;
}

void ConstraintHandler::setCVRanks(const Eigen::VectorXi& rank_lo,
                                   const Eigen::VectorXi& rank_hi)
{
    if (rank_lo.size() != ny_ || rank_hi.size() != ny_)
        throw std::invalid_argument("setCVRanks: size must equal ny");
    cv_rank_lo_ = rank_lo;
    cv_rank_hi_ = rank_hi;
}

void ConstraintHandler::setMVCostRanks(const Eigen::VectorXi& mv_cost_rank)
{
    if (mv_cost_rank.size() != nu_)
        throw std::invalid_argument("setMVCostRanks: size must equal nu");
    mv_cost_rank_ = mv_cost_rank;
}

// ---------------------------------------------------------------------------
// Online updates
// ---------------------------------------------------------------------------
void ConstraintHandler::updateMVBound(int mv_idx, double lb, double ub)
{
    mv_lb_[mv_idx] = lb;
    mv_ub_[mv_idx] = ub;
}

void ConstraintHandler::updateMVRateLimit(int mv_idx, double rate)
{
    du_lb_[mv_idx] = -rate;
    du_ub_[mv_idx] = rate;
}

void ConstraintHandler::updateCVOperatingBound(int cv_idx, double lb, double ub)
{
    cv_oper_lb_[cv_idx] = lb;
    cv_oper_ub_[cv_idx] = ub;
}

void ConstraintHandler::updateCVSafetyBound(int cv_idx, double lb, double ub)
{
    cv_safety_lb_[cv_idx] = lb;
    cv_safety_ub_[cv_idx] = ub;
}

void ConstraintHandler::updateCVConcern(int cv_idx, double concern_lo, double concern_hi)
{
    cv_concern_lo_[cv_idx] = concern_lo;
    cv_concern_hi_[cv_idx] = concern_hi;
}

void ConstraintHandler::updateCVRank(int cv_idx, int rank_lo, int rank_hi)
{
    cv_rank_lo_[cv_idx] = rank_lo;
    cv_rank_hi_[cv_idx] = rank_hi;
}

void ConstraintHandler::updateMVCostRank(int mv_idx, int rank)
{
    mv_cost_rank_[mv_idx] = rank;
}

// ---------------------------------------------------------------------------
// Build hard QP constraints (legacy, no slack variables)
// ---------------------------------------------------------------------------
static ConstraintHandler::QPConstraints buildHardConstraints(
    const DynamicMatrix& dynmat,
    const Eigen::VectorXd& u_current,
    const Eigen::VectorXd& y_free,
    int nu, int ny, int M, int P,
    const Eigen::VectorXd& du_lb, const Eigen::VectorXd& du_ub,
    const Eigen::VectorXd& mv_lb, const Eigen::VectorXd& mv_ub,
    const Eigen::VectorXd& cv_lb, const Eigen::VectorXd& cv_ub,
    const std::vector<int>& relaxed)
{
    int n_var = M * nu;
    int m_du  = M * nu;
    int m_u   = M * nu;
    int m_cv  = P * ny;
    int m_total = m_du + m_u + m_cv;

    ConstraintHandler::QPConstraints qpc;
    qpc.num_constraints = m_total;
    qpc.n_du = n_var;
    qpc.n_slack = 0;
    qpc.relaxed_priorities = relaxed;

    Eigen::MatrixXd A_dense = Eigen::MatrixXd::Zero(m_total, n_var);
    A_dense.block(0, 0, m_du, n_var) = Eigen::MatrixXd::Identity(m_du, n_var);
    A_dense.block(m_du, 0, m_u, n_var) = dynmat.cumulativeMatrix();
    A_dense.block(m_du + m_u, 0, m_cv, n_var) = dynmat.matrix();

    qpc.A = A_dense.sparseView();
    qpc.A.makeCompressed();

    qpc.lb.resize(m_total);
    qpc.ub.resize(m_total);

    for (int j = 0; j < M; ++j) {
        qpc.lb.segment(j * nu, nu) = du_lb;
        qpc.ub.segment(j * nu, nu) = du_ub;
    }
    for (int j = 0; j < M; ++j) {
        qpc.lb.segment(m_du + j * nu, nu) = mv_lb - u_current;
        qpc.ub.segment(m_du + j * nu, nu) = mv_ub - u_current;
    }
    for (int j = 0; j < P; ++j) {
        qpc.lb.segment(m_du + m_u + j * ny, ny) = cv_lb - y_free.segment(j * ny, ny);
        qpc.ub.segment(m_du + m_u + j * ny, ny) = cv_ub - y_free.segment(j * ny, ny);
    }

    return qpc;
}

ConstraintHandler::QPConstraints ConstraintHandler::buildForQP(
    const DynamicMatrix& dynmat,
    const Eigen::VectorXd& u_current,
    const Eigen::VectorXd& y_free) const
{
    return buildHardConstraints(dynmat, u_current, y_free,
                                nu_, ny_, M_, P_,
                                du_lb_, du_ub_, mv_lb_, mv_ub_,
                                cv_oper_lb_, cv_oper_ub_, {});
}

ConstraintHandler::QPConstraints ConstraintHandler::buildWithRelaxation(
    const DynamicMatrix& dynmat,
    const Eigen::VectorXd& u_current,
    const Eigen::VectorXd& y_free,
    int max_relax_priority) const
{
    if (max_relax_priority < 4) {
        return buildForQP(dynmat, u_current, y_free);
    }
    return buildHardConstraints(dynmat, u_current, y_free,
                                nu_, ny_, M_, P_,
                                du_lb_, du_ub_, mv_lb_, mv_ub_,
                                cv_safety_lb_, cv_safety_ub_, {4});
}

// ---------------------------------------------------------------------------
// Build SOFT QP constraints with slack variables
// ---------------------------------------------------------------------------
//
// Decision vector layout: x = [du (M*nu); s_lo (P*ny); s_hi (P*ny)]
//   - du:    move increments
//   - s_lo:  lower-bound slack (>= 0). y_pred[j] >= cv_lo - s_lo[j]
//   - s_hi:  upper-bound slack (>= 0). y_pred[j] <= cv_hi + s_hi[j]
//
// Constraint structure:
//   Row 0 ..M*nu-1:        I*du in [du_lb, du_ub]                 (rate limits, hard)
//   Row M*nu..2*M*nu-1:    C*du in [mv_lb-u, mv_ub-u]              (MV bounds, hard)
//   Row 2*M*nu..2*M*nu+P*ny-1: A_dyn*du + s_lo >= cv_lo - y_free  (CV lo soft)
//                              i.e. A_dyn*du + s_lo in [cv_lo-y_free, +inf]
//   Row 2*M*nu+P*ny..:     A_dyn*du - s_hi <= cv_hi - y_free      (CV hi soft)
//                              i.e. A_dyn*du - s_hi in [-inf, cv_hi-y_free]
//   Row 2*M*nu+2*P*ny..:   I*s_lo >= 0
//   Row 2*M*nu+3*P*ny..:   I*s_hi >= 0
//
// Total rows: 2*M*nu + 2*P*ny + 2*P*ny = 2*M*nu + 4*P*ny
// Total cols: M*nu + 2*P*ny
ConstraintHandler::QPConstraints ConstraintHandler::buildSoftQP(
    const DynamicMatrix& dynmat,
    const Eigen::VectorXd& u_current,
    const Eigen::VectorXd& y_free) const
{
    const int n_du = M_ * nu_;
    const int n_slack_each = P_ * ny_;
    const int n_var = n_du + 2 * n_slack_each;

    const int m_du   = M_ * nu_;       // rate limits
    const int m_u    = M_ * nu_;       // MV abs limits
    const int m_cvlo = P_ * ny_;       // CV soft lo
    const int m_cvhi = P_ * ny_;       // CV soft hi
    const int m_slo  = P_ * ny_;       // s_lo >= 0
    const int m_shi  = P_ * ny_;       // s_hi >= 0
    const int m_total = m_du + m_u + m_cvlo + m_cvhi + m_slo + m_shi;

    QPConstraints qpc;
    qpc.num_constraints = m_total;
    qpc.n_du = n_du;
    qpc.n_slack = 2 * n_slack_each;

    // Build using triplets for sparsity
    std::vector<Eigen::Triplet<double>> trips;
    trips.reserve(m_du + m_u * nu_ + m_cvlo * (nu_ + 1) + m_cvhi * (nu_ + 1) + m_slo + m_shi);

    int row_offset = 0;

    // ---- Rate limits: I*du ----
    for (int i = 0; i < m_du; ++i)
        trips.emplace_back(row_offset + i, i, 1.0);
    row_offset += m_du;

    // ---- MV abs limits: C*du ----
    const Eigen::MatrixXd& C = dynmat.cumulativeMatrix();
    for (int i = 0; i < m_u; ++i)
        for (int j = 0; j < n_du; ++j)
            if (std::abs(C(i, j)) > 1e-16)
                trips.emplace_back(row_offset + i, j, C(i, j));
    row_offset += m_u;

    // ---- CV lo soft: A_dyn*du + I*s_lo ----
    const Eigen::MatrixXd& A_dyn = dynmat.matrix();
    for (int i = 0; i < m_cvlo; ++i) {
        for (int j = 0; j < n_du; ++j)
            if (std::abs(A_dyn(i, j)) > 1e-16)
                trips.emplace_back(row_offset + i, j, A_dyn(i, j));
        // +I on s_lo column
        trips.emplace_back(row_offset + i, n_du + i, 1.0);
    }
    row_offset += m_cvlo;

    // ---- CV hi soft: A_dyn*du - I*s_hi ----
    for (int i = 0; i < m_cvhi; ++i) {
        for (int j = 0; j < n_du; ++j)
            if (std::abs(A_dyn(i, j)) > 1e-16)
                trips.emplace_back(row_offset + i, j, A_dyn(i, j));
        // -I on s_hi column
        trips.emplace_back(row_offset + i, n_du + n_slack_each + i, -1.0);
    }
    row_offset += m_cvhi;

    // ---- s_lo >= 0 ----
    for (int i = 0; i < m_slo; ++i)
        trips.emplace_back(row_offset + i, n_du + i, 1.0);
    row_offset += m_slo;

    // ---- s_hi >= 0 ----
    for (int i = 0; i < m_shi; ++i)
        trips.emplace_back(row_offset + i, n_du + n_slack_each + i, 1.0);
    row_offset += m_shi;

    qpc.A.resize(m_total, n_var);
    qpc.A.setFromTriplets(trips.begin(), trips.end());
    qpc.A.makeCompressed();

    // ---- Bounds ----
    qpc.lb.resize(m_total);
    qpc.ub.resize(m_total);

    int row = 0;
    // Rate limits
    for (int j = 0; j < M_; ++j) {
        qpc.lb.segment(row + j * nu_, nu_) = du_lb_;
        qpc.ub.segment(row + j * nu_, nu_) = du_ub_;
    }
    row += m_du;

    // MV abs limits
    for (int j = 0; j < M_; ++j) {
        qpc.lb.segment(row + j * nu_, nu_) = mv_lb_ - u_current;
        qpc.ub.segment(row + j * nu_, nu_) = mv_ub_ - u_current;
    }
    row += m_u;

    // CV lo soft: A_dyn*du + s_lo >= cv_lo - y_free
    //   -> bounds [cv_lo - y_free, +inf]
    for (int j = 0; j < P_; ++j) {
        qpc.lb.segment(row + j * ny_, ny_) = cv_oper_lb_ - y_free.segment(j * ny_, ny_);
        qpc.ub.segment(row + j * ny_, ny_) = Eigen::VectorXd::Constant(ny_, 1e20);
    }
    row += m_cvlo;

    // CV hi soft: A_dyn*du - s_hi <= cv_hi - y_free
    //   -> bounds [-inf, cv_hi - y_free]
    for (int j = 0; j < P_; ++j) {
        qpc.lb.segment(row + j * ny_, ny_) = Eigen::VectorXd::Constant(ny_, -1e20);
        qpc.ub.segment(row + j * ny_, ny_) = cv_oper_ub_ - y_free.segment(j * ny_, ny_);
    }
    row += m_cvhi;

    // s_lo >= 0
    qpc.lb.segment(row, m_slo) = Eigen::VectorXd::Zero(m_slo);
    qpc.ub.segment(row, m_slo) = Eigen::VectorXd::Constant(m_slo, 1e20);
    row += m_slo;

    // s_hi >= 0
    qpc.lb.segment(row, m_shi) = Eigen::VectorXd::Zero(m_shi);
    qpc.ub.segment(row, m_shi) = Eigen::VectorXd::Constant(m_shi, 1e20);

    return qpc;
}

// ---------------------------------------------------------------------------
// Feasibility check
// ---------------------------------------------------------------------------
ConstraintHandler::FeasibilityReport ConstraintHandler::checkFeasibility(
    const Eigen::VectorXd& u_current) const
{
    FeasibilityReport report;
    report.feasible = true;
    report.highest_infeasible_priority = 0;

    for (int i = 0; i < nu_; ++i) {
        if (u_current[i] < mv_lb_[i] - 1e-6 || u_current[i] > mv_ub_[i] + 1e-6) {
            report.feasible = false;
            report.highest_infeasible_priority = 1;
            std::ostringstream oss;
            oss << "MV " << i << " value " << u_current[i]
                << " outside bounds [" << mv_lb_[i] << ", " << mv_ub_[i] << "]";
            report.message = oss.str();
            return report;
        }
    }

    report.message = "Feasible";
    return report;
}

}  // namespace azeoapc
