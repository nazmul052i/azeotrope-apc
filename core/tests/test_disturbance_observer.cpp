#include <gtest/gtest.h>
#include "azeoapc/disturbance_observer.h"
#include <cmath>

using namespace azeoapc;

// ============================================================================
// Construction
// ============================================================================

TEST(DisturbanceObserver, ConstructionDefaults)
{
    DisturbanceObserver obs(3);

    EXPECT_EQ(obs.estimate().size(), 3);
    EXPECT_DOUBLE_EQ(obs.estimate().sum(), 0.0);
}

TEST(DisturbanceObserver, RejectsInvalidNy)
{
    EXPECT_THROW(DisturbanceObserver(0), std::invalid_argument);
}

// ============================================================================
// Exponential filter
// ============================================================================

TEST(DisturbanceObserver, ExponentialFilter_StepDisturbance)
{
    // Constant prediction error -> filter should converge to the error
    DisturbanceObserver obs(1);
    obs.setFilterGain(0.8);

    Eigen::VectorXd y_meas(1), y_pred(1);
    y_meas << 5.0;
    y_pred << 3.0;  // constant error of 2.0

    // Run many iterations -- should converge to 2.0
    for (int i = 0; i < 200; ++i)
        obs.update(y_meas, y_pred);

    EXPECT_NEAR(obs.estimate()[0], 2.0, 0.01);
}

TEST(DisturbanceObserver, ExponentialFilter_FastGain)
{
    // Low alpha -> fast convergence
    DisturbanceObserver obs(1);
    obs.setFilterGain(0.0);  // instant convergence

    Eigen::VectorXd y_meas(1), y_pred(1);
    y_meas << 10.0;
    y_pred << 7.0;

    obs.update(y_meas, y_pred);
    EXPECT_NEAR(obs.estimate()[0], 3.0, 1e-10);
}

TEST(DisturbanceObserver, ExponentialFilter_MIMO)
{
    DisturbanceObserver obs(2);
    obs.setFilterGain(0.5);

    Eigen::VectorXd y_meas(2), y_pred(2);
    y_meas << 5.0, 10.0;
    y_pred << 3.0, 8.0;  // errors: [2, 2]

    for (int i = 0; i < 100; ++i)
        obs.update(y_meas, y_pred);

    EXPECT_NEAR(obs.estimate()[0], 2.0, 0.01);
    EXPECT_NEAR(obs.estimate()[1], 2.0, 0.01);
}

TEST(DisturbanceObserver, ExponentialFilter_TimeVarying)
{
    DisturbanceObserver obs(1);
    obs.setFilterGain(0.5);

    Eigen::VectorXd y_meas(1), y_pred(1);
    y_pred << 0.0;

    // Step from error=1 to error=3
    y_meas << 1.0;
    for (int i = 0; i < 100; ++i)
        obs.update(y_meas, y_pred);
    EXPECT_NEAR(obs.estimate()[0], 1.0, 0.01);

    y_meas << 3.0;
    for (int i = 0; i < 100; ++i)
        obs.update(y_meas, y_pred);
    EXPECT_NEAR(obs.estimate()[0], 3.0, 0.01);
}

// ============================================================================
// Kalman filter
// ============================================================================

TEST(DisturbanceObserver, KalmanFilter_StepDisturbance)
{
    DisturbanceObserver obs(1, DisturbanceObserver::Method::KALMAN_FILTER);
    obs.setKalmanTuning(
        Eigen::MatrixXd::Identity(1, 1) * 0.01,
        Eigen::MatrixXd::Identity(1, 1) * 1.0);

    Eigen::VectorXd y_meas(1), y_pred(1);
    y_meas << 5.0;
    y_pred << 3.0;

    for (int i = 0; i < 200; ++i)
        obs.update(y_meas, y_pred);

    EXPECT_NEAR(obs.estimate()[0], 2.0, 0.05);
}

TEST(DisturbanceObserver, KalmanFilter_MIMO)
{
    DisturbanceObserver obs(2, DisturbanceObserver::Method::KALMAN_FILTER);

    Eigen::VectorXd y_meas(2), y_pred(2);
    y_meas << 5.0, 10.0;
    y_pred << 3.0, 8.0;

    for (int i = 0; i < 300; ++i)
        obs.update(y_meas, y_pred);

    EXPECT_NEAR(obs.estimate()[0], 2.0, 0.1);
    EXPECT_NEAR(obs.estimate()[1], 2.0, 0.1);
}

// ============================================================================
// Reset
// ============================================================================

TEST(DisturbanceObserver, ResetClearsEstimate)
{
    DisturbanceObserver obs(2);

    Eigen::VectorXd y_meas(2), y_pred(2);
    y_meas << 5.0, 5.0;
    y_pred << 0.0, 0.0;

    for (int i = 0; i < 10; ++i)
        obs.update(y_meas, y_pred);
    EXPECT_GT(obs.estimate().norm(), 0.0);

    obs.reset();
    EXPECT_DOUBLE_EQ(obs.estimate().norm(), 0.0);
}

// ============================================================================
// Filter gain validation
// ============================================================================

TEST(DisturbanceObserver, FilterGainValidation)
{
    DisturbanceObserver obs(1);
    EXPECT_THROW(obs.setFilterGain(-0.1), std::invalid_argument);
    EXPECT_THROW(obs.setFilterGain(1.0), std::invalid_argument);
    EXPECT_NO_THROW(obs.setFilterGain(0.0));
    EXPECT_NO_THROW(obs.setFilterGain(0.99));
}

// ============================================================================
// Input validation
// ============================================================================

TEST(DisturbanceObserver, UpdateRejectsWrongSize)
{
    DisturbanceObserver obs(2);
    Eigen::VectorXd wrong_size(3);
    EXPECT_THROW(obs.update(wrong_size, Eigen::VectorXd::Zero(2)), std::invalid_argument);
    EXPECT_THROW(obs.update(Eigen::VectorXd::Zero(2), wrong_size), std::invalid_argument);
}
