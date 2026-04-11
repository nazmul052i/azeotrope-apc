#include <gtest/gtest.h>
#include "azeoapc/dynamic_matrix.h"
#include <cmath>

using namespace azeoapc;

// ============================================================================
// SISO Dynamic Matrix
// ============================================================================

TEST(DynamicMatrix, SISO_Dimensions)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    int P = 10, M = 3;
    DynamicMatrix dm(model, P, M);

    EXPECT_EQ(dm.predictionHorizon(), P);
    EXPECT_EQ(dm.controlHorizon(), M);
    EXPECT_EQ(dm.ny(), 1);
    EXPECT_EQ(dm.nu(), 1);

    auto& A = dm.matrix();
    EXPECT_EQ(A.rows(), P);    // P*ny = 10*1
    EXPECT_EQ(A.cols(), M);    // M*nu = 3*1
}

TEST(DynamicMatrix, SISO_ToeplitzStructure)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    int P = 5, M = 3;
    DynamicMatrix dm(model, P, M);

    auto& A = dm.matrix();

    // Lower-triangular Toeplitz: A(j,i) = S[j-i+1] for j>=i, 0 otherwise
    // Using S_stored[k] = S[k+1], so A(j,i) = S_stored[j-i]

    // First column: S_stored[0], S_stored[1], ..., S_stored[P-1]
    for (int j = 0; j < P; ++j)
        EXPECT_NEAR(A(j, 0), model.coefficient(0, j, 0), 1e-12);

    // Upper triangle: zero
    EXPECT_DOUBLE_EQ(A(0, 1), 0.0);
    EXPECT_DOUBLE_EQ(A(0, 2), 0.0);
    EXPECT_DOUBLE_EQ(A(1, 2), 0.0);

    // Toeplitz: A(j,i) = A(j-1, i-1) for j>0, i>0
    for (int j = 1; j < P; ++j)
        for (int i = 1; i <= std::min(j, M - 1); ++i)
            EXPECT_NEAR(A(j, i), A(j - 1, i - 1), 1e-12)
                << "Toeplitz mismatch at (" << j << "," << i << ")";
}

TEST(DynamicMatrix, SISO_UpperTriangleZero)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    DynamicMatrix dm(model, 8, 4);
    auto& A = dm.matrix();

    for (int j = 0; j < 8; ++j)
        for (int i = j + 1; i < 4; ++i)
            EXPECT_DOUBLE_EQ(A(j, i), 0.0);
}

// ============================================================================
// MIMO Dynamic Matrix
// ============================================================================

TEST(DynamicMatrix, MIMO_Dimensions)
{
    Eigen::MatrixXd K(2, 3), tau(2, 3), L(2, 3);
    K.setOnes();
    tau.setConstant(10.0);
    L.setZero();

    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 30);
    int P = 8, M = 3;
    DynamicMatrix dm(model, P, M);

    EXPECT_EQ(dm.matrix().rows(), P * 2);    // 16
    EXPECT_EQ(dm.matrix().cols(), M * 3);    // 9
}

TEST(DynamicMatrix, MIMO_BlockToeplitz)
{
    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K << 1.0, 0.5, 0.3, 2.0;
    tau << 10.0, 5.0, 8.0, 15.0;
    L.setZero();

    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 30);
    int P = 6, M = 3;
    DynamicMatrix dm(model, P, M);
    auto& A = dm.matrix();

    int ny = 2, nu = 2;

    // Block (j,0) should equal S_stored[j] coefficient matrix
    for (int j = 0; j < P; ++j) {
        auto S_j = model.coefficientMatrix(j);
        for (int cv = 0; cv < ny; ++cv)
            for (int mv = 0; mv < nu; ++mv)
                EXPECT_NEAR(A(j * ny + cv, 0 * nu + mv), S_j(cv, mv), 1e-12);
    }

    // Block Toeplitz: block(j,i) = block(j-1,i-1)
    for (int j = 1; j < P; ++j) {
        for (int i = 1; i <= std::min(j, M - 1); ++i) {
            for (int cv = 0; cv < ny; ++cv)
                for (int mv = 0; mv < nu; ++mv)
                    EXPECT_NEAR(A(j * ny + cv, i * nu + mv),
                                A((j - 1) * ny + cv, (i - 1) * nu + mv), 1e-12);
        }
    }
}

// ============================================================================
// Sparse Matrix
// ============================================================================

TEST(DynamicMatrix, SparseMatchesDense)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 5.0, 1.0, 30);
    DynamicMatrix dm(model, 10, 3);

    Eigen::MatrixXd from_sparse = dm.sparse();
    EXPECT_EQ(from_sparse.rows(), dm.matrix().rows());
    EXPECT_EQ(from_sparse.cols(), dm.matrix().cols());

    double max_diff = (dm.matrix() - from_sparse).cwiseAbs().maxCoeff();
    EXPECT_LT(max_diff, 1e-15);
}

// ============================================================================
// Cumulative Matrix
// ============================================================================

TEST(DynamicMatrix, CumulativeMatrix_Structure)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    int M = 4;
    DynamicMatrix dm(model, 10, M);

    auto& C = dm.cumulativeMatrix();
    EXPECT_EQ(C.rows(), M);
    EXPECT_EQ(C.cols(), M);

    // Lower triangular with 1s
    for (int j = 0; j < M; ++j) {
        for (int i = 0; i < M; ++i) {
            if (i <= j)
                EXPECT_DOUBLE_EQ(C(j, i), 1.0);
            else
                EXPECT_DOUBLE_EQ(C(j, i), 0.0);
        }
    }
}

TEST(DynamicMatrix, CumulativeMatrix_MIMO)
{
    Eigen::MatrixXd K(2, 2), tau(2, 2), L(2, 2);
    K.setOnes();
    tau.setConstant(10.0);
    L.setZero();

    auto model = StepResponseModel::fromFOPTDMatrix(K, tau, L, 1.0, 30);
    int M = 3, nu = 2;
    DynamicMatrix dm(model, 10, M);

    auto& C = dm.cumulativeMatrix();
    EXPECT_EQ(C.rows(), M * nu);
    EXPECT_EQ(C.cols(), M * nu);

    // Block (1,0) should be I_2
    Eigen::MatrixXd I2 = Eigen::MatrixXd::Identity(nu, nu);
    EXPECT_TRUE(C.block(nu, 0, nu, nu).isApprox(I2, 1e-12));

    // Block (2,0) should be I_2
    EXPECT_TRUE(C.block(2 * nu, 0, nu, nu).isApprox(I2, 1e-12));

    // Block (0,1) should be zero
    EXPECT_TRUE(C.block(0, nu, nu, nu).isZero(1e-12));
}

// ============================================================================
// Rebuild
// ============================================================================

TEST(DynamicMatrix, Rebuild)
{
    auto model1 = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    auto model2 = StepResponseModel::fromFOPTD(2.0, 10.0, 0.0, 1.0, 30);

    DynamicMatrix dm(model1, 5, 3);
    double val_before = dm.matrix()(0, 0);

    dm.rebuild(model2);
    double val_after = dm.matrix()(0, 0);

    // New gain is 2x, so step response should be 2x
    EXPECT_NEAR(val_after, 2.0 * val_before, 1e-10);
}

// ============================================================================
// Validation
// ============================================================================

TEST(DynamicMatrix, RejectsInvalidArgs)
{
    auto model = StepResponseModel::fromFOPTD(1.0, 10.0, 0.0, 1.0, 30);
    EXPECT_THROW(DynamicMatrix(model, 0, 3), std::invalid_argument);
    EXPECT_THROW(DynamicMatrix(model, 10, 0), std::invalid_argument);
    EXPECT_THROW(DynamicMatrix(model, 3, 10), std::invalid_argument);  // M > P
}

// ============================================================================
// Prediction: A_dyn * du should match StepResponseModel::predictForced
// ============================================================================

TEST(DynamicMatrix, PredictionMatchesStepResponse)
{
    auto model = StepResponseModel::fromFOPTD(1.5, 8.0, 2.0, 1.0, 40);
    int P = 15, M = 5;
    DynamicMatrix dm(model, P, M);

    // Random future moves
    Eigen::VectorXd du = Eigen::VectorXd::Random(M);
    Eigen::VectorXd y_matrix = dm.matrix() * du;
    Eigen::VectorXd y_model  = model.predictForced(du, P, M);

    double max_diff = (y_matrix - y_model).cwiseAbs().maxCoeff();
    EXPECT_LT(max_diff, 1e-10);
}
