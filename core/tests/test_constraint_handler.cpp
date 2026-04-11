#include <gtest/gtest.h>
#include "azeoapc/constraint_handler.h"
#include "azeoapc/step_response_model.h"
#include <cmath>

using namespace azeoapc;

// ============================================================================
// Construction
// ============================================================================

TEST(ConstraintHandler, ConstructionDefaults)
{
    ConstraintHandler ch(2, 3, 5, 10);
    auto report = ch.checkFeasibility(Eigen::VectorXd::Zero(2));
    EXPECT_TRUE(report.feasible);
}

// ============================================================================
// Set and query bounds
// ============================================================================

TEST(ConstraintHandler, SetMVBounds)
{
    ConstraintHandler ch(2, 1, 3, 5);
    Eigen::VectorXd lb(2), ub(2);
    lb << 0.0, 0.0;
    ub << 100.0, 50.0;
    EXPECT_NO_THROW(ch.setMVBounds(lb, ub));
}

TEST(ConstraintHandler, SetMVBoundsWrongSize)
{
    ConstraintHandler ch(2, 1, 3, 5);
    EXPECT_THROW(ch.setMVBounds(Eigen::VectorXd::Zero(3), Eigen::VectorXd::Zero(3)),
                 std::invalid_argument);
}

TEST(ConstraintHandler, SetMVRateBounds)
{
    ConstraintHandler ch(2, 1, 3, 5);
    Eigen::VectorXd du_lb(2), du_ub(2);
    du_lb << -5.0, -2.0;
    du_ub << 5.0, 2.0;
    EXPECT_NO_THROW(ch.setMVRateBounds(du_lb, du_ub));
}

TEST(ConstraintHandler, SetCVBounds)
{
    ConstraintHandler ch(1, 2, 3, 5);
    Eigen::VectorXd lb(2), ub(2);
    lb << 300.0, 0.5;
    ub << 400.0, 1.0;
    EXPECT_NO_THROW(ch.setCVSafetyBounds(lb, ub));
    EXPECT_NO_THROW(ch.setCVOperatingBounds(lb + Eigen::VectorXd::Constant(2, 10),
                                             ub - Eigen::VectorXd::Constant(2, 10)));
}

// ============================================================================
// Build QP constraints
// ============================================================================

TEST(ConstraintHandler, BuildForQP_Dimensions)
{
    int nu = 2, ny = 2, M = 3, P = 5;
    ConstraintHandler ch(nu, ny, M, P);

    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K.setOnes();
    tau.setConstant(10.0);
    L.setZero();
    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 30);
    DynamicMatrix dynmat(model, P, M);

    Eigen::VectorXd u_current(nu);
    u_current << 50.0, 25.0;
    Eigen::VectorXd y_free = Eigen::VectorXd::Zero(P * ny);

    auto qpc = ch.buildForQP(dynmat, u_current, y_free);

    // Expected: 2*M*nu + P*ny = 2*3*2 + 5*2 = 22
    EXPECT_EQ(qpc.num_constraints, 2 * M * nu + P * ny);
    EXPECT_EQ(qpc.A.rows(), qpc.num_constraints);
    EXPECT_EQ(qpc.A.cols(), M * nu);
    EXPECT_EQ(qpc.lb.size(), qpc.num_constraints);
    EXPECT_EQ(qpc.ub.size(), qpc.num_constraints);
}

TEST(ConstraintHandler, BuildForQP_MoveConstraintStructure)
{
    int nu = 1, ny = 1, M = 2, P = 3;
    ConstraintHandler ch(nu, ny, M, P);

    Eigen::VectorXd du_lb(1), du_ub(1);
    du_lb << -1.0;
    du_ub << 1.0;
    ch.setMVRateBounds(du_lb, du_ub);

    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    DynamicMatrix dynmat(model, P, M);

    auto qpc = ch.buildForQP(dynmat, Eigen::VectorXd::Zero(nu),
                               Eigen::VectorXd::Zero(P * ny));

    // First M*nu rows are identity (du bounds)
    Eigen::MatrixXd A_dense = qpc.A;
    for (int j = 0; j < M * nu; ++j) {
        EXPECT_DOUBLE_EQ(A_dense(j, j), 1.0);
        EXPECT_DOUBLE_EQ(qpc.lb[j], -1.0);
        EXPECT_DOUBLE_EQ(qpc.ub[j], 1.0);
    }
}

TEST(ConstraintHandler, BuildForQP_MVAbsConstraints)
{
    int nu = 1, ny = 1, M = 2, P = 3;
    ConstraintHandler ch(nu, ny, M, P);

    Eigen::VectorXd mv_lb(1), mv_ub(1);
    mv_lb << 10.0;
    mv_ub << 90.0;
    ch.setMVBounds(mv_lb, mv_ub);

    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    DynamicMatrix dynmat(model, P, M);

    Eigen::VectorXd u_current(1);
    u_current << 50.0;

    auto qpc = ch.buildForQP(dynmat, u_current, Eigen::VectorXd::Zero(P));

    // P1 rows: bounds are mv_lb - u_current to mv_ub - u_current
    for (int j = 0; j < M; ++j) {
        EXPECT_DOUBLE_EQ(qpc.lb[M * nu + j], -40.0);
        EXPECT_DOUBLE_EQ(qpc.ub[M * nu + j], 40.0);
    }
}

TEST(ConstraintHandler, BuildForQP_CVConstraints)
{
    int nu = 1, ny = 1, M = 2, P = 3;
    ConstraintHandler ch(nu, ny, M, P);

    Eigen::VectorXd cv_lb(1), cv_ub(1);
    cv_lb << 0.0;
    cv_ub << 2.0;
    ch.setCVOperatingBounds(cv_lb, cv_ub);

    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    DynamicMatrix dynmat(model, P, M);

    Eigen::VectorXd y_free(P);
    y_free << 0.5, 0.8, 1.0;

    auto qpc = ch.buildForQP(dynmat, Eigen::VectorXd::Zero(nu), y_free);

    // CV rows start at 2*M*nu = 4
    int cv_start = 2 * M * nu;
    for (int j = 0; j < P; ++j) {
        EXPECT_DOUBLE_EQ(qpc.lb[cv_start + j], -y_free[j]);
        EXPECT_DOUBLE_EQ(qpc.ub[cv_start + j], 2.0 - y_free[j]);
    }
}

// ============================================================================
// Feasibility check
// ============================================================================

TEST(ConstraintHandler, FeasibilityCheck_OK)
{
    ConstraintHandler ch(2, 1, 3, 5);
    Eigen::VectorXd lb(2), ub(2);
    lb << 0.0, 0.0;
    ub << 100.0, 50.0;
    ch.setMVBounds(lb, ub);

    Eigen::VectorXd u(2);
    u << 50.0, 25.0;
    EXPECT_TRUE(ch.checkFeasibility(u).feasible);
}

TEST(ConstraintHandler, FeasibilityCheck_OutOfBounds)
{
    ConstraintHandler ch(2, 1, 3, 5);
    Eigen::VectorXd lb(2), ub(2);
    lb << 0.0, 0.0;
    ub << 100.0, 50.0;
    ch.setMVBounds(lb, ub);

    Eigen::VectorXd u(2);
    u << 150.0, 25.0;
    auto report = ch.checkFeasibility(u);
    EXPECT_FALSE(report.feasible);
    EXPECT_EQ(report.highest_infeasible_priority, 1);
}

// ============================================================================
// Online updates
// ============================================================================

TEST(ConstraintHandler, OnlineUpdateMVBound)
{
    ConstraintHandler ch(2, 1, 3, 5);
    ch.setMVBounds(Eigen::VectorXd::Zero(2), Eigen::VectorXd::Constant(2, 100.0));
    ch.updateMVBound(0, 10.0, 80.0);

    Eigen::VectorXd u(2);
    u << 5.0, 25.0;
    EXPECT_FALSE(ch.checkFeasibility(u).feasible);
}

TEST(ConstraintHandler, OnlineUpdateRate)
{
    int nu = 1, ny = 1, M = 2, P = 3;
    ConstraintHandler ch(nu, ny, M, P);
    ch.updateMVRateLimit(0, 0.5);

    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    DynamicMatrix dynmat(model, P, M);
    auto qpc = ch.buildForQP(dynmat, Eigen::VectorXd::Zero(1),
                               Eigen::VectorXd::Zero(P));

    EXPECT_DOUBLE_EQ(qpc.lb[0], -0.5);
    EXPECT_DOUBLE_EQ(qpc.ub[0], 0.5);
}
