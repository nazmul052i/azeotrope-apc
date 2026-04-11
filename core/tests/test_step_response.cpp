#include <gtest/gtest.h>
#include "azeoapc/step_response_model.h"
#include <cmath>

using namespace azeoapc;

// ============================================================================
// Construction
// ============================================================================

TEST(StepResponseModel, ConstructorBasic)
{
    StepResponseModel m(2, 3, 60, 1.0);
    EXPECT_EQ(m.ny(), 2);
    EXPECT_EQ(m.nu(), 3);
    EXPECT_EQ(m.modelHorizon(), 60);
    EXPECT_DOUBLE_EQ(m.sampleTime(), 1.0);

    // All coefficients should be zero
    EXPECT_DOUBLE_EQ(m.coefficient(0, 0, 0), 0.0);
    EXPECT_DOUBLE_EQ(m.coefficient(1, 59, 2), 0.0);
}

TEST(StepResponseModel, ConstructorRejectsInvalid)
{
    EXPECT_THROW(StepResponseModel(0, 1, 10, 1.0), std::invalid_argument);
    EXPECT_THROW(StepResponseModel(1, 0, 10, 1.0), std::invalid_argument);
    EXPECT_THROW(StepResponseModel(1, 1, 0, 1.0), std::invalid_argument);
    EXPECT_THROW(StepResponseModel(1, 1, 10, 0.0), std::invalid_argument);
}

// ============================================================================
// fromFOPTD
// ============================================================================

TEST(StepResponseModel, FromFOPTD_Basic)
{
    // FOPTD: K=2.0, tau=10.0, L=3.0, dt=1.0, N=60
    double K = 2.0, tau = 10.0, L = 3.0, dt = 1.0;
    int N = 60;
    auto model = StepResponseModel::fromFOPTD(K, tau, L, dt, N);

    EXPECT_EQ(model.ny(), 1);
    EXPECT_EQ(model.nu(), 1);
    EXPECT_EQ(model.modelHorizon(), N);

    // Steps within dead time should be zero
    // S_stored[k] is response at time (k+1)*dt
    // t=1,2,3 <= L=3 -> zero
    EXPECT_DOUBLE_EQ(model.coefficient(0, 0, 0), 0.0);  // t=1
    EXPECT_DOUBLE_EQ(model.coefficient(0, 1, 0), 0.0);  // t=2
    EXPECT_DOUBLE_EQ(model.coefficient(0, 2, 0), 0.0);  // t=3

    // t=4 > L=3: K*(1 - exp(-(4-3)/10)) = 2*(1-exp(-0.1))
    double expected = K * (1.0 - std::exp(-1.0 / tau));
    EXPECT_NEAR(model.coefficient(0, 3, 0), expected, 1e-10);

    // Steady state: should approach K=2.0
    EXPECT_NEAR(model.coefficient(0, N - 1, 0), K, 0.01);
}

TEST(StepResponseModel, FromFOPTD_NoDeadTime)
{
    double K = 1.5, tau = 5.0, L = 0.0, dt = 1.0;
    int N = 50;
    auto model = StepResponseModel::fromFOPTD(K, tau, L, dt, N);

    // First step: K*(1 - exp(-1/5)) = 1.5*(1-exp(-0.2))
    double expected = K * (1.0 - std::exp(-dt / tau));
    EXPECT_NEAR(model.coefficient(0, 0, 0), expected, 1e-10);
    EXPECT_GT(model.coefficient(0, 0, 0), 0.0);
}

TEST(StepResponseModel, FromFOPTD_Monotonic)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 100);

    // Step response must be monotonically increasing for positive gain
    for (int k = 1; k < 100; ++k)
        EXPECT_GE(model.coefficient(0, k, 0), model.coefficient(0, k - 1, 0));
}

// ============================================================================
// fromStateSpace
// ============================================================================

TEST(StepResponseModel, FromStateSpace_FirstOrder)
{
    // Discrete first-order: x[k+1] = a*x[k] + b*u[k], y[k] = x[k]
    // Equivalent to FOPTD with tau=10, K=1, L=0, dt=1
    double tau = 10.0, dt = 1.0, K = 1.0;
    double a = std::exp(-dt / tau);
    double b = K * (1.0 - a);

    Eigen::MatrixXd A(1, 1), B(1, 1), C(1, 1), D(1, 1);
    A << a;
    B << b;
    C << 1.0;
    D << 0.0;

    int N = 60;
    auto ss_model = StepResponseModel::fromStateSpace(A, B, C, D, N, dt);
    auto foptd_model = StepResponseModel::fromFOPTD(K, tau, 0.0, dt, N);

    // Both should produce identical step responses
    for (int k = 0; k < N; ++k) {
        EXPECT_NEAR(ss_model.coefficient(0, k, 0),
                    foptd_model.coefficient(0, k, 0), 1e-10)
            << "Mismatch at step " << k;
    }
}

TEST(StepResponseModel, FromStateSpace_SecondOrder)
{
    // 2nd-order discrete system (already discretized):
    //   x[k+1] = A*x[k] + B*u[k], y[k] = C*x[k]
    // Poles at 0.8 and 0.5 (stable)
    Eigen::MatrixXd A(2, 2), B(2, 1), C(1, 2), D(1, 1);
    A << 0.8, 0.0,
         0.0, 0.5;
    B << 1.0,
         1.0;
    C << 1.0, 1.0;
    D << 0.0;

    int N = 50;
    auto model = StepResponseModel::fromStateSpace(A, B, C, D, N, 1.0);

    // Manual verification for first few steps:
    // x[0]=0, u=1
    // x[1] = B = [1; 1], y[1] = C*x[1] = 2   -> S_stored[0] = 2
    EXPECT_NEAR(model.coefficient(0, 0, 0), 2.0, 1e-10);

    // x[2] = A*[1;1]+B = [0.8+1; 0.5+1] = [1.8; 1.5]
    // cumul = [1;1] + [1.8;1.5] = wait, let me redo.
    // cumul after k=0: B = [1;1], S[1] = C*[1;1] = 2 ✓
    // A_power_B = A*B = [0.8; 0.5]
    // cumul after k=1: [1;1]+[0.8;0.5] = [1.8;1.5], S[2] = C*[1.8;1.5] = 3.3
    EXPECT_NEAR(model.coefficient(0, 1, 0), 3.3, 1e-10);

    // Steady state: sum A^j*B = (I-A)^{-1}*B = [1/(1-0.8); 1/(1-0.5)] = [5; 2]
    // SS gain = C * [5;2] = 7
    EXPECT_NEAR(model.steadyStateGain()(0, 0), 7.0, 0.05);
}

TEST(StepResponseModel, FromStateSpace_MIMO)
{
    // 2-output, 2-input system, 1 state per channel
    Eigen::MatrixXd A(2, 2), B(2, 2), C(2, 2), D(2, 2);
    A << 0.9, 0.0,
         0.0, 0.8;
    B << 1.0, 0.5,
         0.0, 1.0;
    C << 1.0, 0.0,
         0.0, 1.0;
    D << 0.0, 0.0,
         0.0, 0.0;

    int N = 60;
    auto model = StepResponseModel::fromStateSpace(A, B, C, D, N, 1.0);
    EXPECT_EQ(model.ny(), 2);
    EXPECT_EQ(model.nu(), 2);

    // Steady-state gain = C * (I-A)^{-1} * B
    // (I-A)^{-1} = diag(10, 5)
    // G = C * diag(10,5) * B = [[10, 5], [0, 5]]
    auto G = model.steadyStateGain();
    EXPECT_NEAR(G(0, 0), 10.0, 0.1);
    EXPECT_NEAR(G(0, 1), 5.0, 0.1);
    EXPECT_NEAR(G(1, 0), 0.0, 0.1);
    EXPECT_NEAR(G(1, 1), 5.0, 0.1);
}

TEST(StepResponseModel, FromStateSpace_WithFeedthrough)
{
    // System with D != 0
    Eigen::MatrixXd A(1, 1), B(1, 1), C(1, 1), D(1, 1);
    A << 0.5;
    B << 1.0;
    C << 1.0;
    D << 0.5;   // direct feedthrough

    auto model = StepResponseModel::fromStateSpace(A, B, C, D, 30, 1.0);

    // S_stored[0] = C*B + D = 1.0 + 0.5 = 1.5
    EXPECT_NEAR(model.coefficient(0, 0, 0), 1.5, 1e-10);

    // S_stored[1] = C*(B + A*B) + D = (1 + 0.5) + 0.5 = 2.0
    EXPECT_NEAR(model.coefficient(0, 1, 0), 2.0, 1e-10);

    // SS: C * (I-A)^{-1} * B + D = 1*(1/0.5)*1 + 0.5 = 2.5
    EXPECT_NEAR(model.steadyStateGain()(0, 0), 2.5, 0.05);
}

// ============================================================================
// fromFOPTDMatrix (MIMO)
// ============================================================================

TEST(StepResponseModel, FromFOPTDMatrix_2x2)
{
    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K   << 1.0, 0.5,
           0.3, 2.0;
    tau << 10.0, 5.0,
           8.0, 15.0;
    L   << 1.0, 2.0,
           0.0, 3.0;

    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 60);

    EXPECT_EQ(model.ny(), 2);
    EXPECT_EQ(model.nu(), 2);

    // Check steady-state gains approach K (tau=15 needs longer horizon to settle)
    auto G = model.steadyStateGain();
    EXPECT_NEAR(G(0, 0), 1.0, 0.02);
    EXPECT_NEAR(G(0, 1), 0.5, 0.02);
    EXPECT_NEAR(G(1, 0), 0.3, 0.02);
    EXPECT_NEAR(G(1, 1), 2.0, 0.1);  // tau=15, N=60 -> ~2% residual
}

// ============================================================================
// Accessor methods
// ============================================================================

TEST(StepResponseModel, StepResponseVector)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto sr = model.stepResponse(0, 0);
    EXPECT_EQ(sr.size(), 30);

    for (int k = 0; k < 30; ++k)
        EXPECT_DOUBLE_EQ(sr[k], model.coefficient(0, k, 0));
}

TEST(StepResponseModel, CoefficientMatrix)
{
    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K << 1.0, 0.5, 0.3, 2.0;
    tau << 10.0, 5.0, 8.0, 15.0;
    L << 0.0, 0.0, 0.0, 0.0;

    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 30);
    auto S5 = model.coefficientMatrix(5);

    EXPECT_EQ(S5.rows(), 2);
    EXPECT_EQ(S5.cols(), 2);
    for (int cv = 0; cv < 2; ++cv)
        for (int mv = 0; mv < 2; ++mv)
            EXPECT_DOUBLE_EQ(S5(cv, mv), model.coefficient(cv, 5, mv));
}

TEST(StepResponseModel, CoefficientOutOfRange)
{
    StepResponseModel m(1, 1, 10, 1.0);
    EXPECT_THROW(m.coefficient(-1, 0, 0), std::out_of_range);
    EXPECT_THROW(m.coefficient(0, 10, 0), std::out_of_range);
    EXPECT_THROW(m.coefficient(0, 0, 1), std::out_of_range);
}

// ============================================================================
// Metadata
// ============================================================================

TEST(StepResponseModel, MetadataNames)
{
    StepResponseModel m(2, 1, 10, 1.0);
    m.setCVNames({"Temp", "Pressure"});
    m.setMVNames({"Valve"});
    EXPECT_EQ(m.cvNames().size(), 2u);
    EXPECT_EQ(m.cvNames()[0], "Temp");
    EXPECT_EQ(m.mvNames()[0], "Valve");
}

// ============================================================================
// Prediction
// ============================================================================

TEST(StepResponseModel, PredictFree_ZeroPastMoves)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    int P = 10;
    Eigen::MatrixXd past_moves = Eigen::MatrixXd::Zero(30, 1);
    auto y_free = model.predictFree(past_moves, P);

    EXPECT_EQ(y_free.size(), P);
    for (int i = 0; i < P; ++i)
        EXPECT_NEAR(y_free[i], 0.0, 1e-12);
}

TEST(StepResponseModel, PredictForced_SingleStep)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    int P = 10, M = 1;

    // Single unit move at k
    Eigen::VectorXd du(1);
    du << 1.0;
    auto y_forced = model.predictForced(du, P, M);

    EXPECT_EQ(y_forced.size(), P);

    // y_forced[j-1] = S_stored[j-1] * 1.0 = step response at step j
    for (int j = 0; j < P; ++j)
        EXPECT_NEAR(y_forced[j], model.coefficient(0, j, 0), 1e-12);
}

TEST(StepResponseModel, PredictFree_MatchesForcedHistory)
{
    // If we apply a step du=1 at time k-5 and nothing else,
    // the free response at k+j should match the step response S[j+5].
    auto model = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 60);
    int N = 60, P = 10;

    Eigen::MatrixXd past_moves = Eigen::MatrixXd::Zero(N, 1);
    past_moves(4, 0) = 1.0;  // du[k-5] = 1.0 (row 4 = 5th most recent)

    auto y_free = model.predictFree(past_moves, P);

    // y_free[j-1] = sum_m S_stored[m+j-1] * past(m-1)
    // Only m=5 contributes: S_stored[5+j-1] * 1.0 = S_stored[j+4]
    for (int j = 1; j <= P; ++j) {
        int s_idx = j + 4;
        if (s_idx < N)
            EXPECT_NEAR(y_free[j - 1], model.coefficient(0, s_idx, 0), 1e-10)
                << "Mismatch at j=" << j;
    }
}
