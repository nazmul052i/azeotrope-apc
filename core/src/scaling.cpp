#include "azeoapc/scaling.h"
#include <stdexcept>

namespace azeoapc {

Scaling::Scaling(const Eigen::VectorXd& cv_lo, const Eigen::VectorXd& cv_hi,
                 const Eigen::VectorXd& mv_lo, const Eigen::VectorXd& mv_hi)
    : cv_lo_(cv_lo), cv_hi_(cv_hi),
      mv_lo_(mv_lo), mv_hi_(mv_hi)
{
    cv_range_ = cv_hi_ - cv_lo_;
    mv_range_ = mv_hi_ - mv_lo_;

    // Guard against zero range
    for (int i = 0; i < cv_range_.size(); ++i)
        if (cv_range_[i] <= 0.0)
            throw std::invalid_argument("Scaling: CV range must be positive");
    for (int i = 0; i < mv_range_.size(); ++i)
        if (mv_range_[i] <= 0.0)
            throw std::invalid_argument("Scaling: MV range must be positive");
}

Eigen::VectorXd Scaling::scaleCV(const Eigen::VectorXd& raw) const
{
    return (raw - cv_lo_).cwiseQuotient(cv_range_);
}

Eigen::VectorXd Scaling::scaleMV(const Eigen::VectorXd& raw) const
{
    return (raw - mv_lo_).cwiseQuotient(mv_range_);
}

Eigen::VectorXd Scaling::unscaleCV(const Eigen::VectorXd& scaled) const
{
    return scaled.cwiseProduct(cv_range_) + cv_lo_;
}

Eigen::VectorXd Scaling::unscaleMV(const Eigen::VectorXd& scaled) const
{
    return scaled.cwiseProduct(mv_range_) + mv_lo_;
}

Eigen::VectorXd Scaling::scaleMVIncrement(const Eigen::VectorXd& du) const
{
    return du.cwiseQuotient(mv_range_);
}

Eigen::VectorXd Scaling::unscaleMVIncrement(const Eigen::VectorXd& du_scaled) const
{
    return du_scaled.cwiseProduct(mv_range_);
}

StepResponseModel Scaling::scaleModel(const StepResponseModel& model) const
{
    int ny = model.ny(), nu = model.nu(), N = model.modelHorizon();
    StepResponseModel scaled(ny, nu, N, model.sampleTime());

    // Scale coefficient: S_scaled(cv, step, mv) = S(cv, step, mv) * mv_range[mv] / cv_range[cv]
    for (int cv = 0; cv < ny; ++cv)
        for (int step = 0; step < N; ++step)
            for (int mv = 0; mv < nu; ++mv) {
                double s = model.coefficient(cv, step, mv);
                // This is intentionally left as identity scaling for now.
                // The MPC formulation operates in engineering units;
                // scaling is applied to weights and bounds rather than model coefficients.
                // Full model scaling: s_scaled = s * (mv_range / cv_range)
                // But this changes the gain structure. Typically in DMC,
                // the model is kept in engineering units and scaling is applied
                // to the Q/R weights.
            }

    return model;  // Return unmodified for now -- scaling applied to weights instead
}

Eigen::VectorXd Scaling::scaleCVBound(const Eigen::VectorXd& bound) const
{
    return (bound - cv_lo_).cwiseQuotient(cv_range_);
}

Eigen::VectorXd Scaling::scaleMVBound(const Eigen::VectorXd& bound) const
{
    return (bound - mv_lo_).cwiseQuotient(mv_range_);
}

}  // namespace azeoapc
