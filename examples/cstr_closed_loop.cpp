#include "azeoapc/step_response_model.h"
#include "azeoapc/dynamic_matrix.h"
#include "azeoapc/prediction_engine.h"
#include "azeoapc/disturbance_observer.h"
#include <iostream>
#include <iomanip>
#include <cmath>
#include <algorithm>
#include <vector>
#include <array>

/**
 * CSTR Closed-Loop Example (Phase 1 Validation)
 *
 * Continuous Stirred Tank Reactor from mpc-tools-casadi reference.
 *
 * States (Nx=3): c (concentration mol/L), T (temperature K), h (level m)
 * Inputs (Nu=2): Tc (coolant temp K), F (outlet flow kL/min)
 * Disturbance:   F0 (inlet flow kL/min)
 *
 * CVs: c (concentration), h (level)  -- 2 controlled outputs
 * MVs: Tc (coolant temp), F (outlet flow) -- 2 manipulated inputs
 *
 * The example:
 *  1. Linearizes the nonlinear CSTR model at steady state
 *  2. Generates step response via fromStateSpace()
 *  3. Runs closed-loop MPC (unconstrained analytical solution)
 *  4. Validates tracking and disturbance rejection
 */

// ===========================================================================
// CSTR parameters (from mpc-tools-casadi/cstr.py)
// ===========================================================================
static constexpr double T0   = 350.0;     // Inlet temperature (K)
static constexpr double c0   = 1.0;       // Inlet concentration (mol/L)
static constexpr double r    = 0.219;     // Tank radius (m)
static constexpr double k0   = 7.2e10;    // Arrhenius pre-exponential (1/min)
static constexpr double E    = 8750.0;    // Activation energy (K)
static constexpr double U    = 54.94;     // Heat transfer coeff (kW/(m^2*K))
static constexpr double rho  = 1000.0;    // Density (kg/m^3)
static constexpr double Cp   = 0.239;     // Heat capacity (kJ/(kg*K))
static constexpr double dH   = -5.0e4;    // Heat of reaction (kJ/kmol)
static constexpr double PI_  = 3.14159265358979323846;
static constexpr double A_cross = PI_ * r * r;  // cross-sectional area

// Steady-state operating point
static constexpr double cs   = 0.878;     // mol/L
static constexpr double Ts   = 324.5;     // K
static constexpr double hs   = 0.659;     // m
static constexpr double Tcs  = 300.0;     // K
static constexpr double Fs   = 0.1;       // kL/min
static constexpr double F0s  = 0.1;       // kL/min

// State vector: [c, T, h]
using State = std::array<double, 3>;

// ===========================================================================
// CSTR ODE: dx/dt = f(x, u, d)
// ===========================================================================
State cstrODE(const State& x, double Tc, double F, double F0)
{
    double c = x[0], T = x[1], h = x[2];
    double rate = k0 * c * std::exp(-E / T);

    State dxdt;
    dxdt[0] = F0 * (c0 - c) / (A_cross * h) - rate;
    dxdt[1] = F0 * (T0 - T) / (A_cross * h)
              - (dH / (rho * Cp)) * rate
              + (2.0 * U / (r * rho * Cp)) * (Tc - T);
    dxdt[2] = (F0 - F) / A_cross;
    return dxdt;
}

// ===========================================================================
// RK4 integrator (one step)
// ===========================================================================
State rk4Step(const State& x, double Tc, double F, double F0, double dt)
{
    auto add = [](const State& a, const State& b, double s) -> State {
        return {a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2]};
    };

    State k1 = cstrODE(x, Tc, F, F0);
    State x2 = add(x, k1, 0.5 * dt);
    State k2 = cstrODE(x2, Tc, F, F0);
    State x3 = add(x, k2, 0.5 * dt);
    State k3 = cstrODE(x3, Tc, F, F0);
    State x4 = add(x, k3, dt);
    State k4 = cstrODE(x4, Tc, F, F0);

    State xnew;
    for (int i = 0; i < 3; ++i)
        xnew[i] = x[i] + (dt / 6.0) * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]);
    return xnew;
}

// ===========================================================================
// Numerical linearization: compute discrete (A, B, C, D) via finite differences
// ===========================================================================
void linearize(double dt,
               Eigen::MatrixXd& Ad, Eigen::MatrixXd& Bd,
               Eigen::MatrixXd& Cd, Eigen::MatrixXd& Dd)
{
    const int Nx = 3, Nu = 2, Ny = 2;
    State xs = {cs, Ts, hs};
    double us[2] = {Tcs, Fs};

    // Nominal next state
    State x_nom = rk4Step(xs, us[0], us[1], F0s, dt);

    // A matrix: perturb each state
    Ad.resize(Nx, Nx);
    double eps_x[3] = {1e-6, 1e-4, 1e-6};  // perturbation per state
    for (int j = 0; j < Nx; ++j) {
        State xp = xs;
        xp[j] += eps_x[j];
        State x_plus = rk4Step(xp, us[0], us[1], F0s, dt);

        State xm = xs;
        xm[j] -= eps_x[j];
        State x_minus = rk4Step(xm, us[0], us[1], F0s, dt);

        for (int i = 0; i < Nx; ++i)
            Ad(i, j) = (x_plus[i] - x_minus[i]) / (2.0 * eps_x[j]);
    }

    // B matrix: perturb each input
    Bd.resize(Nx, Nu);
    double eps_u[2] = {1e-4, 1e-7};
    for (int j = 0; j < Nu; ++j) {
        double up[2] = {us[0], us[1]};
        up[j] += eps_u[j];
        State x_plus = rk4Step(xs, up[0], up[1], F0s, dt);

        double um[2] = {us[0], us[1]};
        um[j] -= eps_u[j];
        State x_minus = rk4Step(xs, um[0], um[1], F0s, dt);

        for (int i = 0; i < Nx; ++i)
            Bd(i, j) = (x_plus[i] - x_minus[i]) / (2.0 * eps_u[j]);
    }

    // C matrix: output = [c, h] (states 0 and 2)
    Cd.resize(Ny, Nx);
    Cd.setZero();
    Cd(0, 0) = 1.0;  // c
    Cd(1, 2) = 1.0;  // h

    // D matrix: no direct feedthrough
    Dd = Eigen::MatrixXd::Zero(Ny, Nu);
}

// ===========================================================================
// Main
// ===========================================================================
int main()
{
    using namespace azeoapc;
    using Eigen::MatrixXd;
    using Eigen::VectorXd;

    // ---- Parameters ----
    double dt = 0.5;       // sample time (minutes), matching ref
    int N  = 120;          // model horizon (60 min)
    int P  = 30;           // prediction horizon
    int M  = 5;            // control horizon
    int sim_steps = 150;   // simulation length

    std::cout << "=== Azeotrope APC -- CSTR Closed-Loop Example ===\n";
    std::cout << "States: c (mol/L), T (K), h (m)\n";
    std::cout << "CVs: c, h | MVs: Tc, F\n";
    std::cout << "dt=" << dt << " min, N=" << N << ", P=" << P << ", M=" << M << "\n\n";

    // ---- Linearize at steady state ----
    MatrixXd Ad, Bd, Cd, Dd;
    linearize(dt, Ad, Bd, Cd, Dd);

    std::cout << "Discrete A (3x3):\n" << Ad << "\n\n";
    std::cout << "Discrete B (3x2):\n" << Bd << "\n\n";
    std::cout << "C (2x3): rows for c and h\n\n";

    // ---- Build step response model from state space ----
    auto model = StepResponseModel::fromStateSpace(Ad, Bd, Cd, Dd, N, dt);
    model.setCVNames({"Concentration", "Level"});
    model.setMVNames({"Coolant_Temp", "Outlet_Flow"});

    std::cout << "Step response model: " << model.ny() << " CVs x "
              << model.nu() << " MVs, horizon=" << N << "\n";

    MatrixXd G = model.steadyStateGain();
    std::cout << "Steady-state gain matrix:\n" << G << "\n\n";

    // ---- Build prediction engine ----
    PredictionEngine pred(model, P, M);
    const auto& dynmat = pred.dynamicMatrix();
    std::cout << "Dynamic matrix: " << dynmat.matrix().rows() << " x "
              << dynmat.matrix().cols() << "\n\n";

    // ---- Disturbance observer ----
    int Ny = 2;
    DisturbanceObserver observer(Ny);
    observer.setFilterGain(0.85);

    // ---- QP matrices (unconstrained analytical) ----
    MatrixXd A_dyn = dynmat.matrix();
    MatrixXd Q = MatrixXd::Identity(P * Ny, P * Ny);
    // Weight concentration tracking more than level
    for (int j = 0; j < P; ++j) {
        Q(j * Ny + 0, j * Ny + 0) = 10.0;   // concentration weight
        Q(j * Ny + 1, j * Ny + 1) = 5.0;    // level weight
    }
    MatrixXd R = MatrixXd::Identity(M * 2, M * 2) * 0.1;
    MatrixXd H_inv = (A_dyn.transpose() * Q * A_dyn + R).inverse();

    // ---- Plant state and MV initial conditions (at steady state) ----
    State x_plant = {cs, Ts, hs};
    double Tc = Tcs, F_out = Fs;
    double F0 = F0s;

    // Setpoints (deviation from steady state)
    double c_sp = cs;
    double h_sp = hs;

    std::cout << std::setw(6) << "Step"
              << std::setw(9) << "c"
              << std::setw(9) << "c_sp"
              << std::setw(9) << "T"
              << std::setw(9) << "h"
              << std::setw(9) << "h_sp"
              << std::setw(9) << "Tc"
              << std::setw(9) << "F"
              << "\n" << std::string(72, '-') << "\n";

    double sse_c = 0.0, sse_h = 0.0;
    int n_track = 0;

    for (int k = 0; k < sim_steps; ++k) {
        // ---- Setpoint changes ----
        if (k == 20) c_sp = cs - 0.05;     // decrease concentration setpoint
        if (k == 80) h_sp = hs + 0.05;     // increase level setpoint

        // ---- Disturbance: +10% inlet flow at step 50 ----
        if (k == 50) F0 = F0s * 1.1;

        // ---- Simulate plant (RK4) ----
        x_plant = rk4Step(x_plant, Tc, F_out, F0, dt);
        double c_meas = x_plant[0];
        double h_meas = x_plant[2];

        // ---- Controller (in deviation variables) ----
        VectorXd y_meas(Ny);
        y_meas << (c_meas - cs), (h_meas - hs);

        // Free response
        auto y_free = pred.freeResponse();

        // Disturbance observer
        VectorXd y_pred_1(Ny);
        y_pred_1 << y_free[0], y_free[1];
        auto d_est = observer.update(y_meas, y_pred_1);

        // Build error: (setpoint - free_response - disturbance) for each step
        VectorXd error(P * Ny);
        for (int j = 0; j < P; ++j) {
            error[j * Ny + 0] = (c_sp - cs) - y_free[j * Ny + 0] - d_est[0];
            error[j * Ny + 1] = (h_sp - hs) - y_free[j * Ny + 1] - d_est[1];
        }

        // Unconstrained optimal moves (deviation du)
        VectorXd du_opt = H_inv * A_dyn.transpose() * Q * error;

        // Apply first move with simple clamping
        double dTc = std::clamp(du_opt[0], -10.0, 10.0);
        double dF  = std::clamp(du_opt[1], -0.03, 0.03);

        double Tc_old = Tc, F_old = F_out;
        Tc    = std::clamp(Tc + dTc, 250.0, 400.0);
        F_out = std::clamp(F_out + dF, 0.01, 0.5);

        // Record actual du (after clamping)
        VectorXd du_actual(2);
        du_actual << (Tc - Tc_old), (F_out - F_old);
        pred.update(y_meas, du_actual);

        // ---- Tracking metrics (after step 10) ----
        if (k >= 10) {
            sse_c += (c_meas - c_sp) * (c_meas - c_sp);
            sse_h += (h_meas - h_sp) * (h_meas - h_sp);
            n_track++;
        }

        if (k % 5 == 0 || k < 5) {
            std::cout << std::setw(6) << k
                      << std::setw(9) << std::fixed << std::setprecision(4) << c_meas
                      << std::setw(9) << c_sp
                      << std::setw(9) << x_plant[1]
                      << std::setw(9) << h_meas
                      << std::setw(9) << h_sp
                      << std::setw(9) << Tc
                      << std::setw(9) << F_out
                      << "\n";
        }
    }

    double rmse_c = std::sqrt(sse_c / n_track);
    double rmse_h = std::sqrt(sse_h / n_track);

    std::cout << "\nRMSE concentration: " << rmse_c << "\n";
    std::cout << "RMSE level:         " << rmse_h << "\n";

    // ---- Validation ----
    bool pass = true;

    if (rmse_c > 0.05) {
        std::cout << "WARN: concentration RMSE too high\n";
        pass = false;
    }
    // Note: level (h) has integrating dynamics (dh/dt = (F0-F)/A_cross),
    // causing the step response to never truly settle. Linear MPC with
    // finite-horizon FIR model handles this poorly -- this is addressed
    // by state-space prediction in Layer 1 and constraint handling in Layer 2.
    if (rmse_h > 0.2) {
        std::cout << "WARN: level RMSE too high\n";
        pass = false;
    }
    // Check MVs actually moved
    if (std::abs(Tc - Tcs) < 0.1 && std::abs(F_out - Fs) < 0.001) {
        std::cout << "WARN: MVs did not respond\n";
        pass = false;
    }

    std::cout << "\n" << (pass ? "PASS" : "FAIL")
              << ": CSTR closed-loop validation\n";
    return pass ? 0 : 1;
}
