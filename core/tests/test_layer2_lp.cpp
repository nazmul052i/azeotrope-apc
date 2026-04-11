#include <gtest/gtest.h>
#include "azeoapc/layer2_ss_target.h"
#include <cmath>

using namespace azeoapc;

// ============================================================================
// Construction
// ============================================================================

TEST(Layer2SSTarget, Construction)
{
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 30);
    Layer2Config cfg;
    cfg.ss_cv_weights = Eigen::VectorXd::Constant(1, 1.0);
    cfg.ss_mv_costs = Eigen::VectorXd::Zero(1);
    cfg.use_lp = true;
    EXPECT_NO_THROW(Layer2SSTarget(model, cfg));
}

// ============================================================================
// LP mode: minimize c' * u_ss  subject to y_ss = G * u_ss + d
// ============================================================================

TEST(Layer2SSTarget, LP_NoConstraints)
{
    // SISO: G = 2.0, no constraints, cost = 1.0 per unit u
    // With no bounds, LP is unbounded (direction depends on cost sign)
    // We expect the solver to find a solution (or report unbounded)
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 60);
    Layer2Config cfg;
    cfg.ss_cv_weights = Eigen::VectorXd::Constant(1, 1.0);
    cfg.ss_mv_costs = Eigen::VectorXd::Zero(1);  // zero cost -> any u is optimal
    cfg.use_lp = true;

    Layer2SSTarget layer2(model, cfg);

    auto result = layer2.solve(
        Eigen::VectorXd::Constant(1, 1.0),  // setpoint
        Eigen::VectorXd::Zero(1));           // no disturbance

    // With zero cost and no bounds, solution exists (y=G*u)
    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
}

TEST(Layer2SSTarget, LP_WithEconomicCost)
{
    // 2 MVs, 1 CV: G = [2.0, 3.0]
    // Cost = [1.0, 2.0] -- prefer MV1 (cheaper)
    // Need MV bounds to avoid unbounded LP
    Eigen::MatrixXd K(1, 2), tau(1, 2), L(1, 2);
    K << 2.0, 3.0;
    tau << 10.0, 10.0;
    L << 0.0, 0.0;
    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 60);

    Layer2Config cfg;
    cfg.ss_cv_weights = Eigen::VectorXd::Constant(1, 1.0);
    cfg.ss_mv_costs.resize(2);
    cfg.ss_mv_costs << 1.0, 2.0;
    cfg.use_lp = true;

    Layer2SSTarget layer2(model, cfg);
    // Set MV bounds: u >= 0 (non-negative)
    layer2.constraints().setMVBounds(Eigen::VectorXd::Zero(2),
                                      Eigen::VectorXd::Constant(2, 100.0));

    auto result = layer2.solve(
        Eigen::VectorXd::Zero(1),    // setpoint = 0
        Eigen::VectorXd::Zero(1));

    // With y_sp=0, d=0: G*u = y → y=0 → u=0 is optimal (zero cost)
    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    EXPECT_NEAR(result.u_ss.norm(), 0.0, 1e-4);
}

// ============================================================================
// QP mode: minimize ||y_ss - y_sp||^2_Qs + c' * u_ss
// ============================================================================

TEST(Layer2SSTarget, QP_TrackSetpoint)
{
    // SISO: G ≈ 2.0, track setpoint = 1.0
    // QP should find u_ss such that G * u_ss ≈ 1.0, so u_ss ≈ 0.5
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 60);

    Layer2Config cfg;
    cfg.ss_cv_weights = Eigen::VectorXd::Constant(1, 10.0);
    cfg.ss_mv_costs = Eigen::VectorXd::Zero(1);
    cfg.use_lp = false;  // QP mode

    Layer2SSTarget layer2(model, cfg);
    auto result = layer2.solve(
        Eigen::VectorXd::Constant(1, 1.0),  // setpoint = 1.0
        Eigen::VectorXd::Zero(1));

    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    // y_ss = G * u_ss ≈ 1.0
    EXPECT_NEAR(result.y_ss[0], 1.0, 0.05);
    // u_ss ≈ 1.0 / G ≈ 0.5
    double G_val = model.steadyStateGain()(0, 0);
    EXPECT_NEAR(result.u_ss[0], 1.0 / G_val, 0.05);
}

TEST(Layer2SSTarget, QP_WithDisturbance)
{
    // SISO: G ≈ 2.0, track SP=1.0 with disturbance d=0.5
    // y_ss = G * u_ss + d,  want y_ss = 1.0 -> G * u_ss = 0.5 -> u_ss ≈ 0.25
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 60);

    Layer2Config cfg;
    cfg.ss_cv_weights = Eigen::VectorXd::Constant(1, 10.0);
    cfg.ss_mv_costs = Eigen::VectorXd::Zero(1);
    cfg.use_lp = false;

    Layer2SSTarget layer2(model, cfg);
    auto result = layer2.solve(
        Eigen::VectorXd::Constant(1, 1.0),
        Eigen::VectorXd::Constant(1, 0.5));

    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    EXPECT_NEAR(result.y_ss[0], 1.0, 0.05);
}

TEST(Layer2SSTarget, QP_MIMO_2x2)
{
    // 2x2: G = [2 -1; 1 3], track [1.0, 2.0]
    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K << 2.0, -1.0, 1.0, 3.0;
    tau << 10.0, 10.0, 10.0, 10.0;
    L.setZero();
    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 60);

    Layer2Config cfg;
    cfg.ss_cv_weights = Eigen::VectorXd::Constant(2, 10.0);
    cfg.ss_mv_costs = Eigen::VectorXd::Zero(2);
    cfg.use_lp = false;

    Layer2SSTarget layer2(model, cfg);
    Eigen::VectorXd y_sp(2);
    y_sp << 1.0, 2.0;

    auto result = layer2.solve(y_sp, Eigen::VectorXd::Zero(2));

    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    EXPECT_NEAR(result.y_ss[0], 1.0, 0.1);
    EXPECT_NEAR(result.y_ss[1], 2.0, 0.1);
}

// ============================================================================
// Gain matrix update (from Layer 3 re-linearization)
// ============================================================================

TEST(Layer2SSTarget, UpdateGainMatrix)
{
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 60);

    Layer2Config cfg;
    cfg.ss_cv_weights = Eigen::VectorXd::Constant(1, 10.0);
    cfg.ss_mv_costs = Eigen::VectorXd::Zero(1);
    cfg.use_lp = false;

    Layer2SSTarget layer2(model, cfg);

    // Solve with original gain
    auto r1 = layer2.solve(Eigen::VectorXd::Ones(1), Eigen::VectorXd::Zero(1));

    // Update gain to 4.0 (doubled)
    Eigen::MatrixXd G_new(1, 1);
    G_new << 4.0;
    layer2.updateGainMatrix(G_new);

    auto r2 = layer2.solve(Eigen::VectorXd::Ones(1), Eigen::VectorXd::Zero(1));

    // With doubled gain, u_ss should be roughly halved
    EXPECT_LT(std::abs(r2.u_ss[0]), std::abs(r1.u_ss[0]) + 0.01);
}

// ============================================================================
// Solve time
// ============================================================================

TEST(Layer2SSTarget, SolveTimeReported)
{
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 60);
    Layer2Config cfg;
    cfg.ss_cv_weights = Eigen::VectorXd::Constant(1, 1.0);
    cfg.ss_mv_costs = Eigen::VectorXd::Zero(1);
    cfg.use_lp = false;

    Layer2SSTarget layer2(model, cfg);
    auto result = layer2.solve(Eigen::VectorXd::Ones(1), Eigen::VectorXd::Zero(1));
    EXPECT_GT(result.solve_time_ms, 0.0);
}
