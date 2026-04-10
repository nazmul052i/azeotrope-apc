#pragma once

#include <Eigen/Dense>
#include <deque>
#include "azeoapc/step_response_model.h"
#include "azeoapc/dynamic_matrix.h"

namespace azeoapc {

/**
 * Prediction Engine
 *
 * Manages the rolling prediction: maintains history of past moves,
 * computes free response, and generates predictions for future moves.
 */
class PredictionEngine {
public:
    PredictionEngine(const StepResponseModel& model, int P, int M);

    /// Update with new measurement and applied move
    void update(const Eigen::VectorXd& y_measured,
                const Eigen::VectorXd& du_applied);

    /// Free response: predicted output if no future moves [P*ny]
    Eigen::VectorXd freeResponse() const;

    /// Predicted output for given future moves [P*ny]
    Eigen::VectorXd predict(const Eigen::VectorXd& du_future) const;

    /// Access the dynamic matrix
    const DynamicMatrix& dynamicMatrix() const { return dynmat_; }

    /// Reset internal state (past moves history)
    void reset();

    /// Get past moves history as matrix [N x nu]
    Eigen::MatrixXd pastMovesMatrix() const;

private:
    StepResponseModel model_;
    DynamicMatrix dynmat_;
    std::deque<Eigen::VectorXd> past_moves_;  // rolling window [N] of du vectors
    int N_;   // model horizon
    int P_;   // prediction horizon
    int M_;   // control horizon
    int nu_;  // MV count
};

}  // namespace azeoapc
