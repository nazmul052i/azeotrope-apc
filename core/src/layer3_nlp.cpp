#include "azeoapc/layer3_nlp.h"
#include <stdexcept>
#include <chrono>
#include <cmath>
#include <functional>
#include <spdlog/spdlog.h>

namespace azeoapc {

// ===========================================================================
// Pimpl implementation
// ===========================================================================
struct Layer3NLP::Impl {
    Layer3Config config;
    std::string codegen_path;

    // Stored discrete model function for numerical linearization.
    // f(x, u) -> x_next.  Set via the codegen path or CasADi.
    // For now, numerical linearization uses finite differences
    // on a user-provided discrete model function.
    std::function<Eigen::VectorXd(const Eigen::VectorXd&, const Eigen::VectorXd&)> model_fn;
    int nx = 0;
    int nu = 0;
    int ny = 0;

    bool has_model = false;
};

// ===========================================================================
// Constructors
// ===========================================================================
#ifdef AZEOAPC_HAS_CASADI
Layer3NLP::Layer3NLP(const casadi::Function& /*model*/,
                     const casadi::Function& /*objective*/,
                     const Layer3Config& config)
    : impl_(std::make_unique<Impl>()), config_(config)
{
    impl_->config = config;
    throw std::runtime_error("Layer3NLP: CasADi constructor not yet implemented");
}
#endif

Layer3NLP::Layer3NLP(const std::string& codegen_path, const Layer3Config& config)
    : impl_(std::make_unique<Impl>()), config_(config)
{
    impl_->config = config;
    impl_->codegen_path = codegen_path;
    // The codegen path would load a shared library containing the solver.
    // For now, this prepares the Layer3 for numerical linearization.
}

Layer3NLP::~Layer3NLP() = default;

void Layer3NLP::setModelFunction(
    std::function<Eigen::VectorXd(const Eigen::VectorXd&, const Eigen::VectorXd&)> fn)
{
    impl_->model_fn = std::move(fn);
    impl_->has_model = true;
}

// ===========================================================================
// Solve NLP
// ===========================================================================
Layer3Result Layer3NLP::solve(
    const Eigen::VectorXd& /*x_current*/,
    const Eigen::VectorXd& u_current,
    const Eigen::VectorXd& /*parameters*/)
{
    auto t_start = std::chrono::high_resolution_clock::now();

    Layer3Result result;
    result.u_optimal = u_current;
    result.status = SolverStatus::NOT_SOLVED;

    // NLP solve requires either CasADi or a loaded codegen solver.
    // Without those, return current point as "optimal" (no-op RTO).
    result.status = SolverStatus::OPTIMAL;
    result.objective = 0.0;

    auto t_end = std::chrono::high_resolution_clock::now();
    result.solve_time_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
    return result;
}

// ===========================================================================
// Numerical linearization via finite differences
// ===========================================================================
StateSpaceModel Layer3NLP::linearizeAt(
    const Eigen::VectorXd& x_op,
    const Eigen::VectorXd& u_op)
{
    if (!impl_->has_model)
        throw std::runtime_error("linearizeAt: no model function set. "
                                 "Call setModelFunction() first.");

    spdlog::debug("Layer3 linearizeAt: nx={}, nu={}", x_op.size(), u_op.size());

    int nx = static_cast<int>(x_op.size());
    int nu = static_cast<int>(u_op.size());

    StateSpaceModel ss;

    // Nominal next state
    Eigen::VectorXd x_nom = impl_->model_fn(x_op, u_op);
    int nx_out = static_cast<int>(x_nom.size());

    // A matrix: df/dx via central differences
    ss.A.resize(nx_out, nx);
    for (int j = 0; j < nx; ++j) {
        double eps = std::max(1e-6, std::abs(x_op[j]) * 1e-6);
        Eigen::VectorXd xp = x_op, xm = x_op;
        xp[j] += eps;
        xm[j] -= eps;
        Eigen::VectorXd fp = impl_->model_fn(xp, u_op);
        Eigen::VectorXd fm = impl_->model_fn(xm, u_op);
        ss.A.col(j) = (fp - fm) / (2.0 * eps);
    }

    // B matrix: df/du via central differences
    ss.B.resize(nx_out, nu);
    for (int j = 0; j < nu; ++j) {
        double eps = std::max(1e-6, std::abs(u_op[j]) * 1e-6);
        Eigen::VectorXd up = u_op, um = u_op;
        up[j] += eps;
        um[j] -= eps;
        Eigen::VectorXd fp = impl_->model_fn(x_op, up);
        Eigen::VectorXd fm = impl_->model_fn(x_op, um);
        ss.B.col(j) = (fp - fm) / (2.0 * eps);
    }

    // C = I (all states measured), D = 0
    ss.C = Eigen::MatrixXd::Identity(nx_out, nx_out);
    ss.D = Eigen::MatrixXd::Zero(nx_out, nu);

    spdlog::trace("  A: {}x{}, B: {}x{}", ss.A.rows(), ss.A.cols(), ss.B.rows(), ss.B.cols());

    return ss;
}

// ===========================================================================
// Code generation (requires CasADi)
// ===========================================================================
void Layer3NLP::generateCode(
#ifdef AZEOAPC_HAS_CASADI
    const casadi::Function& /*model*/,
    const casadi::Function& /*objective*/,
#endif
    const std::string& /*output_path*/)
{
    throw std::runtime_error("generateCode: requires CasADi (compile with AZEOAPC_HAS_CASADI)");
}

}  // namespace azeoapc
