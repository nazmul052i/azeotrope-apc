#include <gtest/gtest.h>
#include "azeoapc/layer1_dynamic_qp.h"
#include <cmath>

using namespace azeoapc;

static Layer1Config makeSISOConfig(int P, int M, double Q, double R)
{
    Layer1Config cfg;
    cfg.prediction_horizon = P;
    cfg.control_horizon = M;
    cfg.cv_weights = Eigen::VectorXd::Constant(1, Q);
    cfg.mv_weights = Eigen::VectorXd::Constant(1, R);
    return cfg;
}

// ============================================================================
// Construction
// ============================================================================

TEST(Layer1DynamicQP, Construction)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig(10, 3, 5.0, 1.0);
    EXPECT_NO_THROW(Layer1DynamicQP(model, cfg));
}

// ============================================================================
// Unconstrained solve
// ============================================================================

TEST(Layer1DynamicQP, Solve_StepResponse)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig(10, 3, 5.0, 1.0);
    Layer1DynamicQP qp(model, cfg);

    auto result = qp.solve(
        Eigen::VectorXd::Zero(10),
        Eigen::VectorXd::Ones(1),
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Zero(1));

    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    EXPECT_GT(result.du[0], 0.0);
    EXPECT_EQ(result.du.size(), 3);
    EXPECT_EQ(result.y_predicted.size(), 10);
    EXPECT_GT(result.y_predicted[9], 0.0);
}

TEST(Layer1DynamicQP, Solve_AtSetpoint)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig(10, 3, 5.0, 1.0);
    Layer1DynamicQP qp(model, cfg);

    auto result = qp.solve(
        Eigen::VectorXd::Ones(10),    // free response already at SP
        Eigen::VectorXd::Ones(1),     // setpoint = 1
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Zero(1));

    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    EXPECT_NEAR(result.du.norm(), 0.0, 1e-6);
}

TEST(Layer1DynamicQP, Solve_WithDisturbance)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig(10, 3, 5.0, 1.0);
    Layer1DynamicQP qp(model, cfg);

    Eigen::VectorXd d(1);
    d << 0.5;

    auto result = qp.solve(
        Eigen::VectorXd::Ones(10),
        Eigen::VectorXd::Ones(1),
        Eigen::VectorXd::Zero(1),
        d);

    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    EXPECT_LT(result.du[0], 0.0);  // compensate positive disturbance
}

// ============================================================================
// Constrained solve (uses analytical fallback with post-hoc clamping if no OSQP)
// ============================================================================

TEST(Layer1DynamicQP, Constrained_MoveLimit)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig(10, 3, 100.0, 0.01);
    Layer1DynamicQP qp(model, cfg);

    qp.constraints().setMVRateBounds(
        Eigen::VectorXd::Constant(1, -0.5),
        Eigen::VectorXd::Constant(1, 0.5));

    auto result = qp.solve(
        Eigen::VectorXd::Zero(10),
        Eigen::VectorXd::Constant(1, 10.0),
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Zero(1));

    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    for (int i = 0; i < 3; ++i)
        EXPECT_LE(result.du[i], 0.5 + 1e-3);
}

// ============================================================================
// MIMO
// ============================================================================

TEST(Layer1DynamicQP, MIMO_2x2)
{
    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K << 1.0, 0.5, 0.3, 2.0;
    tau << 10.0, 5.0, 8.0, 15.0;
    L.setZero();
    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 30);

    Layer1Config cfg;
    cfg.prediction_horizon = 10;
    cfg.control_horizon = 3;
    cfg.cv_weights = Eigen::VectorXd::Constant(2, 5.0);
    cfg.mv_weights = Eigen::VectorXd::Constant(2, 1.0);
    Layer1DynamicQP qp(model, cfg);

    Eigen::VectorXd y_target(2);
    y_target << 1.0, 0.5;

    auto result = qp.solve(
        Eigen::VectorXd::Zero(20),
        y_target,
        Eigen::VectorXd::Zero(2),
        Eigen::VectorXd::Zero(2));

    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    EXPECT_EQ(result.du.size(), 6);
    EXPECT_GT(std::abs(result.du[0]) + std::abs(result.du[1]), 0.0);
}

// ============================================================================
// Weight update
// ============================================================================

TEST(Layer1DynamicQP, UpdateWeights)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig(10, 3, 1.0, 1.0);
    Layer1DynamicQP qp(model, cfg);

    auto r1 = qp.solve(
        Eigen::VectorXd::Zero(10),
        Eigen::VectorXd::Ones(1),
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Zero(1));

    qp.updateWeights(Eigen::VectorXd::Constant(1, 100.0),
                     Eigen::VectorXd::Constant(1, 0.1));

    auto r2 = qp.solve(
        Eigen::VectorXd::Zero(10),
        Eigen::VectorXd::Ones(1),
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Zero(1));

    EXPECT_GT(std::abs(r2.du[0]), std::abs(r1.du[0]));
}

// ============================================================================
// Solve time
// ============================================================================

TEST(Layer1DynamicQP, SolveTimeReported)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig(10, 3, 5.0, 1.0);
    Layer1DynamicQP qp(model, cfg);

    auto result = qp.solve(
        Eigen::VectorXd::Zero(10),
        Eigen::VectorXd::Ones(1),
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Zero(1));

    EXPECT_GT(result.solve_time_ms, 0.0);
}
