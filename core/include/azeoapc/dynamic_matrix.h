#pragma once

#include <Eigen/Dense>
#include <Eigen/Sparse>
#include "azeoapc/step_response_model.h"

namespace azeoapc {

/**
 * Dynamic Matrix
 *
 * Builds the lower-triangular Toeplitz prediction matrix from step response
 * coefficients. This is the "Dynamic Matrix" in Dynamic Matrix Control.
 *
 * A_dyn = | S[1]    0      0    ... 0       |    size: (P*ny) x (M*nu)
 *         | S[2]    S[1]   0    ... 0       |
 *         | S[3]    S[2]   S[1] ... 0       |
 *         | ...     ...    ...  ... ...     |
 *         | S[P]    S[P-1] ...  ... S[P-M+1]|
 *
 * Also builds the cumulative move matrix C for absolute MV constraints:
 *   u[k+j] = u[k-1] + C * du
 */
class DynamicMatrix {
public:
    DynamicMatrix(const StepResponseModel& model, int P, int M);

    /// Dense dynamic matrix A_dyn [P*ny x M*nu]
    const Eigen::MatrixXd& matrix() const { return A_dyn_; }

    /// Sparse version for QP solver
    const Eigen::SparseMatrix<double>& sparse() const { return A_sparse_; }

    /// Cumulative move matrix C [M*nu x M*nu]
    /// Lower-triangular identity blocks: u[k+j] = u[k-1] + sum_{i=0}^{j} du[k+i]
    const Eigen::MatrixXd& cumulativeMatrix() const { return C_cumul_; }

    int predictionHorizon() const { return P_; }
    int controlHorizon() const { return M_; }
    int ny() const { return ny_; }
    int nu() const { return nu_; }

    /// Rebuild matrix (e.g., after model update from Layer 3)
    void rebuild(const StepResponseModel& model);

private:
    int P_;     // prediction horizon
    int M_;     // control horizon
    int ny_;    // CV count
    int nu_;    // MV count

    Eigen::MatrixXd A_dyn_;
    Eigen::SparseMatrix<double> A_sparse_;
    Eigen::MatrixXd C_cumul_;

    void build(const StepResponseModel& model);
};

}  // namespace azeoapc
