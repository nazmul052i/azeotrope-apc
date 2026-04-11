#include "azeoapc/disturbance_observer.h"
#include <stdexcept>

namespace azeoapc {

DisturbanceObserver::DisturbanceObserver(int ny, Method method)
    : ny_(ny),
      method_(method),
      alpha_(0.8),
      d_(Eigen::VectorXd::Zero(ny))
{
    if (ny <= 0)
        throw std::invalid_argument("DisturbanceObserver: ny must be positive");

    if (method_ == Method::KALMAN_FILTER) {
        P_ = Eigen::MatrixXd::Identity(ny, ny);
        Q_ = Eigen::MatrixXd::Identity(ny, ny) * 0.01;
        R_ = Eigen::MatrixXd::Identity(ny, ny) * 1.0;
    }
}

Eigen::VectorXd DisturbanceObserver::update(
    const Eigen::VectorXd& y_measured,
    const Eigen::VectorXd& y_predicted)
{
    if (y_measured.size() != ny_ || y_predicted.size() != ny_)
        throw std::invalid_argument("DisturbanceObserver::update: vector size must equal ny");

    // error = y_measured - y_predicted  (prediction does NOT include d_)
    Eigen::VectorXd error = y_measured - y_predicted;

    if (method_ == Method::EXPONENTIAL_FILTER) {
        // d[k] = alpha * d[k-1] + (1 - alpha) * error
        d_ = alpha_ * d_ + (1.0 - alpha_) * error;
    }
    else {  // KALMAN_FILTER
        // Disturbance random walk: d[k+1] = d[k] + w,  z[k] = d[k] + v
        // Predict
        Eigen::MatrixXd P_pred = P_ + Q_;
        // Update
        Eigen::MatrixXd S = P_pred + R_;
        Eigen::MatrixXd K = P_pred * S.inverse();
        Eigen::VectorXd innovation = error - d_;
        d_ = d_ + K * innovation;
        Eigen::MatrixXd I = Eigen::MatrixXd::Identity(ny_, ny_);
        P_ = (I - K) * P_pred;
    }

    return d_;
}

void DisturbanceObserver::setFilterGain(double alpha)
{
    if (alpha < 0.0 || alpha >= 1.0)
        throw std::invalid_argument("setFilterGain: alpha must be in [0, 1)");
    alpha_ = alpha;
}

void DisturbanceObserver::setKalmanTuning(
    const Eigen::MatrixXd& Q,
    const Eigen::MatrixXd& R)
{
    if (Q.rows() != ny_ || Q.cols() != ny_ || R.rows() != ny_ || R.cols() != ny_)
        throw std::invalid_argument("setKalmanTuning: Q and R must be [ny x ny]");
    Q_ = Q;
    R_ = R;
}

void DisturbanceObserver::reset()
{
    d_.setZero();
    if (method_ == Method::KALMAN_FILTER)
        P_ = Eigen::MatrixXd::Identity(ny_, ny_);
}

}  // namespace azeoapc
