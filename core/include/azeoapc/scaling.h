#pragma once

#include <Eigen/Dense>
#include "azeoapc/step_response_model.h"

namespace azeoapc {

/**
 * Variable Scaling
 *
 * Industrial controllers require proper scaling to handle variables
 * with different engineering units and ranges. All internal computations
 * operate on scaled [0, 1] variables for numerical conditioning.
 */
class Scaling {
public:
    Scaling(const Eigen::VectorXd& cv_lo, const Eigen::VectorXd& cv_hi,
            const Eigen::VectorXd& mv_lo, const Eigen::VectorXd& mv_hi);

    // Scale raw engineering values to [0, 1]
    Eigen::VectorXd scaleCV(const Eigen::VectorXd& raw) const;
    Eigen::VectorXd scaleMV(const Eigen::VectorXd& raw) const;

    // Unscale [0, 1] back to engineering values
    Eigen::VectorXd unscaleCV(const Eigen::VectorXd& scaled) const;
    Eigen::VectorXd unscaleMV(const Eigen::VectorXd& scaled) const;

    // Scale increments (du)
    Eigen::VectorXd scaleMVIncrement(const Eigen::VectorXd& du) const;
    Eigen::VectorXd unscaleMVIncrement(const Eigen::VectorXd& du_scaled) const;

    // Scale step response model coefficients
    StepResponseModel scaleModel(const StepResponseModel& model) const;

    // Scale bounds
    Eigen::VectorXd scaleCVBound(const Eigen::VectorXd& bound) const;
    Eigen::VectorXd scaleMVBound(const Eigen::VectorXd& bound) const;

private:
    Eigen::VectorXd cv_lo_, cv_hi_, cv_range_;
    Eigen::VectorXd mv_lo_, mv_hi_, mv_range_;
};

}  // namespace azeoapc
