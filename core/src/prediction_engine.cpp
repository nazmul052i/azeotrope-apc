#include "azeoapc/prediction_engine.h"
#include <stdexcept>

namespace azeoapc {

PredictionEngine::PredictionEngine(const StepResponseModel& model, int P, int M)
    : model_(model),
      dynmat_(model, P, M),
      N_(model.modelHorizon()),
      P_(P),
      M_(M),
      nu_(model.nu())
{
    reset();
}

void PredictionEngine::update(
    const Eigen::VectorXd& /*y_measured*/,
    const Eigen::VectorXd& du_applied)
{
    if (du_applied.size() != nu_)
        throw std::invalid_argument("PredictionEngine::update: du_applied size must equal nu");

    // Push new move to front (most recent first)
    past_moves_.push_front(du_applied);

    // Trim to model horizon length
    while (static_cast<int>(past_moves_.size()) > N_)
        past_moves_.pop_back();
}

Eigen::VectorXd PredictionEngine::freeResponse() const
{
    Eigen::MatrixXd pm = pastMovesMatrix();
    return model_.predictFree(pm, P_);
}

Eigen::VectorXd PredictionEngine::predict(const Eigen::VectorXd& du_future) const
{
    Eigen::VectorXd y_free = freeResponse();
    Eigen::VectorXd y_forced = dynmat_.matrix() * du_future;
    return y_free + y_forced;
}

void PredictionEngine::reset()
{
    past_moves_.clear();
    for (int i = 0; i < N_; ++i)
        past_moves_.push_back(Eigen::VectorXd::Zero(nu_));
}

Eigen::MatrixXd PredictionEngine::pastMovesMatrix() const
{
    Eigen::MatrixXd pm = Eigen::MatrixXd::Zero(N_, nu_);

    int n = static_cast<int>(past_moves_.size());
    for (int i = 0; i < std::min(n, N_); ++i)
        pm.row(i) = past_moves_[i].transpose();

    return pm;
}

}  // namespace azeoapc
