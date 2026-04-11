#include "azeoapc/step_response_model.h"
#include <stdexcept>
#include <cmath>
#include <algorithm>

namespace azeoapc {

StepResponseModel::StepResponseModel(int ny, int nu, int model_horizon, double sample_time)
    : ny_(ny), nu_(nu), N_(model_horizon), dt_(sample_time),
      S_flat_(Eigen::VectorXd::Zero(ny * model_horizon * nu))
{
    if (ny <= 0 || nu <= 0 || model_horizon <= 0 || sample_time <= 0.0)
        throw std::invalid_argument("StepResponseModel: all dimensions and sample_time must be positive");
}

// ---------------------------------------------------------------------------
// Factory: state-space (A,B,C,D) -> step response
// ---------------------------------------------------------------------------
StepResponseModel StepResponseModel::fromStateSpace(
    const Eigen::MatrixXd& A,
    const Eigen::MatrixXd& B,
    const Eigen::MatrixXd& C,
    const Eigen::MatrixXd& D,
    int model_horizon,
    double sample_time)
{
    int nx = A.rows();
    int nu = static_cast<int>(B.cols());
    int ny = static_cast<int>(C.rows());

    if (A.cols() != nx)
        throw std::invalid_argument("fromStateSpace: A must be square");
    if (B.rows() != nx)
        throw std::invalid_argument("fromStateSpace: B row count must match A");
    if (C.cols() != nx)
        throw std::invalid_argument("fromStateSpace: C col count must match A");
    if (D.rows() != ny || D.cols() != nu)
        throw std::invalid_argument("fromStateSpace: D dimensions must be [ny x nu]");

    StepResponseModel model(ny, nu, model_horizon, sample_time);

    // Step response to unit step at k=0:
    //   S[k] = D + C * sum_{j=0}^{k-1} A^j * B    for k = 1..N
    //
    // Stored at index k-1 (0-based): S_stored[k-1] = S[k]
    //
    // Iterative computation:
    //   A_power_B starts as A^0*B = B
    //   cumul accumulates sum of A^j*B

    Eigen::MatrixXd A_power_B = B;                              // A^0 * B
    Eigen::MatrixXd cumul = Eigen::MatrixXd::Zero(nx, nu);     // running sum

    for (int k = 0; k < model_horizon; ++k) {
        cumul += A_power_B;                     // sum_{j=0}^{k} A^j * B
        Eigen::MatrixXd S_k = C * cumul + D;   // [ny x nu]

        for (int cv = 0; cv < ny; ++cv)
            for (int mv = 0; mv < nu; ++mv)
                model.S_flat_[model.flatIndex(cv, k, mv)] = S_k(cv, mv);

        A_power_B = A * A_power_B;              // advance to A^(k+1) * B
    }

    return model;
}

// ---------------------------------------------------------------------------
// Factory: FOPTD (SISO convenience)
// ---------------------------------------------------------------------------
StepResponseModel StepResponseModel::fromFOPTD(
    double gain, double time_constant, double dead_time,
    double sample_time, int model_horizon)
{
    if (time_constant <= 0.0)
        throw std::invalid_argument("fromFOPTD: time_constant must be positive");
    if (dead_time < 0.0)
        throw std::invalid_argument("fromFOPTD: dead_time must be non-negative");

    StepResponseModel model(1, 1, model_horizon, sample_time);

    // Continuous FOPTD: G(s) = K * exp(-Ls) / (tau*s + 1)
    // Step response: y(t) = K * (1 - exp(-(t-L)/tau))  for t > L,  0 otherwise
    //
    // S_stored[k] = step response at time (k+1)*dt

    for (int k = 0; k < model_horizon; ++k) {
        double t = (k + 1) * sample_time;
        double val = 0.0;
        if (t > dead_time)
            val = gain * (1.0 - std::exp(-(t - dead_time) / time_constant));
        model.S_flat_[model.flatIndex(0, k, 0)] = val;
    }

    return model;
}

// ---------------------------------------------------------------------------
// Factory: MIMO FOPTD matrix
// ---------------------------------------------------------------------------
StepResponseModel StepResponseModel::fromFOPTDMatrix(
    const Eigen::MatrixXd& gains,
    const Eigen::MatrixXd& time_constants,
    const Eigen::MatrixXd& dead_times,
    double sample_time, int model_horizon)
{
    int ny = static_cast<int>(gains.rows());
    int nu = static_cast<int>(gains.cols());

    if (time_constants.rows() != ny || time_constants.cols() != nu ||
        dead_times.rows() != ny || dead_times.cols() != nu)
        throw std::invalid_argument("fromFOPTDMatrix: all matrices must have same dimensions");

    StepResponseModel model(ny, nu, model_horizon, sample_time);

    for (int cv = 0; cv < ny; ++cv) {
        for (int mv = 0; mv < nu; ++mv) {
            double K   = gains(cv, mv);
            double tau = time_constants(cv, mv);
            double L   = dead_times(cv, mv);

            for (int k = 0; k < model_horizon; ++k) {
                double t = (k + 1) * sample_time;
                double val = 0.0;
                if (tau > 0.0 && t > L)
                    val = K * (1.0 - std::exp(-(t - L) / tau));
                else if (tau <= 0.0 && t > L)
                    val = K;   // pure gain + dead time
                model.S_flat_[model.flatIndex(cv, k, mv)] = val;
            }
        }
    }

    return model;
}

// ---------------------------------------------------------------------------
// Accessors
// ---------------------------------------------------------------------------
double StepResponseModel::coefficient(int cv, int step, int mv) const
{
    if (cv < 0 || cv >= ny_ || step < 0 || step >= N_ || mv < 0 || mv >= nu_)
        throw std::out_of_range("StepResponseModel::coefficient: index out of range");
    return S_flat_[flatIndex(cv, step, mv)];
}

Eigen::VectorXd StepResponseModel::stepResponse(int cv, int mv) const
{
    Eigen::VectorXd sr(N_);
    for (int k = 0; k < N_; ++k)
        sr[k] = S_flat_[flatIndex(cv, k, mv)];
    return sr;
}

Eigen::MatrixXd StepResponseModel::steadyStateGain() const
{
    return coefficientMatrix(N_ - 1);
}

Eigen::MatrixXd StepResponseModel::coefficientMatrix(int step) const
{
    if (step < 0 || step >= N_)
        throw std::out_of_range("StepResponseModel::coefficientMatrix: step out of range");

    Eigen::MatrixXd S(ny_, nu_);
    for (int cv = 0; cv < ny_; ++cv)
        for (int mv = 0; mv < nu_; ++mv)
            S(cv, mv) = S_flat_[flatIndex(cv, step, mv)];
    return S;
}

// ---------------------------------------------------------------------------
// Prediction helpers
// ---------------------------------------------------------------------------
Eigen::VectorXd StepResponseModel::predictFree(
    const Eigen::MatrixXd& past_moves, int P) const
{
    // past_moves: [N x nu], row 0 = most recent du[k-1]
    //
    // Free response at prediction step j (j=1..P, output index j-1):
    //   y_free[j-1] = sum_{m=1}^{N-j} S_stored[m+j-1] * past_moves.row(m-1)

    Eigen::VectorXd y_free = Eigen::VectorXd::Zero(P * ny_);
    int rows_available = static_cast<int>(past_moves.rows());

    for (int j = 1; j <= P; ++j) {
        int upper = std::min(N_ - j, rows_available);
        if (upper <= 0) continue;

        for (int m = 1; m <= upper; ++m) {
            int s_step = m + j - 1;   // stored index (0-based)
            if (s_step >= N_) break;

            Eigen::MatrixXd S_mat = coefficientMatrix(s_step);  // [ny x nu]
            y_free.segment((j - 1) * ny_, ny_) +=
                S_mat * past_moves.row(m - 1).transpose();
        }
    }

    return y_free;
}

Eigen::VectorXd StepResponseModel::predictForced(
    const Eigen::VectorXd& future_moves, int P, int M) const
{
    // future_moves: [M*nu], stacked [du[k]; du[k+1]; ...; du[k+M-1]]
    //
    // Matches the dynamic matrix (Toeplitz) multiplication:
    //   y_forced[j] = sum_{i=0}^{min(j, M-1)} S_stored[j-i] * du_future[i]
    //
    // j = 0..P-1 (0-indexed output row blocks)
    // i = 0..M-1 (0-indexed move blocks)

    Eigen::VectorXd y_forced = Eigen::VectorXd::Zero(P * ny_);

    for (int j = 0; j < P; ++j) {
        for (int i = 0; i <= std::min(j, M - 1); ++i) {
            int s_step = j - i;
            if (s_step >= N_) continue;

            Eigen::MatrixXd S_mat = coefficientMatrix(s_step);
            y_forced.segment(j * ny_, ny_) +=
                S_mat * future_moves.segment(i * nu_, nu_);
        }
    }

    return y_forced;
}

// ---------------------------------------------------------------------------
// HDF5 serialization (stub -- requires HDF5)
// ---------------------------------------------------------------------------
#ifdef AZEOAPC_HAS_HDF5
StepResponseModel StepResponseModel::fromHDF5(const std::string& /*path*/)
{
    throw std::runtime_error("fromHDF5: not yet implemented");
}

void StepResponseModel::saveHDF5(const std::string& /*path*/) const
{
    throw std::runtime_error("saveHDF5: not yet implemented");
}
#else
StepResponseModel StepResponseModel::fromHDF5(const std::string& /*path*/)
{
    throw std::runtime_error("fromHDF5: HDF5 support not compiled");
}

void StepResponseModel::saveHDF5(const std::string& /*path*/) const
{
    throw std::runtime_error("saveHDF5: HDF5 support not compiled");
}
#endif

// ---------------------------------------------------------------------------
// Metadata
// ---------------------------------------------------------------------------
void StepResponseModel::setCVNames(const std::vector<std::string>& names)
{
    cv_names_ = names;
}

void StepResponseModel::setMVNames(const std::vector<std::string>& names)
{
    mv_names_ = names;
}

}  // namespace azeoapc
