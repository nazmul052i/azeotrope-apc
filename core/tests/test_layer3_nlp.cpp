#include <gtest/gtest.h>
#include "azeoapc/layer3_nlp.h"
#include <cmath>

using namespace azeoapc;

// ============================================================================
// Construction
// ============================================================================

TEST(Layer3NLP, Construction_Codegen)
{
    Layer3Config cfg;
    cfg.model_source = "codegen";
    cfg.execution_interval_sec = 3600;
    cfg.nlp_max_iter = 100;
    cfg.nlp_tolerance = 1e-6;

    EXPECT_NO_THROW(Layer3NLP("", cfg));
}

// ============================================================================
// Numerical linearization
// ============================================================================

TEST(Layer3NLP, LinearizeAt_FirstOrder)
{
    // Discrete first-order system: x_next = 0.9*x + 0.5*u
    Layer3Config cfg;
    cfg.model_source = "codegen";
    Layer3NLP nlp("", cfg);

    nlp.setModelFunction([](const Eigen::VectorXd& x, const Eigen::VectorXd& u)
        -> Eigen::VectorXd {
        Eigen::VectorXd xn(1);
        xn[0] = 0.9 * x[0] + 0.5 * u[0];
        return xn;
    });

    Eigen::VectorXd x_op(1), u_op(1);
    x_op << 0.0;
    u_op << 0.0;

    auto ss = nlp.linearizeAt(x_op, u_op);

    EXPECT_NEAR(ss.A(0, 0), 0.9, 1e-4);
    EXPECT_NEAR(ss.B(0, 0), 0.5, 1e-4);
    EXPECT_DOUBLE_EQ(ss.C(0, 0), 1.0);
    EXPECT_DOUBLE_EQ(ss.D(0, 0), 0.0);
}

TEST(Layer3NLP, LinearizeAt_Nonlinear)
{
    // Nonlinear system: x_next = x^2 + u
    // At x_op=1, u_op=0: df/dx = 2*x_op = 2, df/du = 1
    Layer3Config cfg;
    Layer3NLP nlp("", cfg);

    nlp.setModelFunction([](const Eigen::VectorXd& x, const Eigen::VectorXd& u)
        -> Eigen::VectorXd {
        Eigen::VectorXd xn(1);
        xn[0] = x[0] * x[0] + u[0];
        return xn;
    });

    Eigen::VectorXd x_op(1), u_op(1);
    x_op << 1.0;
    u_op << 0.0;

    auto ss = nlp.linearizeAt(x_op, u_op);

    EXPECT_NEAR(ss.A(0, 0), 2.0, 1e-4);   // df/dx = 2*x = 2
    EXPECT_NEAR(ss.B(0, 0), 1.0, 1e-4);   // df/du = 1
}

TEST(Layer3NLP, LinearizeAt_MIMO)
{
    // 2-state, 2-input system:
    // x1_next = 0.8*x1 + 0.2*x2 + u1
    // x2_next = 0.1*x1 + 0.7*x2 + u2
    Layer3Config cfg;
    Layer3NLP nlp("", cfg);

    nlp.setModelFunction([](const Eigen::VectorXd& x, const Eigen::VectorXd& u)
        -> Eigen::VectorXd {
        Eigen::VectorXd xn(2);
        xn[0] = 0.8 * x[0] + 0.2 * x[1] + u[0];
        xn[1] = 0.1 * x[0] + 0.7 * x[1] + u[1];
        return xn;
    });

    auto ss = nlp.linearizeAt(Eigen::VectorXd::Zero(2), Eigen::VectorXd::Zero(2));

    EXPECT_NEAR(ss.A(0, 0), 0.8, 1e-4);
    EXPECT_NEAR(ss.A(0, 1), 0.2, 1e-4);
    EXPECT_NEAR(ss.A(1, 0), 0.1, 1e-4);
    EXPECT_NEAR(ss.A(1, 1), 0.7, 1e-4);
    EXPECT_NEAR(ss.B(0, 0), 1.0, 1e-4);
    EXPECT_NEAR(ss.B(1, 1), 1.0, 1e-4);
    EXPECT_NEAR(ss.B(0, 1), 0.0, 1e-4);
    EXPECT_NEAR(ss.B(1, 0), 0.0, 1e-4);
}

TEST(Layer3NLP, LinearizeAt_CSTR)
{
    // Simplified CSTR: 2 states (c, T), 1 input (Tc)
    // c_next = f1(c, T, Tc)
    // T_next = f2(c, T, Tc)
    // Simple Euler: x_next = x + dt * ode(x, u)
    double dt = 0.5;
    double k0 = 7.2e10, E_a = 8750, K_gain = 1.0;
    double rho_Cp = 1000.0 * 0.239;  // rho * Cp

    Layer3Config cfg;
    Layer3NLP nlp("", cfg);

    nlp.setModelFunction([=](const Eigen::VectorXd& x, const Eigen::VectorXd& u)
        -> Eigen::VectorXd {
        double c = x[0], T = x[1], Tc = u[0];
        double rate = k0 * c * std::exp(-E_a / T);

        Eigen::VectorXd xn(2);
        // Simplified (no level dynamics)
        xn[0] = c + dt * (-rate);
        xn[1] = T + dt * ((-5e4 / rho_Cp) * rate + (2 * 54.94 / (0.219 * rho_Cp)) * (Tc - T));
        return xn;
    });

    Eigen::VectorXd x_op(2), u_op(1);
    x_op << 0.878, 324.5;
    u_op << 300.0;

    auto ss = nlp.linearizeAt(x_op, u_op);

    // Check dimensions
    EXPECT_EQ(ss.A.rows(), 2);
    EXPECT_EQ(ss.A.cols(), 2);
    EXPECT_EQ(ss.B.rows(), 2);
    EXPECT_EQ(ss.B.cols(), 1);

    // A diagonal: close to 1 for concentration, may be < 1 for temperature
    // (strong heat transfer creates fast dynamics)
    EXPECT_NEAR(ss.A(0, 0), 1.0, 0.5);
    EXPECT_LT(std::abs(ss.A(1, 1)), 3.0);  // finite value, possibly negative

    // B: Tc should affect T (row 1) but not c (row 0) much
    EXPECT_GT(std::abs(ss.B(1, 0)), std::abs(ss.B(0, 0)));
}

// ============================================================================
// Linearization without model should throw
// ============================================================================

TEST(Layer3NLP, LinearizeAt_NoModel_Throws)
{
    Layer3Config cfg;
    Layer3NLP nlp("", cfg);

    EXPECT_THROW(nlp.linearizeAt(Eigen::VectorXd::Zero(1), Eigen::VectorXd::Zero(1)),
                 std::runtime_error);
}

// ============================================================================
// Solve returns current point (no CasADi)
// ============================================================================

TEST(Layer3NLP, Solve_ReturnsCurrentPoint)
{
    Layer3Config cfg;
    Layer3NLP nlp("", cfg);

    Eigen::VectorXd x(2), u(1);
    x << 1.0, 2.0;
    u << 0.5;

    auto result = nlp.solve(x, u);
    EXPECT_EQ(result.status, SolverStatus::OPTIMAL);
    EXPECT_DOUBLE_EQ(result.u_optimal[0], u[0]);
}

// ============================================================================
// Layer 3 -> Layer 2 integration: re-linearize and update gain
// ============================================================================

TEST(Layer3NLP, RelinearizationUpdatesGain)
{
    // Simulate the 3-layer flow:
    // 1. Layer 3 linearizes at new operating point
    // 2. Layer 2 uses updated gain matrix
    Layer3Config cfg;
    Layer3NLP nlp("", cfg);

    // Simple nonlinear model: y = K(x) * u where K depends on state
    nlp.setModelFunction([](const Eigen::VectorXd& x, const Eigen::VectorXd& u)
        -> Eigen::VectorXd {
        Eigen::VectorXd xn(1);
        xn[0] = (1.0 + 0.1 * x[0]) * u[0];  // gain varies with state
        return xn;
    });

    // Linearize at x=0: gain ≈ 1.0
    auto ss1 = nlp.linearizeAt(Eigen::VectorXd::Zero(1), Eigen::VectorXd::Zero(1));
    EXPECT_NEAR(ss1.B(0, 0), 1.0, 0.01);

    // Linearize at x=5: gain ≈ 1.5
    Eigen::VectorXd x_new(1);
    x_new << 5.0;
    auto ss2 = nlp.linearizeAt(x_new, Eigen::VectorXd::Zero(1));
    EXPECT_NEAR(ss2.B(0, 0), 1.5, 0.01);
}
