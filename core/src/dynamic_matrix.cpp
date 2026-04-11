#include "azeoapc/dynamic_matrix.h"
#include <algorithm>
#include <stdexcept>

namespace azeoapc {

DynamicMatrix::DynamicMatrix(const StepResponseModel& model, int P, int M)
    : P_(P), M_(M), ny_(model.ny()), nu_(model.nu())
{
    if (P <= 0 || M <= 0)
        throw std::invalid_argument("DynamicMatrix: P and M must be positive");
    if (M > P)
        throw std::invalid_argument("DynamicMatrix: control horizon M must be <= prediction horizon P");

    build(model);
}

void DynamicMatrix::build(const StepResponseModel& model)
{
    int rows = P_ * ny_;
    int cols = M_ * nu_;
    int N = model.modelHorizon();

    // ---- Dense dynamic matrix (lower-triangular block Toeplitz) ----
    //
    //   Block (j, i) = S_stored[j-i]   for j >= i  and  j-i < N
    //                = 0               otherwise
    //
    //   j = 0..P-1  (row blocks of size ny)
    //   i = 0..M-1  (col blocks of size nu)

    A_dyn_ = Eigen::MatrixXd::Zero(rows, cols);

    for (int j = 0; j < P_; ++j) {
        for (int i = 0; i <= std::min(j, M_ - 1); ++i) {
            int s_step = j - i;
            if (s_step >= N) continue;

            for (int cv = 0; cv < ny_; ++cv)
                for (int mv = 0; mv < nu_; ++mv)
                    A_dyn_(j * ny_ + cv, i * nu_ + mv) =
                        model.coefficient(cv, s_step, mv);
        }
    }

    // ---- Sparse version ----
    A_sparse_ = A_dyn_.sparseView();
    A_sparse_.makeCompressed();

    // ---- Cumulative move matrix C [M*nu x M*nu] ----
    //
    //   u[k+j] = u[k-1] + sum_{i=0}^{j} du[k+i]
    //   C maps du vector to cumulative absolute moves:
    //     Block (j, i) = I_nu  for i <= j,  0 otherwise

    C_cumul_ = Eigen::MatrixXd::Zero(M_ * nu_, M_ * nu_);

    for (int j = 0; j < M_; ++j)
        for (int i = 0; i <= j; ++i)
            C_cumul_.block(j * nu_, i * nu_, nu_, nu_) =
                Eigen::MatrixXd::Identity(nu_, nu_);
}

void DynamicMatrix::rebuild(const StepResponseModel& model)
{
    ny_ = model.ny();
    nu_ = model.nu();
    build(model);
}

}  // namespace azeoapc
