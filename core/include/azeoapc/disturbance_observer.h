#pragma once

#include <Eigen/Dense>

namespace azeoapc {

/**
 * Disturbance Observer
 *
 * Estimates output bias d[k] for offset-free tracking.
 * Without this, the controller would have steady-state offset whenever
 * the model doesn't perfectly match the plant.
 *
 * Simple mode: exponential filter on prediction error
 *   d[k] = alpha * d[k-1] + (1 - alpha) * (y_meas - y_pred)
 *
 * Kalman mode: augmented state Kalman filter
 *   [x; d]+ = [A 0; 0 I] [x; d] + [B; 0] u + w
 *   y = [C I] [x; d] + v
 */
class DisturbanceObserver {
public:
    enum class Method {
        EXPONENTIAL_FILTER,
        KALMAN_FILTER
    };

    DisturbanceObserver(int ny, Method method = Method::EXPONENTIAL_FILTER);

    /// Update with prediction error and return new estimate
    Eigen::VectorXd update(const Eigen::VectorXd& y_measured,
                           const Eigen::VectorXd& y_predicted);

    /// Current disturbance estimate [ny]
    const Eigen::VectorXd& estimate() const { return d_; }

    /// Set exponential filter gain (0 < alpha < 1, higher = more filtering)
    void setFilterGain(double alpha);

    /// Set Kalman filter tuning matrices
    void setKalmanTuning(const Eigen::MatrixXd& Q,
                         const Eigen::MatrixXd& R);

    /// Reset estimate to zero
    void reset();

private:
    int ny_;
    Method method_;
    double alpha_;              // filter gain
    Eigen::VectorXd d_;         // current disturbance estimate

    // Kalman filter state (if method == KALMAN_FILTER)
    Eigen::MatrixXd P_;         // error covariance
    Eigen::MatrixXd Q_;         // process noise
    Eigen::MatrixXd R_;         // measurement noise
};

}  // namespace azeoapc
