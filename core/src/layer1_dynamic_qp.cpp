#include "azeoapc/layer1_dynamic_qp.h"
#include <stdexcept>
#include <chrono>
#include <algorithm>
#include <spdlog/spdlog.h>

#ifdef AZEOAPC_HAS_OSQP
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "osqp.h"
#ifdef MAX_ITER
#undef MAX_ITER
#endif
#ifdef max
#undef max
#endif
#ifdef min
#undef min
#endif
#endif

namespace azeoapc {

// ===========================================================================
// OSQP pimpl wrapper
// ===========================================================================
struct Layer1DynamicQP::OSQPData {
#ifdef AZEOAPC_HAS_OSQP
    OSQPWorkspace* work = nullptr;

    std::vector<c_float> P_x;
    std::vector<c_int>   P_i, P_p;
    std::vector<c_float> A_x;
    std::vector<c_int>   A_i, A_p;
    std::vector<c_float> q_vec;
    std::vector<c_float> l_vec, u_vec;

    int n_var = 0;       // total decision vars (M*nu + 2*P*ny)
    int n_du = 0;        // move vars only (M*nu)
    int m_con = 0;

    ~OSQPData() {
        if (work) osqp_cleanup(work);
    }
#endif
};

#ifdef AZEOAPC_HAS_OSQP
static void eigenToCSC(const Eigen::SparseMatrix<double>& mat,
                       std::vector<c_float>& values,
                       std::vector<c_int>& row_indices,
                       std::vector<c_int>& col_pointers)
{
    Eigen::SparseMatrix<double> cmat = mat;
    cmat.makeCompressed();

    int nnz  = static_cast<int>(cmat.nonZeros());
    int cols = static_cast<int>(cmat.cols());

    values.resize(nnz);
    row_indices.resize(nnz);
    col_pointers.resize(cols + 1);

    for (int k = 0; k < nnz; ++k) {
        values[k]      = static_cast<c_float>(cmat.valuePtr()[k]);
        row_indices[k] = static_cast<c_int>(cmat.innerIndexPtr()[k]);
    }
    for (int k = 0; k <= cols; ++k) {
        col_pointers[k] = static_cast<c_int>(cmat.outerIndexPtr()[k]);
    }
}

static Eigen::SparseMatrix<double> upperTriangular(const Eigen::MatrixXd& H)
{
    int n = static_cast<int>(H.rows());
    Eigen::SparseMatrix<double> Hut(n, n);
    std::vector<Eigen::Triplet<double>> triplets;
    triplets.reserve(n * (n + 1) / 2);
    for (int j = 0; j < n; ++j)
        for (int i = 0; i <= j; ++i)
            if (std::abs(H(i, j)) > 1e-16)
                triplets.emplace_back(i, j, H(i, j));
    Hut.setFromTriplets(triplets.begin(), triplets.end());
    Hut.makeCompressed();
    return Hut;
}
#endif

// ===========================================================================
// Constructor / Destructor
// ===========================================================================
Layer1DynamicQP::Layer1DynamicQP(const StepResponseModel& model, const Layer1Config& config)
    : model_(model),
      dynmat_(model, config.prediction_horizon, config.control_horizon),
      constraints_(model.nu(), model.ny(), config.control_horizon, config.prediction_horizon),
      config_(config),
      osqp_data_(std::make_unique<OSQPData>())
{
    buildQPMatrices();
    setupOSQP();
}

Layer1DynamicQP::~Layer1DynamicQP() = default;

// ===========================================================================
// Build augmented Hessian H with slack variables
// ===========================================================================
//
// Decision vector: x = [du (M*nu); s_lo (P*ny); s_hi (P*ny)]
//
// Objective:
//   J = 0.5 * du' * (A_dyn'*Q*A_dyn + R) * du + g'*du
//     + 0.5 * s_lo' * diag(2*concern_lo^2) * s_lo
//     + 0.5 * s_hi' * diag(2*concern_hi^2) * s_hi
//
// (Factor of 2 because OSQP uses min 0.5*x'*P*x + q'*x form, so to get
//  penalty = concern^2 * s^2 we need P diagonal entry = 2*concern^2)
//
// Hessian H = block_diag(H_du, W_lo, W_hi)
//   H_du = A_dyn'*Q*A_dyn + R     (M*nu x M*nu)
//   W_lo = diag(2 * concern_lo^2)  (P*ny x P*ny)
//   W_hi = diag(2 * concern_hi^2)  (P*ny x P*ny)
// ===========================================================================
void Layer1DynamicQP::buildQPMatrices()
{
    int P  = config_.prediction_horizon;
    int M  = config_.control_horizon;
    int ny = model_.ny();
    int nu = model_.nu();

    int n_du    = M * nu;
    int n_slack = P * ny;
    int n_var   = n_du + 2 * n_slack;

    // Q diagonal: tracking weight per CV per step
    Eigen::VectorXd Q_vec(P * ny);
    for (int j = 0; j < P; ++j)
        Q_vec.segment(j * ny, ny) = config_.cv_weights;

    // R diagonal: move suppression
    Eigen::VectorXd R_vec(M * nu);
    for (int j = 0; j < M; ++j)
        R_vec.segment(j * nu, nu) = config_.mv_weights;

    const Eigen::MatrixXd& A_dyn = dynmat_.matrix();

    // H_du = A_dyn' * Q * A_dyn + R
    Eigen::MatrixXd H_du = A_dyn.transpose() * Q_vec.asDiagonal() * A_dyn
                           + Eigen::MatrixXd(R_vec.asDiagonal());

    // Slack penalty diagonal: 2 * concern^2 (repeated P times)
    Eigen::VectorXd W_lo_vec(n_slack);
    Eigen::VectorXd W_hi_vec(n_slack);
    const Eigen::VectorXd& cl = constraints_.cvConcernLo();
    const Eigen::VectorXd& ch = constraints_.cvConcernHi();
    for (int j = 0; j < P; ++j) {
        for (int i = 0; i < ny; ++i) {
            W_lo_vec[j * ny + i] = 2.0 * cl[i] * cl[i];
            W_hi_vec[j * ny + i] = 2.0 * ch[i] * ch[i];
        }
    }

    // Assemble block-diagonal H
    H_ = Eigen::MatrixXd::Zero(n_var, n_var);
    H_.block(0, 0, n_du, n_du) = H_du;
    for (int i = 0; i < n_slack; ++i) {
        H_(n_du + i, n_du + i) = W_lo_vec[i];
        H_(n_du + n_slack + i, n_du + n_slack + i) = W_hi_vec[i];
    }

    g_.resize(n_var);
    g_.setZero();
}

// ===========================================================================
// OSQP setup
// ===========================================================================
void Layer1DynamicQP::setupOSQP()
{
#ifdef AZEOAPC_HAS_OSQP
    int P  = config_.prediction_horizon;
    int M  = config_.control_horizon;
    int ny = model_.ny();
    int nu = model_.nu();

    int n_du    = M * nu;
    int n_slack = P * ny;
    int n_var   = n_du + 2 * n_slack;

    // Build a dummy soft QP constraint set to determine structure
    Eigen::VectorXd u_dummy = Eigen::VectorXd::Zero(nu);
    Eigen::VectorXd y_dummy = Eigen::VectorXd::Zero(P * ny);
    auto qpc = constraints_.buildSoftQP(dynmat_, u_dummy, y_dummy);

    int m_con = qpc.num_constraints;

    osqp_data_->n_var = n_var;
    osqp_data_->n_du = n_du;
    osqp_data_->m_con = m_con;

    // Convert H to upper-triangular CSC
    Eigen::SparseMatrix<double> H_ut = upperTriangular(H_);
    eigenToCSC(H_ut, osqp_data_->P_x, osqp_data_->P_i, osqp_data_->P_p);

    // Convert constraint matrix to CSC
    eigenToCSC(qpc.A, osqp_data_->A_x, osqp_data_->A_i, osqp_data_->A_p);

    // Initial gradient (zeros)
    osqp_data_->q_vec.assign(n_var, 0.0);

    // Initial bounds
    osqp_data_->l_vec.resize(m_con);
    osqp_data_->u_vec.resize(m_con);
    for (int i = 0; i < m_con; ++i) {
        osqp_data_->l_vec[i] = static_cast<c_float>(qpc.lb[i]);
        osqp_data_->u_vec[i] = static_cast<c_float>(qpc.ub[i]);
    }

    // Allocate OSQP data struct
    ::OSQPData* data = static_cast<::OSQPData*>(c_malloc(sizeof(::OSQPData)));
    data->n = static_cast<c_int>(n_var);
    data->m = static_cast<c_int>(m_con);
    data->P = csc_matrix(
        data->n, data->n,
        static_cast<c_int>(osqp_data_->P_x.size()),
        osqp_data_->P_x.data(),
        osqp_data_->P_i.data(),
        osqp_data_->P_p.data());
    data->q = osqp_data_->q_vec.data();
    data->A = csc_matrix(
        data->m, data->n,
        static_cast<c_int>(osqp_data_->A_x.size()),
        osqp_data_->A_x.data(),
        osqp_data_->A_i.data(),
        osqp_data_->A_p.data());
    data->l = osqp_data_->l_vec.data();
    data->u = osqp_data_->u_vec.data();

    OSQPSettings* settings = static_cast<OSQPSettings*>(c_malloc(sizeof(OSQPSettings)));
    osqp_set_default_settings(settings);
    settings->verbose = 0;
    settings->warm_start = 1;
    settings->polish = 1;
    settings->eps_abs = 1e-6;
    settings->eps_rel = 1e-6;
    settings->max_iter = 4000;

    c_int status = osqp_setup(&osqp_data_->work, data, settings);

    if (data->P) c_free(data->P);
    if (data->A) c_free(data->A);
    c_free(data);
    c_free(settings);

    if (status != 0)
        throw std::runtime_error("Layer1DynamicQP: OSQP setup failed with code "
                                 + std::to_string(status));
#endif
}

// ===========================================================================
// Solve
// ===========================================================================
Layer1Result Layer1DynamicQP::solve(
    const Eigen::VectorXd& y_free,
    const Eigen::VectorXd& y_target,
    const Eigen::VectorXd& u_current,
    const Eigen::VectorXd& disturbance)
{
    auto t_start = std::chrono::high_resolution_clock::now();

    int P  = config_.prediction_horizon;
    int M  = config_.control_horizon;
    int ny = model_.ny();
    int nu = model_.nu();
    int n_du = M * nu;
    int n_slack = P * ny;
    int n_var = n_du + 2 * n_slack;

    Layer1Result result;
    result.du = Eigen::VectorXd::Zero(n_du);
    result.y_predicted = Eigen::VectorXd::Zero(P * ny);
    result.status = SolverStatus::NOT_SOLVED;
    result.objective = 0.0;
    result.iterations = 0;

    // Build Q diagonal
    Eigen::VectorXd Q_vec(P * ny);
    for (int j = 0; j < P; ++j)
        Q_vec.segment(j * ny, ny) = config_.cv_weights;

    // Build target/disturbance vectors (repeated P times)
    Eigen::VectorXd y_target_rep(P * ny);
    Eigen::VectorXd d_rep(P * ny);
    for (int j = 0; j < P; ++j) {
        y_target_rep.segment(j * ny, ny) = y_target;
        d_rep.segment(j * ny, ny) = disturbance;
    }

    // Tracking error
    Eigen::VectorXd error = y_target_rep - y_free - d_rep;

    // Gradient for du portion: g_du = -A_dyn' * Q * error
    const Eigen::MatrixXd& A_dyn = dynmat_.matrix();
    Eigen::VectorXd g_du = -A_dyn.transpose() * Q_vec.asDiagonal() * error;

    // Full gradient (slack vars have zero linear term)
    g_.setZero();
    g_.head(n_du) = g_du;

    // y_free including disturbance for constraint construction
    Eigen::VectorXd y_free_with_d = y_free + d_rep;

    // Build SOFT QP constraints (with slack variables)
    auto qpc = constraints_.buildSoftQP(dynmat_, u_current, y_free_with_d);
    result.relaxed_priorities = qpc.relaxed_priorities;

#ifdef AZEOAPC_HAS_OSQP
    if (!osqp_data_->work)
        throw std::runtime_error("Layer1DynamicQP::solve: OSQP workspace not initialized");

    std::vector<c_float> q_new(n_var);
    for (int i = 0; i < n_var; ++i)
        q_new[i] = static_cast<c_float>(g_[i]);

    std::vector<c_float> l_new(qpc.num_constraints);
    std::vector<c_float> u_new(qpc.num_constraints);
    for (int i = 0; i < qpc.num_constraints; ++i) {
        l_new[i] = static_cast<c_float>(qpc.lb[i]);
        u_new[i] = static_cast<c_float>(qpc.ub[i]);
    }

    osqp_update_lin_cost(osqp_data_->work, q_new.data());
    osqp_update_bounds(osqp_data_->work, l_new.data(), u_new.data());

    c_int solve_status = osqp_solve(osqp_data_->work);
    (void)solve_status;

    auto* sol = osqp_data_->work->solution;
    auto* info = osqp_data_->work->info;

    result.objective = static_cast<double>(info->obj_val);
    result.iterations = static_cast<int>(info->iter);

    bool valid_solution = false;
    switch (info->status_val) {
        case OSQP_SOLVED:
        case OSQP_SOLVED_INACCURATE:
            result.status = SolverStatus::OPTIMAL;
            valid_solution = true;
            break;
        case OSQP_PRIMAL_INFEASIBLE:
        case OSQP_PRIMAL_INFEASIBLE_INACCURATE:
        case OSQP_DUAL_INFEASIBLE:
        case OSQP_DUAL_INFEASIBLE_INACCURATE:
            result.status = SolverStatus::INFEASIBLE;
            break;
        case OSQP_MAX_ITER_REACHED:
            result.status = SolverStatus::MAX_ITER;
            valid_solution = true;
            break;
        default:
            result.status = SolverStatus::NUMERICAL_ERROR;
            break;
    }

    if (valid_solution) {
        // Extract du from first n_du entries
        for (int i = 0; i < n_du; ++i)
            result.du[i] = static_cast<double>(sol->x[i]);

        // Track which CVs got relaxed (slack > tolerance)
        const double slack_tol = 1e-4;
        for (int j = 0; j < P; ++j) {
            for (int i = 0; i < ny; ++i) {
                double s_lo = static_cast<double>(sol->x[n_du + j * ny + i]);
                double s_hi = static_cast<double>(sol->x[n_du + n_slack + j * ny + i]);
                if (s_lo > slack_tol || s_hi > slack_tol) {
                    // Mark CV as relaxed (use index encoding: i + 100*priority)
                    if (std::find(result.relaxed_priorities.begin(),
                                  result.relaxed_priorities.end(), i)
                        == result.relaxed_priorities.end()) {
                        result.relaxed_priorities.push_back(i);
                    }
                }
            }
        }
    } else {
        result.du.setZero();
    }

#else
#error "Layer1DynamicQP requires OSQP. Ensure OSQP is available."
#endif

    // Predicted output
    result.y_predicted = y_free + A_dyn * result.du + d_rep;

    auto t_end = std::chrono::high_resolution_clock::now();
    result.solve_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();

    spdlog::trace("OSQP soft QP: status={}, iter={}, obj={:.6f}, n_var={}, m={}, time={:.3f}ms",
                  static_cast<int>(result.status), result.iterations,
                  result.objective, n_var, qpc.num_constraints,
                  result.solve_time_ms);

    return result;
}

// ===========================================================================
// Warm start
// ===========================================================================
void Layer1DynamicQP::warmStart(const Eigen::VectorXd& du_prev)
{
#ifdef AZEOAPC_HAS_OSQP
    if (!osqp_data_->work) return;

    int n_var = osqp_data_->n_var;
    int n_du = osqp_data_->n_du;
    std::vector<c_float> x_warm(n_var, 0.0);

    int nu = model_.nu();
    int M  = config_.control_horizon;
    int prev_size = static_cast<int>(du_prev.size());

    // Shift previous moves: position j gets value from j+1
    for (int j = 0; j < M - 1; ++j)
        for (int i = 0; i < nu; ++i) {
            int src = (j + 1) * nu + i;
            if (src < prev_size)
                x_warm[j * nu + i] = static_cast<c_float>(du_prev[src]);
        }
    // Slack variables warm-started to zero (already done by init)

    osqp_warm_start_x(osqp_data_->work, x_warm.data());
#else
    (void)du_prev;
#endif
}

// ===========================================================================
// Update weights (and concerns -- triggers full rebuild)
// ===========================================================================
void Layer1DynamicQP::updateWeights(const Eigen::VectorXd& Q, const Eigen::VectorXd& R)
{
    config_.cv_weights = Q;
    config_.mv_weights = R;

    buildQPMatrices();

#ifdef AZEOAPC_HAS_OSQP
    if (osqp_data_->work) {
        osqp_cleanup(osqp_data_->work);
        osqp_data_->work = nullptr;
    }
    setupOSQP();
#endif
}

}  // namespace azeoapc
