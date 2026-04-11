#include <gtest/gtest.h>
#include "azeoapc/mpc_controller.h"
#include <cmath>

using namespace azeoapc;

// Helper: build minimal MPCConfig for SISO FOPTD
static MPCConfig makeSISOConfig()
{
    MPCConfig cfg;
    cfg.sample_time = 1.0;
    cfg.layer1.prediction_horizon = 10;
    cfg.layer1.control_horizon = 3;
    cfg.layer1.cv_weights = Eigen::VectorXd::Constant(1, 5.0);
    cfg.layer1.mv_weights = Eigen::VectorXd::Constant(1, 1.0);
    cfg.layer2.ss_cv_weights = Eigen::VectorXd::Constant(1, 10.0);
    cfg.layer2.ss_mv_costs = Eigen::VectorXd::Zero(1);
    cfg.layer2.use_lp = false;  // QP tracking mode
    cfg.enable_layer3 = false;
    cfg.enable_storage = false;
    return cfg;
}

static MPCConfig make2x2Config()
{
    MPCConfig cfg;
    cfg.sample_time = 1.0;
    cfg.layer1.prediction_horizon = 10;
    cfg.layer1.control_horizon = 3;
    cfg.layer1.cv_weights = Eigen::VectorXd::Constant(2, 5.0);
    cfg.layer1.mv_weights = Eigen::VectorXd::Constant(2, 1.0);
    cfg.layer2.ss_cv_weights = Eigen::VectorXd::Constant(2, 10.0);
    cfg.layer2.ss_mv_costs = Eigen::VectorXd::Zero(2);
    cfg.layer2.use_lp = false;
    cfg.enable_layer3 = false;
    cfg.enable_storage = false;
    return cfg;
}

// ============================================================================
// Construction
// ============================================================================

TEST(MPCController, Construction)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    EXPECT_NO_THROW(MPCController(cfg, model));
}

TEST(MPCController, Dimensions)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);

    EXPECT_EQ(ctrl.ny(), 1);
    EXPECT_EQ(ctrl.nu(), 1);
    EXPECT_EQ(ctrl.cycleCount(), 0);
    EXPECT_EQ(ctrl.mode(), ControllerMode::AUTO);
}

// ============================================================================
// Execute: basic step tracking
// ============================================================================

TEST(MPCController, Execute_StepTracking)
{
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);

    // Set setpoint
    ctrl.setSetpoints(Eigen::VectorXd::Constant(1, 1.0));

    // First execution: y=0, u=0
    auto out = ctrl.execute(
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Zero(1));

    EXPECT_EQ(out.layer1_status, SolverStatus::OPTIMAL);
    EXPECT_EQ(out.layer2_status, SolverStatus::OPTIMAL);
    EXPECT_GT(out.du[0], 0.0);  // should move positive to track SP=1
    EXPECT_EQ(out.du.size(), 1);
    EXPECT_EQ(out.u_new.size(), 1);
    EXPECT_GT(out.total_solve_time_ms, 0.0);
    EXPECT_EQ(ctrl.cycleCount(), 1);
}

TEST(MPCController, Execute_MultipleCycles)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);
    ctrl.setSetpoints(Eigen::VectorXd::Constant(1, 1.0));

    double u = 0.0;
    for (int k = 0; k < 5; ++k) {
        auto out = ctrl.execute(
            Eigen::VectorXd::Zero(1),  // measurement (simplified)
            Eigen::VectorXd::Constant(1, u));
        u += out.du[0];
    }

    EXPECT_EQ(ctrl.cycleCount(), 5);
    // u should have moved significantly toward tracking
    EXPECT_GT(std::abs(u), 0.01);
}

// ============================================================================
// Execute: already at setpoint
// ============================================================================

TEST(MPCController, Execute_AtSetpoint)
{
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);
    ctrl.setSetpoints(Eigen::VectorXd::Zero(1));

    auto out = ctrl.execute(
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Zero(1));

    EXPECT_EQ(out.layer1_status, SolverStatus::OPTIMAL);
    EXPECT_NEAR(out.du.norm(), 0.0, 1e-4);
}

// ============================================================================
// MIMO
// ============================================================================

TEST(MPCController, Execute_MIMO_2x2)
{
    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K << 1.0, 0.5, 0.3, 2.0;
    tau << 10.0, 5.0, 8.0, 15.0;
    L.setZero();
    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 30);
    auto cfg = make2x2Config();
    MPCController ctrl(cfg, model);

    Eigen::VectorXd sp(2);
    sp << 1.0, 0.5;
    ctrl.setSetpoints(sp);

    auto out = ctrl.execute(
        Eigen::VectorXd::Zero(2),
        Eigen::VectorXd::Zero(2));

    EXPECT_EQ(out.layer1_status, SolverStatus::OPTIMAL);
    EXPECT_EQ(out.du.size(), 2);
    EXPECT_EQ(out.u_new.size(), 2);
    EXPECT_GT(out.du.norm(), 0.0);
}

// ============================================================================
// Manual mode
// ============================================================================

TEST(MPCController, ManualMode)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);

    ctrl.setMode(ControllerMode::MANUAL);
    EXPECT_EQ(ctrl.mode(), ControllerMode::MANUAL);

    auto out = ctrl.execute(
        Eigen::VectorXd::Zero(1),
        Eigen::VectorXd::Constant(1, 5.0));

    // In manual mode, du should be zero
    EXPECT_NEAR(out.du[0], 0.0, 1e-10);
    EXPECT_DOUBLE_EQ(out.u_new[0], 5.0);
}

// ============================================================================
// Online configuration
// ============================================================================

TEST(MPCController, SetSetpoint)
{
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);

    ctrl.setSetpoints(Eigen::VectorXd::Constant(1, 1.0));
    auto r1 = ctrl.execute(Eigen::VectorXd::Zero(1), Eigen::VectorXd::Zero(1));

    ctrl.setSetpoints(Eigen::VectorXd::Constant(1, 2.0));
    auto r2 = ctrl.execute(Eigen::VectorXd::Zero(1), Eigen::VectorXd::Zero(1));

    // Larger setpoint should produce larger du
    EXPECT_GT(r2.du[0], r1.du[0] - 0.01);
}

TEST(MPCController, ModeSwitching)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);
    ctrl.setSetpoints(Eigen::VectorXd::Constant(1, 1.0));

    // AUTO -> MANUAL -> AUTO
    ctrl.setMode(ControllerMode::AUTO);
    auto r1 = ctrl.execute(Eigen::VectorXd::Zero(1), Eigen::VectorXd::Zero(1));
    EXPECT_GT(std::abs(r1.du[0]), 0.0);

    ctrl.setMode(ControllerMode::MANUAL);
    auto r2 = ctrl.execute(Eigen::VectorXd::Zero(1), Eigen::VectorXd::Zero(1));
    EXPECT_NEAR(r2.du[0], 0.0, 1e-10);

    ctrl.setMode(ControllerMode::AUTO);
    auto r3 = ctrl.execute(Eigen::VectorXd::Zero(1), Eigen::VectorXd::Zero(1));
    EXPECT_GT(std::abs(r3.du[0]), 0.0);
}

// ============================================================================
// Status
// ============================================================================

TEST(MPCController, Status)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);

    auto s = ctrl.status();
    EXPECT_EQ(s.mode, ControllerMode::AUTO);
    EXPECT_TRUE(s.is_running);
    EXPECT_EQ(s.total_cvs, 1);
    EXPECT_EQ(s.total_mvs, 1);
}

// ============================================================================
// Diagnostics in output
// ============================================================================

TEST(MPCController, DiagnosticsPopulated)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto cfg = makeSISOConfig();
    MPCController ctrl(cfg, model);
    ctrl.setSetpoints(Eigen::VectorXd::Constant(1, 1.0));

    auto out = ctrl.execute(Eigen::VectorXd::Zero(1), Eigen::VectorXd::Zero(1));

    EXPECT_GT(out.diagnostics.layer1_solve_ms, 0.0);
    EXPECT_GT(out.diagnostics.layer2_solve_ms, 0.0);
    EXPECT_GT(out.diagnostics.total_solve_ms, 0.0);
}
