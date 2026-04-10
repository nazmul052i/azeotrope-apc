#pragma once

#include <Eigen/Dense>
#include <string>
#include <memory>
#include "azeoapc/types.h"

#ifdef AZEOAPC_HAS_CASADI
#include <casadi/casadi.hpp>
#endif

namespace azeoapc {

/**
 * Layer 3: Nonlinear Optimizer (CasADi / IPOPT)
 *
 * The slow outer loop -- performs Real-Time Optimization (RTO) or
 * nonlinear MPC when the plant operates far from the linear region.
 *
 * Two modes:
 *   1. CasADi C++ API: builds NLP at runtime (requires CasADi)
 *   2. Code-generated: loads pre-compiled solver .so (no CasADi needed)
 *
 * CasADi code generation workflow:
 *   Builder (offline): CasADi C++ → define NLP → generate C code → compile .so
 *   Runtime (online):  Load .so → solve → no CasADi dependency
 */

struct Layer3Config {
    std::string model_source;          // "casadi" or "codegen"
    std::string codegen_path;          // path to .so/.dll (codegen mode)
    double execution_interval_sec;     // how often to run (e.g., 3600)
    int nlp_max_iter;
    double nlp_tolerance;
};

struct StateSpaceModel {
    Eigen::MatrixXd A, B, C, D;
};

struct Layer3Result {
    Eigen::VectorXd u_optimal;         // economically optimal MVs
    Eigen::VectorXd y_optimal;         // predicted CVs at optimum
    StateSpaceModel linearized;        // re-linearized model at optimum
    Eigen::MatrixXd updated_gain;      // new G matrix for Layer 2
    SolverStatus status;
    double objective;
    double solve_time_ms;
};

class Layer3NLP {
public:
#ifdef AZEOAPC_HAS_CASADI
    /// Build NLP from CasADi function objects
    Layer3NLP(const casadi::Function& model,
              const casadi::Function& objective,
              const Layer3Config& config);
#endif

    /// Load code-generated solver (no CasADi dependency)
    Layer3NLP(const std::string& codegen_path, const Layer3Config& config);

    ~Layer3NLP();

    /// Solve NLP
    Layer3Result solve(
        const Eigen::VectorXd& x_current,      // current state estimate
        const Eigen::VectorXd& u_current,       // current MVs
        const Eigen::VectorXd& parameters = {}  // model parameters
    );

    /// Re-linearize nonlinear model at operating point
    /// Returns (A,B,C,D) for updating Layer 2 gain matrix
    StateSpaceModel linearizeAt(const Eigen::VectorXd& x_op,
                                 const Eigen::VectorXd& u_op);

    /// Generate C code for the NLP solver (offline, in Builder)
    static void generateCode(
#ifdef AZEOAPC_HAS_CASADI
        const casadi::Function& model,
        const casadi::Function& objective,
#endif
        const std::string& output_path);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    Layer3Config config_;
};

}  // namespace azeoapc
