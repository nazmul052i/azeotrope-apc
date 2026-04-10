#pragma once

#include <Eigen/Dense>
#include <string>
#include <vector>

namespace azeoapc {

/**
 * Step Response Model (FIR)
 *
 * Stores the step response coefficients S[ny][N][nu] that define the
 * dynamic relationship between MV step changes and CV responses.
 *
 * y[k] = sum_{i=1}^{N} S[i] * delta_u[k-i] + d[k]
 *
 * For MIMO systems, S is a 3D array where S(cv, step, mv) gives the
 * response of CV 'cv' at time step 'step' to a unit step in MV 'mv'.
 */
class StepResponseModel {
public:
    StepResponseModel(int ny, int nu, int model_horizon, double sample_time);

    // ---- Factory methods ----

    /// Load from HDF5 file
    static StepResponseModel fromHDF5(const std::string& path);

    /// Convert state-space (A,B,C,D) to step response
    static StepResponseModel fromStateSpace(
        const Eigen::MatrixXd& A,
        const Eigen::MatrixXd& B,
        const Eigen::MatrixXd& C,
        const Eigen::MatrixXd& D,
        int model_horizon,
        double sample_time);

    /// Create from first-order plus dead time parameters (SISO convenience)
    static StepResponseModel fromFOPTD(
        double gain, double time_constant, double dead_time,
        double sample_time, int model_horizon);

    /// Create MIMO from vector of FOPTD parameters
    static StepResponseModel fromFOPTDMatrix(
        const Eigen::MatrixXd& gains,
        const Eigen::MatrixXd& time_constants,
        const Eigen::MatrixXd& dead_times,
        double sample_time, int model_horizon);

    // ---- Accessors ----

    int ny() const { return ny_; }
    int nu() const { return nu_; }
    int modelHorizon() const { return N_; }
    double sampleTime() const { return dt_; }

    /// Get single coefficient S(cv, step, mv)
    double coefficient(int cv, int step, int mv) const;

    /// Get full step response vector for one CV-MV pair [N x 1]
    Eigen::VectorXd stepResponse(int cv, int mv) const;

    /// Get steady-state gain matrix G = S[:, N-1, :], shape [ny x nu]
    Eigen::MatrixXd steadyStateGain() const;

    /// Get step response coefficient matrix at a given time step [ny x nu]
    Eigen::MatrixXd coefficientMatrix(int step) const;

    // ---- Prediction ----

    /// Free response: predicted output trajectory if no future moves
    /// past_moves: [N x nu] matrix of past delta_u values (newest first)
    /// P: prediction horizon
    /// Returns: [P * ny] vector
    Eigen::VectorXd predictFree(const Eigen::MatrixXd& past_moves, int P) const;

    /// Forced response: effect of planned future moves
    /// future_moves: [M * nu] vector of planned delta_u
    /// Returns: [P * ny] vector
    Eigen::VectorXd predictForced(const Eigen::VectorXd& future_moves,
                                   int P, int M) const;

    // ---- Serialization ----

    void saveHDF5(const std::string& path) const;

    // ---- Metadata ----

    void setCVNames(const std::vector<std::string>& names);
    void setMVNames(const std::vector<std::string>& names);
    const std::vector<std::string>& cvNames() const { return cv_names_; }
    const std::vector<std::string>& mvNames() const { return mv_names_; }

private:
    int ny_;                           // number of CVs
    int nu_;                           // number of MVs
    int N_;                            // model horizon (truncation length)
    double dt_;                        // sample time (seconds)

    // Step response coefficients stored as [ny * N * nu] flattened
    // Access: S_(cv * N_ * nu_ + step * nu_ + mv)
    // Using flat vector for cache-friendly access patterns
    Eigen::VectorXd S_flat_;

    std::vector<std::string> cv_names_;
    std::vector<std::string> mv_names_;

    // Internal index helper
    int flatIndex(int cv, int step, int mv) const {
        return cv * N_ * nu_ + step * nu_ + mv;
    }
};

}  // namespace azeoapc
