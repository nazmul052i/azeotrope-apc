#include <gtest/gtest.h>
#include "azeoapc/prediction_engine.h"
#include <cmath>

using namespace azeoapc;

// ============================================================================
// Construction & Reset
// ============================================================================

TEST(PredictionEngine, ConstructionAndDimensions)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    PredictionEngine pe(model, 10, 3);

    EXPECT_EQ(pe.dynamicMatrix().predictionHorizon(), 10);
    EXPECT_EQ(pe.dynamicMatrix().controlHorizon(), 3);
}

TEST(PredictionEngine, ResetGivesZeroFreeResponse)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    int P = 10;
    PredictionEngine pe(model, P, 3);

    auto y_free = pe.freeResponse();
    EXPECT_EQ(y_free.size(), P);
    for (int i = 0; i < P; ++i)
        EXPECT_NEAR(y_free[i], 0.0, 1e-12);
}

// ============================================================================
// Past moves tracking
// ============================================================================

TEST(PredictionEngine, PastMovesMatrix)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 10);
    PredictionEngine pe(model, 5, 2);

    Eigen::VectorXd du1(1);
    du1 << 1.0;
    pe.update(Eigen::VectorXd::Zero(1), du1);

    Eigen::VectorXd du2(1);
    du2 << 2.0;
    pe.update(Eigen::VectorXd::Zero(1), du2);

    auto pm = pe.pastMovesMatrix();
    EXPECT_EQ(pm.rows(), 10);  // N
    EXPECT_EQ(pm.cols(), 1);   // nu

    // Most recent first
    EXPECT_DOUBLE_EQ(pm(0, 0), 2.0);  // du2
    EXPECT_DOUBLE_EQ(pm(1, 0), 1.0);  // du1
    EXPECT_DOUBLE_EQ(pm(2, 0), 0.0);  // initial zero
}

// ============================================================================
// Free response after step change
// ============================================================================

TEST(PredictionEngine, FreeResponseAfterStep)
{
    // Apply a unit step at k=0, then check free response at k=1
    double K = 1.0, tau = 10.0, dt = 1.0;
    int N = 30, P = 10;
    auto model = StepResponseModel::fromFOPTD(K, tau, 0.0, dt, N);
    PredictionEngine pe(model, P, 3);

    // Apply du = 1 at first step
    Eigen::VectorXd du(1);
    du << 1.0;
    pe.update(Eigen::VectorXd::Zero(1), du);

    // Free response should predict the ongoing effect of du[k-1]=1
    // y_free[j-1] = sum_m S_stored[m+j-1] * past(m-1)
    // Only past(0) = 1.0 contributes: y_free[j-1] = S_stored[j]
    auto y_free = pe.freeResponse();

    for (int j = 1; j <= P; ++j) {
        int s_idx = j;  // S_stored[j] = response at step j+1
        if (s_idx < N) {
            EXPECT_NEAR(y_free[j - 1], model.coefficient(0, s_idx, 0), 1e-10)
                << "Free response mismatch at j=" << j;
        }
    }
}

// ============================================================================
// Predict (free + forced)
// ============================================================================

TEST(PredictionEngine, PredictMatchesFreeForced)
{
    auto model = StepResponseModel::fromFOPTD(1.5, 8.0, 0.0, 1.0, 30);
    int P = 10, M = 3;
    PredictionEngine pe(model, P, M);

    // Apply some past moves
    Eigen::VectorXd du(1);
    du << 0.5;
    pe.update(Eigen::VectorXd::Zero(1), du);
    du << -0.3;
    pe.update(Eigen::VectorXd::Zero(1), du);

    // Future moves
    Eigen::VectorXd du_future = Eigen::VectorXd::Random(M);

    // predict = freeResponse + A_dyn * du_future
    auto y_pred = pe.predict(du_future);
    auto y_free = pe.freeResponse();
    Eigen::VectorXd y_forced = pe.dynamicMatrix().matrix() * du_future;

    double max_diff = (y_pred - y_free - y_forced).cwiseAbs().maxCoeff();
    EXPECT_LT(max_diff, 1e-10);
}

// ============================================================================
// Superposition: step response via prediction engine
// ============================================================================

TEST(PredictionEngine, SuperpositionPrinciple)
{
    // Two separate simulations with different du sequences should
    // combine linearly (since this is a linear model).
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 20);
    int P = 8, M = 2;

    Eigen::VectorXd du_a(1), du_b(1);
    du_a << 1.0;
    du_b << 2.0;

    // Simulation A
    PredictionEngine pe_a(model, P, M);
    pe_a.update(Eigen::VectorXd::Zero(1), du_a);
    auto y_a = pe_a.freeResponse();

    // Simulation B
    PredictionEngine pe_b(model, P, M);
    pe_b.update(Eigen::VectorXd::Zero(1), du_b);
    auto y_b = pe_b.freeResponse();

    // Simulation A+B
    PredictionEngine pe_ab(model, P, M);
    Eigen::VectorXd du_ab(1);
    du_ab << 3.0;
    pe_ab.update(Eigen::VectorXd::Zero(1), du_ab);
    auto y_ab = pe_ab.freeResponse();

    double max_diff = (y_ab - y_a - y_b).cwiseAbs().maxCoeff();
    EXPECT_LT(max_diff, 1e-10);
}

// ============================================================================
// MIMO prediction
// ============================================================================

TEST(PredictionEngine, MIMO_BasicPrediction)
{
    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K << 1.0, 0.5, 0.3, 2.0;
    tau << 10.0, 5.0, 8.0, 15.0;
    L.setZero();

    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 30);
    int P = 6, M = 2, nu = 2, ny = 2;
    PredictionEngine pe(model, P, M);

    Eigen::VectorXd du(nu);
    du << 1.0, 0.0;  // step only MV1
    pe.update(Eigen::VectorXd::Zero(ny), du);

    auto y_free = pe.freeResponse();
    EXPECT_EQ(y_free.size(), P * ny);

    // First CV should respond, second CV should respond (K(1,0)=0.3)
    EXPECT_GT(std::abs(y_free[0 * 1]), 0.0);   // CV0 at first prediction step
}

// ============================================================================
// Rolling history trimming
// ============================================================================

TEST(PredictionEngine, HistoryTrimsToModelHorizon)
{
    int N = 5;
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, N);
    PredictionEngine pe(model, 3, 2);

    // Push N+5 moves (more than model horizon)
    for (int i = 0; i < N + 5; ++i) {
        Eigen::VectorXd du(1);
        du << static_cast<double>(i);
        pe.update(Eigen::VectorXd::Zero(1), du);
    }

    auto pm = pe.pastMovesMatrix();
    EXPECT_EQ(pm.rows(), N);

    // Most recent should be the last pushed value
    EXPECT_DOUBLE_EQ(pm(0, 0), static_cast<double>(N + 4));
}
