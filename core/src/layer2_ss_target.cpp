#include "azeoapc/layer2_ss_target.h"
#include <stdexcept>
#include <chrono>
#include <algorithm>
#include <cmath>
#include <spdlog/spdlog.h>

#ifdef AZEOAPC_HAS_HIGHS
#include "Highs.h"
#endif

// Undefine problematic macros
#ifdef MAX_ITER
#undef MAX_ITER
#endif

namespace azeoapc {

// ===========================================================================
// Constructor
// ===========================================================================
Layer2SSTarget::Layer2SSTarget(const StepResponseModel& model, const Layer2Config& config)
    : G_(model.steadyStateGain()),
      constraints_(model.nu(), model.ny(), 1, 1),
      config_(config)
{
}

// ===========================================================================
// Solve dispatch
// ===========================================================================
Layer2Result Layer2SSTarget::solve(
    const Eigen::VectorXd& y_setpoint,
    const Eigen::VectorXd& disturbance,
    const Eigen::VectorXd& /*dv_values*/)
{
    if (config_.use_lp)
        return solveLP(y_setpoint, disturbance);
    else
        return solveQP(y_setpoint, disturbance);
}

// ===========================================================================
// Lexicographic LP solve helper
//
// Solves a sequence of LPs grouped by MV cost rank.
//   Tier 1 (highest rank): solve LP with all MVs free.
//                          Lock MVs that hit a bound.
//   Tier 2: re-solve with locked MVs fixed at their solution.
//   ...
//
// This is the standard DMC3 lexicographic optimization.
// ===========================================================================
struct LpTierResult {
    Eigen::VectorXd u_ss;
    Eigen::VectorXd y_ss;
    SolverStatus status;
    double objective;
};

#ifdef AZEOAPC_HAS_HIGHS
static LpTierResult solveTierLP(
    const Eigen::MatrixXd& G,
    const Eigen::VectorXd& d_eff,
    const Eigen::VectorXd& mv_lo,
    const Eigen::VectorXd& mv_hi,
    const Eigen::VectorXd& cv_lo,
    const Eigen::VectorXd& cv_hi,
    const Eigen::VectorXd& mv_costs,
    const std::vector<bool>& mv_locked,
    const Eigen::VectorXd& mv_locked_values)
{
    int ny = static_cast<int>(G.rows());
    int nu = static_cast<int>(G.cols());
    int n_var = nu + ny;

    LpTierResult res;
    res.u_ss = Eigen::VectorXd::Zero(nu);
    res.y_ss = Eigen::VectorXd::Zero(ny);
    res.status = SolverStatus::NOT_SOLVED;
    res.objective = 0.0;

    Highs highs;
    highs.setOptionValue("output_flag", false);
    highs.setOptionValue("presolve", "on");

    // Column costs: only this tier's MVs have cost
    std::vector<double> col_cost(n_var, 0.0);
    for (int i = 0; i < nu; ++i)
        col_cost[i] = mv_costs[i];

    // Column bounds
    std::vector<double> col_lower(n_var), col_upper(n_var);
    for (int i = 0; i < nu; ++i) {
        if (mv_locked[i]) {
            // Lock at fixed value
            col_lower[i] = mv_locked_values[i];
            col_upper[i] = mv_locked_values[i];
        } else {
            col_lower[i] = mv_lo[i];
            col_upper[i] = mv_hi[i];
        }
    }
    for (int i = 0; i < ny; ++i) {
        col_lower[nu + i] = cv_lo[i];
        col_upper[nu + i] = cv_hi[i];
    }

    // Constraint matrix [G, -I] (equality: G*u - y = -d)
    HighsInt m_row = static_cast<HighsInt>(ny);
    std::vector<HighsInt> a_start, a_index;
    std::vector<double> a_value;

    for (int j = 0; j < nu; ++j) {
        a_start.push_back(static_cast<HighsInt>(a_index.size()));
        for (int i = 0; i < ny; ++i) {
            if (std::abs(G(i, j)) > 1e-16) {
                a_index.push_back(static_cast<HighsInt>(i));
                a_value.push_back(G(i, j));
            }
        }
    }
    for (int j = 0; j < ny; ++j) {
        a_start.push_back(static_cast<HighsInt>(a_index.size()));
        a_index.push_back(static_cast<HighsInt>(j));
        a_value.push_back(-1.0);
    }
    a_start.push_back(static_cast<HighsInt>(a_index.size()));

    std::vector<double> row_lower(ny), row_upper(ny);
    for (int i = 0; i < ny; ++i) {
        row_lower[i] = -d_eff[i];
        row_upper[i] = -d_eff[i];
    }

    highs.addCols(static_cast<HighsInt>(n_var), col_cost.data(),
                  col_lower.data(), col_upper.data(),
                  0, nullptr, nullptr, nullptr);
    highs.addRows(m_row, row_lower.data(), row_upper.data(),
                  static_cast<HighsInt>(a_index.size()),
                  a_start.data(), a_index.data(), a_value.data());

    highs.run();

    HighsModelStatus model_status = highs.getModelStatus();
    const auto& sol = highs.getSolution();

    if (model_status == HighsModelStatus::kOptimal) {
        res.status = SolverStatus::OPTIMAL;
        for (int i = 0; i < nu; ++i) res.u_ss[i] = sol.col_value[i];
        for (int i = 0; i < ny; ++i) res.y_ss[i] = sol.col_value[nu + i];
        double obj_val = 0.0;
        highs.getInfoValue("objective_function_value", obj_val);
        res.objective = obj_val;
    } else if (model_status == HighsModelStatus::kInfeasible) {
        res.status = SolverStatus::INFEASIBLE;
    } else {
        res.status = SolverStatus::NUMERICAL_ERROR;
    }

    return res;
}
#endif

// ===========================================================================
// LP mode: minimize c' * u_ss  subject to  y_ss = G * u_ss + d
// Uses lexicographic ranked LP based on mv_cost_rank.
// ===========================================================================
Layer2Result Layer2SSTarget::solveLP(
    const Eigen::VectorXd& y_sp,
    const Eigen::VectorXd& d)
{
    auto t_start = std::chrono::high_resolution_clock::now();

    int ny = static_cast<int>(G_.rows());
    int nu = static_cast<int>(G_.cols());

    Layer2Result result;
    result.u_ss = Eigen::VectorXd::Zero(nu);
    result.y_ss = Eigen::VectorXd::Zero(ny);
    result.status = SolverStatus::NOT_SOLVED;

#ifdef AZEOAPC_HAS_HIGHS
    Eigen::VectorXd d_eff = (d.size() == ny) ? d : Eigen::VectorXd::Zero(ny);

    // Gather inputs from constraint handler
    Eigen::VectorXd mv_lo = constraints_.mvLowerBound();
    Eigen::VectorXd mv_hi = constraints_.mvUpperBound();
    Eigen::VectorXd cv_lo = constraints_.cvOperLowerBound();
    Eigen::VectorXd cv_hi = constraints_.cvOperUpperBound();
    const Eigen::VectorXi& mv_ranks = constraints_.mvCostRank();

    Eigen::VectorXd costs = Eigen::VectorXd::Zero(nu);
    for (int i = 0; i < nu; ++i)
        costs[i] = config_.ss_mv_costs.size() > i ? config_.ss_mv_costs[i] : 0.0;

    // Group MVs by rank tier (highest rank = solved first)
    std::vector<int> unique_ranks;
    for (int i = 0; i < nu; ++i) {
        if (std::find(unique_ranks.begin(), unique_ranks.end(), mv_ranks[i])
            == unique_ranks.end())
            unique_ranks.push_back(mv_ranks[i]);
    }
    std::sort(unique_ranks.begin(), unique_ranks.end(), std::greater<int>());

    // Lock state across tiers
    std::vector<bool> mv_locked(nu, false);
    Eigen::VectorXd mv_locked_values = Eigen::VectorXd::Zero(nu);

    // Solve each tier sequentially
    Layer2Result tier_result;
    tier_result.status = SolverStatus::OPTIMAL;

    for (size_t tier = 0; tier < unique_ranks.size(); ++tier) {
        int this_rank = unique_ranks[tier];

        // Build cost vector: only this tier's MVs have non-zero cost
        Eigen::VectorXd tier_costs = Eigen::VectorXd::Zero(nu);
        bool any_active = false;
        for (int i = 0; i < nu; ++i) {
            if (!mv_locked[i] && mv_ranks[i] == this_rank) {
                tier_costs[i] = costs[i];
                any_active = true;
            }
        }
        if (!any_active && tier > 0) continue;

        auto tier_lp = solveTierLP(G_, d_eff, mv_lo, mv_hi, cv_lo, cv_hi,
                                   tier_costs, mv_locked, mv_locked_values);

        if (tier_lp.status != SolverStatus::OPTIMAL) {
            // First tier failure -> overall failure
            result.status = tier_lp.status;
            spdlog::warn("Layer 2 LP tier {} (rank={}) failed: status={}",
                         tier, this_rank, static_cast<int>(tier_lp.status));
            break;
        }

        // Lock MVs that hit a bound at this tier (or all this-tier MVs)
        for (int i = 0; i < nu; ++i) {
            if (mv_locked[i]) continue;
            if (mv_ranks[i] == this_rank) {
                mv_locked[i] = true;
                mv_locked_values[i] = tier_lp.u_ss[i];
            }
        }

        result.u_ss = tier_lp.u_ss;
        result.y_ss = tier_lp.y_ss;
        result.objective = tier_lp.objective;
        result.status = SolverStatus::OPTIMAL;
    }

    if (result.status == SolverStatus::NOT_SOLVED) {
        // No tiers ran (all rank values made every MV inactive); do single LP
        std::vector<bool> no_lock(nu, false);
        auto single = solveTierLP(G_, d_eff, mv_lo, mv_hi, cv_lo, cv_hi,
                                  costs, no_lock, mv_locked_values);
        result.u_ss = single.u_ss;
        result.y_ss = single.y_ss;
        result.objective = single.objective;
        result.status = single.status;
    }

#else
    #error "Layer2SSTarget requires HiGHS."
#endif

    auto t_end = std::chrono::high_resolution_clock::now();
    result.solve_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();

    spdlog::trace("HiGHS LP: status={}, obj={:.6f}, time={:.3f}ms",
                  static_cast<int>(result.status), result.objective, result.solve_time_ms);

    return result;
}

// ===========================================================================
// QP mode: minimize ||y_ss - y_sp||^2_Qs + c' * u_ss
// ===========================================================================
Layer2Result Layer2SSTarget::solveQP(
    const Eigen::VectorXd& y_sp,
    const Eigen::VectorXd& d)
{
    auto t_start = std::chrono::high_resolution_clock::now();

    int ny = static_cast<int>(G_.rows());
    int nu = static_cast<int>(G_.cols());
    int n_var = nu + ny;

    Layer2Result result;
    result.u_ss = Eigen::VectorXd::Zero(nu);
    result.y_ss = Eigen::VectorXd::Zero(ny);
    result.status = SolverStatus::NOT_SOLVED;

    // QP mode uses direct KKT solve (system is small: nu+ny variables).
    //
    // minimize  0.5 * y_ss' * Qs * y_ss - y_sp' * Qs * y_ss + c' * u_ss
    // subject to  y_ss = G * u_ss + d
    //
    // Substituting the equality constraint:
    //   y_ss = G * u_ss + d
    //   J(u) = 0.5*(G*u+d)'*Qs*(G*u+d) - y_sp'*Qs*(G*u+d) + c'*u
    //   dJ/du = G'*Qs*(G*u+d) - G'*Qs*y_sp + c = 0
    //   G'*Qs*G*u = G'*Qs*(y_sp - d) - c
    //   u_ss = (G'*Qs*G)^{-1} * (G'*Qs*(y_sp - d) - c)

    Eigen::VectorXd d_eff = (d.size() == ny) ? d : Eigen::VectorXd::Zero(ny);

    // Build Qs diagonal matrix
    Eigen::VectorXd qs_diag(ny);
    for (int i = 0; i < ny; ++i)
        qs_diag[i] = config_.ss_cv_weights.size() > i ? config_.ss_cv_weights[i] : 1.0;
    Eigen::MatrixXd Qs = qs_diag.asDiagonal();

    // Economic cost vector
    Eigen::VectorXd c_vec = Eigen::VectorXd::Zero(nu);
    for (int i = 0; i < nu; ++i)
        c_vec[i] = config_.ss_mv_costs.size() > i ? config_.ss_mv_costs[i] : 0.0;

    // Solve: (G'*Qs*G) * u_ss = G'*Qs*(y_sp - d) - c
    Eigen::MatrixXd GtQsG = G_.transpose() * Qs * G_;
    Eigen::VectorXd rhs = G_.transpose() * Qs * (y_sp - d_eff) - c_vec;

    // Use robust solve (pseudoinverse for singular systems)
    Eigen::JacobiSVD<Eigen::MatrixXd> svd(GtQsG, Eigen::ComputeThinU | Eigen::ComputeThinV);
    result.u_ss = svd.solve(rhs);
    result.y_ss = G_ * result.u_ss + d_eff;
    result.status = SolverStatus::OPTIMAL;
    result.objective = 0.5 * (result.y_ss - y_sp).transpose() * Qs * (result.y_ss - y_sp)
                       + c_vec.dot(result.u_ss);

    auto t_end = std::chrono::high_resolution_clock::now();
    result.solve_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();

    spdlog::trace("Layer2 QP: obj={:.6f}, time={:.3f}ms", result.objective, result.solve_time_ms);

    return result;
}

// ===========================================================================
// Online updates
// ===========================================================================
void Layer2SSTarget::updateSetpoints(const Eigen::VectorXd& /*y_sp*/)
{
    // Setpoints are passed to solve() directly; nothing to store here.
}

void Layer2SSTarget::updateCosts(const Eigen::VectorXd& mv_costs)
{
    config_.ss_mv_costs = mv_costs;
}

void Layer2SSTarget::updateGainMatrix(const Eigen::MatrixXd& G)
{
    G_ = G;
}

}  // namespace azeoapc
