# Process Identification Theory for Model Predictive Control

**A Mathematical Reference for the Azeotrope APC Identification Suite**

---

## Table of Contents

1. [FIR Identification](#1-fir-identification)
2. [Subspace Identification](#2-subspace-identification)
3. [Constrained Identification](#3-constrained-identification)
4. [Closed-Loop Identification](#4-closed-loop-identification)
5. [CV Grouping](#5-cv-grouping)
6. [Data Conditioning](#6-data-conditioning)
7. [Model Quality Assessment](#7-model-quality-assessment)
8. [Curve Operations](#8-curve-operations)

---

## Notation and Conventions

Throughout this document, the following notation is used consistently:

| Symbol | Meaning |
|--------|---------|
| $$n_y$$ | Number of controlled variables (CVs / outputs) |
| $$n_u$$ | Number of manipulated variables (MVs / inputs) |
| $$n_d$$ | Number of disturbance variables (DVs) |
| $$N$$ | Number of data samples |
| $$n$$ | Number of FIR coefficients (model length) |
| $$n_x$$ | State-space model order |
| $$T_s$$ or $$\Delta t$$ | Sample period (seconds) |
| $$u(k) \in \mathbb{R}^{n_u}$$ | Input (MV) vector at sample $$k$$ |
| $$y(k) \in \mathbb{R}^{n_y}$$ | Output (CV) vector at sample $$k$$ |
| $$\Delta u(k) = u(k) - u(k-1)$$ | Input move (first difference) |
| $$g_k \in \mathbb{R}^{n_y \times n_u}$$ | FIR (Markov parameter) coefficient at lag $$k$$ |
| $$S_k \in \mathbb{R}^{n_y \times n_u}$$ | Step response coefficient at step $$k$$ |
| $$K \in \mathbb{R}^{n_y \times n_u}$$ | Steady-state gain matrix |
| $$\Phi$$ | Toeplitz regression matrix |
| $$\theta$$ | Parameter vector or matrix |
| $$I$$ | Identity matrix of appropriate dimension |
| $$\sigma^2$$ | Noise variance |
| $$\otimes$$ | Kronecker product |
| $$\text{vec}(\cdot)$$ | Column-stacking vectorization operator |

Matrices are denoted by uppercase bold or uppercase Roman letters. Vectors are lowercase.
The discrete-time index is $$k$$; continuous time is $$t$$.

---

## 1. FIR Identification

### 1.1 The Finite Impulse Response Model

The Finite Impulse Response (FIR) model is the workhorse of industrial Model
Predictive Control. It relates the output $$y(k)$$ to a finite history of
input values $$u(k), u(k-1), \ldots, u(k-n+1)$$ through a convolution sum:

$$
y(k) = \sum_{i=0}^{n-1} g_i \, u(k - i) + e(k)
$$

where:

- $$g_i \in \mathbb{R}^{n_y \times n_u}$$ is the $$i$$-th **Markov parameter**
  (impulse response coefficient),
- $$n$$ is the **model length** (number of coefficients), and
- $$e(k)$$ is a zero-mean disturbance (measurement noise plus unmodeled dynamics).

For a MIMO system with $$n_y$$ outputs and $$n_u$$ inputs, each $$g_i$$ is a
matrix. The $$(p, q)$$ element of $$g_i$$, denoted $$g_i^{(p,q)}$$, represents
the impulse response from input $$q$$ to output $$p$$ at lag $$i$$.

**Physical interpretation.** If a unit impulse is applied to input $$q$$ at
time $$k = 0$$ (that is, $$u_q(0) = 1$$ and $$u_q(k) = 0$$ for $$k \neq 0$$,
with all other inputs held at zero), then the response of output $$p$$ at
time $$k = i$$ is exactly $$g_i^{(p,q)}$$.

**Stability assumption.** For a stable, open-loop process, the impulse response
decays to zero:

$$
\lim_{i \to \infty} g_i = 0
$$

The model length $$n$$ must be chosen large enough that $$g_i \approx 0$$
for $$i \geq n$$. In practice, $$n$$ is set to 1.5 to 2 times the estimated
settling time of the slowest channel, measured in sample periods.

**FIR vs. transfer function.** The FIR model is a non-parametric model: it
does not assume any particular structure (order, dead time, time constants)
for the process. This makes it robust to model structure uncertainty but
requires many parameters. A first-order-plus-dead-time (FOPTD) process
$$G(s) = K e^{-\theta s}/(1 + \tau s)$$ with $$\tau / T_s = 20$$ requires
roughly $$n = 60$$ coefficients for adequate representation, whereas the
parametric model has only three parameters $$(K, \tau, \theta)$$.


### 1.2 Relationship to Step Response

The step response is the cumulative sum of the impulse response. If a unit step
is applied to input $$q$$ at $$k = 0$$ (i.e., $$u_q(k) = 1$$ for
$$k \geq 0$$), the output of channel $$p$$ at time $$k$$ is:

$$
S_k^{(p,q)} = \sum_{i=0}^{k} g_i^{(p,q)}
$$

or in matrix form:

$$
S_k = \sum_{i=0}^{k} g_i
$$

The steady-state gain matrix is the limit of the step response:

$$
K = S_\infty = \sum_{i=0}^{\infty} g_i \approx \sum_{i=0}^{n-1} g_i = S_{n-1}
$$

In DMC-style controllers, the step response coefficients $$S_0, S_1, \ldots, S_{n-1}$$
are the primary model representation. The dynamic matrix (Toeplitz matrix used
in the QP) is built from these coefficients.

**Conversion formulas:**

$$
\text{FIR} \to \text{Step:} \quad S_k = \sum_{i=0}^{k} g_i
$$

$$
\text{Step} \to \text{FIR:} \quad g_k = S_k - S_{k-1}, \quad g_0 = S_0
$$


### 1.3 Toeplitz Regression Matrix Construction

The FIR convolution can be written as a linear regression problem. Define the
output vector and regressor matrix as follows.

For a single output $$p$$, stack the output measurements from $$k = n-1$$ to
$$k = N-1$$ into a vector:

$$
Y_p = \begin{bmatrix} y_p(n-1) \\ y_p(n) \\ \vdots \\ y_p(N-1) \end{bmatrix}
\in \mathbb{R}^{N - n + 1}
$$

Construct the block-Toeplitz regression matrix $$\Phi$$ where row $$t$$
(corresponding to time $$k = t + n - 1$$) contains the lagged inputs:

$$
\Phi = \begin{bmatrix}
u^T(n-1) & u^T(n-2) & \cdots & u^T(0) \\
u^T(n) & u^T(n-1) & \cdots & u^T(1) \\
\vdots & \vdots & \ddots & \vdots \\
u^T(N-1) & u^T(N-2) & \cdots & u^T(N-n)
\end{bmatrix}
\in \mathbb{R}^{(N - n + 1) \times (n \cdot n_u)}
$$

Each row of $$\Phi$$ is a flattened vector of $$n$$ consecutive input vectors
in reverse chronological order. For a SISO system ($$n_u = 1$$), this reduces
to a standard Toeplitz matrix.

The parameter matrix $$\theta$$ stacks the FIR coefficients:

$$
\theta = \begin{bmatrix}
g_0^T \\ g_1^T \\ \vdots \\ g_{n-1}^T
\end{bmatrix}
\in \mathbb{R}^{(n \cdot n_u) \times n_y}
$$

The MIMO regression model is then:

$$
Y = \Phi \, \theta + E
$$

where $$Y \in \mathbb{R}^{(N-n+1) \times n_y}$$ stacks all output channels
column-wise, and $$E$$ is the residual matrix.

**Construction algorithm.** For each lag $$k = 0, 1, \ldots, n-1$$, the
block column of $$\Phi$$ corresponding to lag $$k$$ is:

$$
\Phi[:, k \cdot n_u : (k+1) \cdot n_u] = u[n-1-k : N-k, :]
$$

This is the shifted input matrix, where the shift increases with the lag index.


### 1.4 Direct Least Squares (DLS)

The Direct Least Squares (DLS) estimator minimizes the sum of squared residuals:

$$
\hat{\theta}_{\text{DLS}} = \arg\min_{\theta} \| Y - \Phi \, \theta \|_F^2
$$

where $$\| \cdot \|_F$$ denotes the Frobenius norm. The normal equations give:

$$
\Phi^T \Phi \, \hat{\theta} = \Phi^T Y
$$

The solution is:

$$
\hat{\theta}_{\text{DLS}} = (\Phi^T \Phi)^{-1} \Phi^T Y
$$

In practice, this is solved via the SVD (singular value decomposition) of $$\Phi$$
rather than by explicit inversion, for numerical stability:

$$
\Phi = U \Sigma V^T
$$

$$
\hat{\theta}_{\text{DLS}} = V \Sigma^{-1} U^T Y
$$

where singular values below a tolerance are truncated.

**Conditions for well-posedness.** The matrix $$\Phi^T \Phi$$ must be
non-singular, which requires:

1. The number of data samples exceeds the number of parameters:
   $$N - n + 1 > n \cdot n_u$$
2. The input signals are **persistently exciting** of order $$n$$ -- informally,
   the input must contain sufficient frequency content to excite all $$n$$
   modes of the FIR model. For step-test data, this means the MVs must be
   moved enough times with sufficient amplitude variation.

**Condition number.** The condition number $$\kappa(\Phi) = \sigma_{\max} / \sigma_{\min}$$
of the regression matrix quantifies numerical sensitivity. Guidelines:

| Condition Number | Interpretation |
|---|---|
| $$< 10^3$$ | Well-conditioned, reliable estimates |
| $$10^3 - 10^6$$ | Moderate conditioning, check estimates |
| $$> 10^6$$ | Ill-conditioned, use Ridge or check data |

**Bias-variance trade-off.** DLS is the minimum-variance unbiased estimator
(MVUE) when the noise $$e(k)$$ is i.i.d. with $$\mathbb{E}[e] = 0$$ and
$$\text{Var}(e) = \sigma^2 I$$. However, it is biased when:

- The input $$u$$ is correlated with the noise $$e$$ through a feedback
  controller (closed-loop data), or
- The model length $$n$$ is shorter than the true settling time (truncation bias).


### 1.5 Correlation Method (COR)

The correlation method provides tolerance to closed-loop feedback by replacing
the regression with correlation equations. Instead of solving the overdetermined
system $$Y = \Phi \theta + E$$ directly, we premultiply both sides by
$$\Phi^T / N_{\text{eff}}$$ and use the sample auto-correlation and
cross-correlation matrices.

Define the input auto-correlation matrix:

$$
R_{uu}(i, j) = \frac{1}{N_{\text{eff}}} \sum_{t} u(t - i) \, u^T(t - j)
$$

where $$i, j$$ are lag indices running from $$0$$ to $$n - 1$$, and $$N_{\text{eff}}$$
is the number of valid overlap samples for each lag pair:
$$N_{\text{eff}} = N - \max(i, j)$$.

The full auto-correlation matrix is block-structured:

$$
R_{uu} = \begin{bmatrix}
R_{uu}(0,0) & R_{uu}(0,1) & \cdots & R_{uu}(0,n-1) \\
R_{uu}(1,0) & R_{uu}(1,1) & \cdots & R_{uu}(1,n-1) \\
\vdots & & \ddots & \vdots \\
R_{uu}(n-1,0) & R_{uu}(n-1,1) & \cdots & R_{uu}(n-1,n-1)
\end{bmatrix}
\in \mathbb{R}^{(n \cdot n_u) \times (n \cdot n_u)}
$$

Each block $$R_{uu}(i, j) \in \mathbb{R}^{n_u \times n_u}$$ is the
sample cross-covariance between $$u(t-i)$$ and $$u(t-j)$$.

Similarly, the input-output cross-correlation matrix is:

$$
R_{uy}(i) = \frac{1}{N_{\text{eff}}} \sum_{t} u(t - i) \, y^T(t)
$$

$$
R_{uy} = \begin{bmatrix}
R_{uy}(0) \\ R_{uy}(1) \\ \vdots \\ R_{uy}(n-1)
\end{bmatrix}
\in \mathbb{R}^{(n \cdot n_u) \times n_y}
$$

The correlation estimator solves the Wiener-Hopf (Yule-Walker) equations:

$$
R_{uu} \, \hat{\theta}_{\text{COR}} = R_{uy}
$$

$$
\hat{\theta}_{\text{COR}} = R_{uu}^{-1} \, R_{uy}
$$

**Why this helps with closed-loop data.** In the DLS formulation, the regression
$$\Phi^T \Phi$$ is contaminated by feedback-induced correlation between $$u$$
and $$e$$. The correlation method reduces (but does not eliminate) this bias
because the auto-correlation and cross-correlation estimates are more robust
to the specific temporal structure of the feedback-induced correlation.

Specifically, if the controller responds to the noise component of $$y$$
with a delay of at least one sample, then the low-lag correlation estimates
$$R_{uu}(i,j)$$ for small $$|i - j|$$ are less affected than the
corresponding entries in $$\Phi^T \Phi$$.

**Regularization.** If $$R_{uu}$$ is ill-conditioned (condition number exceeding
$$10^8$$), a small ridge is added:

$$
R_{uu} \leftarrow R_{uu} + \epsilon \cdot \frac{\text{tr}(R_{uu})}{n \cdot n_u} \cdot I
$$

with $$\epsilon = 10^{-6}$$ as the default regularization factor.


### 1.6 Ridge Regularization (Tikhonov)

When the regression matrix is ill-conditioned (collinear inputs, short test
window, or high model order), the DLS estimator produces large-variance
estimates. Ridge regression (L2 regularization, Tikhonov regularization)
addresses this by adding a penalty on the parameter norm:

$$
\hat{\theta}_{\text{Ridge}} = \arg\min_{\theta}
\left\{ \| Y - \Phi \theta \|_F^2 + \alpha \| \theta \|_F^2 \right\}
$$

where $$\alpha > 0$$ is the regularization parameter. The closed-form solution is:

$$
\hat{\theta}_{\text{Ridge}} = (\Phi^T \Phi + \alpha I)^{-1} \Phi^T Y
$$

**Effect on the estimate.** In terms of the SVD $$\Phi = U \Sigma V^T$$,
the Ridge estimator is:

$$
\hat{\theta}_{\text{Ridge}} = \sum_{i=1}^{r} \frac{\sigma_i}{\sigma_i^2 + \alpha} \, v_i \, u_i^T Y
$$

where $$\sigma_i$$ are the singular values, and $$u_i, v_i$$ are the
corresponding left and right singular vectors. Compared to the DLS solution
(which uses $$1 / \sigma_i$$), the Ridge solution shrinks the contribution
of small singular values toward zero. This:

1. **Reduces variance** by suppressing the amplification of noise through
   poorly conditioned directions, at the cost of
2. **Introducing bias** -- the estimate is shrunk toward zero.

**Choosing $$\alpha$$.** The regularization parameter controls the
bias-variance trade-off:

| $$\alpha$$ | Effect |
|---|---|
| Too small ($$\ll \sigma_{\min}^2$$) | No effect, equivalent to DLS |
| Optimal | Minimizes mean squared error (bias$$^2$$ + variance) |
| Too large ($$\gg \sigma_{\max}^2$$) | Over-smooths, significant bias |

Practical approaches for choosing $$\alpha$$:

- **Cross-validation**: Hold out a portion of data, choose $$\alpha$$ that
  minimizes prediction error on the held-out set.
- **L-curve**: Plot $$\| \theta \|$$ vs. $$\| Y - \Phi \theta \|$$ and
  select the "corner" of the L-shaped curve.
- **Rule of thumb**: Start with $$\alpha = 1$$ and adjust based on the
  condition number improvement.

**Effective condition number.** The regularized system has effective condition
number:

$$
\kappa_{\text{eff}} = \frac{\sigma_{\max}^2 + \alpha}{\sigma_{\min}^2 + \alpha}
$$

which is always smaller than $$\kappa^2 = \sigma_{\max}^2 / \sigma_{\min}^2$$.


### 1.7 Confidence Intervals

Under the assumption that the residuals $$e(k)$$ are independent and
identically distributed (i.i.d.) with zero mean and variance $$\sigma^2$$,
the covariance of the DLS estimator is:

$$
\text{Cov}(\hat{\theta}_j) = \sigma_j^2 (\Phi^T \Phi)^{-1}
$$

where $$\hat{\theta}_j$$ is the $$j$$-th column of $$\hat{\theta}$$
(corresponding to the $$j$$-th output), and $$\sigma_j^2$$ is the residual
variance for output $$j$$:

$$
\hat{\sigma}_j^2 = \frac{1}{N - n + 1 - n \cdot n_u} \sum_{t} e_j^2(t)
$$

The standard error of the parameter $$\hat{\theta}_{ij}$$ (row $$i$$,
column $$j$$ of $$\hat{\theta}$$) is:

$$
\text{SE}(\hat{\theta}_{ij}) = \hat{\sigma}_j \sqrt{[(\Phi^T \Phi)^{-1}]_{ii}}
$$

A $$(1 - \alpha)$$ confidence interval for the FIR coefficient $$g_k^{(p,q)}$$
is:

$$
g_k^{(p,q)} \pm z_{\alpha/2} \cdot \text{SE}(\hat{\theta}_{ij})
$$

where $$z_{\alpha/2}$$ is the standard normal quantile (e.g., $$z_{0.025} = 1.96$$
for a 95% interval), and the mapping between $$(k, p, q)$$ and $$(i, j)$$ follows
the parameter matrix layout: $$i = k \cdot n_u + q$$, $$j = p$$.

**Interpretation for process engineers.** Wide confidence bands indicate that
the identified coefficient is uncertain -- typically due to:

- Insufficient excitation of the corresponding MV
- High process noise relative to the input signal
- Collinear inputs making it difficult to separate individual MV effects

Coefficients with confidence bands that include zero may indicate a
non-existent or negligibly small dynamic relationship.


### 1.8 Step Response from FIR

Given the identified FIR coefficients $$\hat{g}_0, \hat{g}_1, \ldots, \hat{g}_{n-1}$$,
the step response is computed by cumulative summation:

$$
\hat{S}_k = \sum_{i=0}^{k} \hat{g}_i, \quad k = 0, 1, \ldots, n-1
$$

The steady-state gain matrix is:

$$
\hat{K} = \hat{S}_{n-1} = \sum_{i=0}^{n-1} \hat{g}_i
$$

**Settling index.** For each channel $$(p, q)$$, the settling index is the
last time index where the step response deviates from its final value by
more than a tolerance:

$$
k_{\text{settle}}^{(p,q)} = \max \left\{ k : \left| \hat{S}_k^{(p,q)} - \hat{K}^{(p,q)} \right| > \epsilon \left| \hat{K}^{(p,q)} \right| \right\}
$$

where $$\epsilon$$ is a settling tolerance (typically 0.01 or 1%). If
$$k_{\text{settle}}$$ is close to $$n - 1$$, the model length may be
too short and should be increased.


### 1.9 Smoothing Methods

Raw FIR coefficients identified from noisy data exhibit random fluctuations,
particularly in the tail (high-lag) region where the signal-to-noise ratio
is lowest. Smoothing improves the model quality for controller use.

The Azeotrope APC suite implements four smoothing methods, which can be
applied individually or in a pipeline (exponential, then Savitzky-Golay,
then asymptotic).


#### 1.9.1 Exponential Tail Decay

**Motivation.** A stable process has an impulse response that decays
exponentially:

$$
g_k \approx c \cdot e^{-k / \tau_d}
$$

for large $$k$$, where $$\tau_d$$ is the decay time constant. Noise in the
tail region causes the identified coefficients to deviate from this smooth
decay. The exponential smoothing enforces the expected tail behavior.

**Algorithm.** Let $$k_s = \lfloor f_s \cdot n \rfloor$$ be the start of the
tail region, where $$f_s$$ is the smoothing start fraction (default 0.6).
For $$k \geq k_s$$:

1. **Estimate $$\tau_d$$** (if not user-specified): fit a linear model to
   $$\log |g_k|$$ vs. $$k$$ in the tail region using least squares:

   $$
   \log |g_k| \approx -k / \tau_d + c
   $$

   The slope gives $$\tau_d = -1 / \text{slope}$$. If the slope is
   non-negative (non-decaying tail), use $$\tau_d = (n - k_s) / 3$$ as a
   fallback.

2. **Apply exponential window**: for each offset $$j = 0, 1, \ldots, n - k_s - 1$$
   in the tail:

   $$
   w_j = (1 - j / n_{\text{tail}}) + (j / n_{\text{tail}}) \cdot e^{-j / \tau_d}
   $$

   $$
   g_{k_s + j}^{\text{smooth}} = g_{k_s + j} \cdot w_j
   $$

   The weight $$w_j$$ is a linear blend from 1 (preserve original) at the
   start of the tail to an exponential decay at the end, ensuring a smooth
   transition.


#### 1.9.2 Savitzky-Golay Smoothing

The Savitzky-Golay filter fits a local polynomial of degree $$p$$ to a
sliding window of $$w$$ points and evaluates it at the center point. This
is equivalent to convolution with a set of pre-computed filter coefficients.

**Properties.** The Savitzky-Golay filter:

- Preserves the shape of peaks and transitions (unlike moving average)
- Preserves polynomial trends up to degree $$p$$
- Has zero phase shift (symmetric convolution)
- Effectively acts as a low-pass filter with a cutoff determined by $$w$$

**Parameters:**

| Parameter | Default | Meaning |
|---|---|---|
| Window length $$w$$ | 11 | Must be odd; larger = more smoothing |
| Polynomial order $$p$$ | 3 | Must be $$< w$$; higher = less smoothing |

**Application.** Applied independently to each channel's FIR sequence
$$[g_0^{(p,q)}, g_1^{(p,q)}, \ldots, g_{n-1}^{(p,q)}]$$.


#### 1.9.3 Asymptotic Projection

For a stable process, the impulse response must approach zero as $$k \to \infty$$.
Asymptotic projection enforces this by blending the tail coefficients toward
zero using a cosine window.

Let $$k_a = \lfloor f_a \cdot n \rfloor$$ be the asymptotic start index
(default $$f_a = 0.75$$). For $$k \geq k_a$$:

$$
g_k^{\text{smooth}} = g_k \cdot \frac{1}{2}\left(1 + \cos\left(\frac{\pi (k - k_a)}{n - k_a}\right)\right)
$$

The cosine window transitions smoothly from 1 at $$k = k_a$$ to 0 at
$$k = n - 1$$. This ensures:

- The last coefficient is exactly zero
- The transition from identified to projected values is smooth (no discontinuities)
- The gain is preserved (the area under the impulse response changes only
  in the tail, where it should be small)


#### 1.9.4 Pipeline Smoothing

The default smoothing pipeline applies all three methods in sequence:

$$
g^{\text{raw}} \xrightarrow{\text{exponential}} g^{(1)} \xrightarrow{\text{Savitzky-Golay}} g^{(2)} \xrightarrow{\text{asymptotic}} g^{\text{final}}
$$

This ordering is deliberate:

1. **Exponential** first: stabilizes the tail magnitude
2. **Savitzky-Golay** second: smooths local fluctuations while preserving shape
3. **Asymptotic** last: ensures the final coefficients decay cleanly to zero

The step response is then computed from the smoothed FIR:

$$
S_k^{\text{final}} = \sum_{i=0}^{k} g_i^{\text{final}}
$$


### 1.10 Ljung-Box Residual Whiteness Test

After identification, the residuals $$\hat{e}(k) = y(k) - \hat{y}(k)$$
should be white noise (uncorrelated in time) if the model has captured all
systematic dynamics. The Ljung-Box test checks this formally.

**Test statistic.** The Ljung-Box Q statistic is:

$$
Q = N(N + 2) \sum_{k=1}^{m} \frac{\hat{\rho}_k^2}{N - k}
$$

where:

- $$N$$ is the number of residual samples,
- $$m$$ is the number of lags tested (default: 20),
- $$\hat{\rho}_k$$ is the sample autocorrelation of residuals at lag $$k$$:

$$
\hat{\rho}_k = \frac{\sum_{t=k+1}^{N} \hat{e}(t) \hat{e}(t-k)}
{N \cdot \hat{\sigma}_e^2}
$$

where $$\hat{\sigma}_e^2 = \frac{1}{N} \sum_{t=1}^{N} \hat{e}(t)^2$$ is
the sample variance of the residuals.

**Distribution.** Under the null hypothesis that the residuals are white
noise, $$Q \sim \chi^2(m)$$ (chi-squared with $$m$$ degrees of freedom).

**Decision rule.** At significance level $$\alpha = 0.05$$:

- If $$p\text{-value} = P(\chi^2_m > Q) > 0.05$$: **fail to reject** $$H_0$$ --
  residuals are consistent with white noise. The model has adequate dynamic
  structure.
- If $$p\text{-value} \leq 0.05$$: **reject** $$H_0$$ -- residuals contain
  significant autocorrelation. Possible causes:
  - Model length $$n$$ too short (truncated dynamics)
  - Missing disturbance variable
  - Nonlinear effects not captured by the linear FIR model
  - Data quality issues (e.g., intermittent sensor faults)

**Interpretation for process engineers.** A "white" residual (passing the
Ljung-Box test) does not guarantee a good model -- it means the model has
extracted all the linear dynamics it can. A "correlated" residual is a
stronger signal: it indicates systematic information left in the residuals
that a better model (longer, different structure, or nonlinear) might capture.


### 1.11 Preprocessing

Before identification, the data is preprocessed to improve the conditioning
of the regression problem.

**Detrending.** Removal of linear trends from each signal using least-squares
line subtraction:

$$
u_j^{\text{detrended}}(k) = u_j(k) - (a_j k + b_j)
$$

where $$(a_j, b_j)$$ are the slope and intercept of the best-fit line.
Detrending removes slow drifts that are not part of the process dynamics
(e.g., ambient temperature changes, catalyst deactivation).

**Mean removal.** Subtracting the sample mean centers the data around zero,
which is a prerequisite for the correlation method and improves numerical
conditioning:

$$
u_j^{\text{centered}}(k) = u_j(k) - \bar{u}_j
$$

**Prewhitening.** First-differencing to suppress low-frequency content
(drift, integrating behavior):

$$
u_j^{\text{pw}}(k) = u_j(k) - u_j(k-1) = \Delta u_j(k)
$$

Prewhitening is useful when the input signals contain slow ramps or drifts
that would otherwise dominate the regression. However, it changes the model
interpretation: the identified FIR relates input *changes* to output
*changes*, and post-processing is needed to recover the original model.


---

## 2. Subspace Identification

### 2.1 State-Space Model

Subspace identification recovers a discrete-time state-space model directly
from input-output data, without requiring a priori specification of the
model order or structure.

The model is:

$$
x(k+1) = A x(k) + B u(k) + w(k)
$$

$$
y(k) = C x(k) + D u(k) + v(k)
$$

where:

- $$x(k) \in \mathbb{R}^{n_x}$$ is the state vector,
- $$A \in \mathbb{R}^{n_x \times n_x}$$ is the state transition matrix,
- $$B \in \mathbb{R}^{n_x \times n_u}$$ is the input matrix,
- $$C \in \mathbb{R}^{n_y \times n_x}$$ is the output matrix,
- $$D \in \mathbb{R}^{n_y \times n_u}$$ is the direct feedthrough matrix,
- $$w(k)$$ is process noise, $$v(k)$$ is measurement noise.

The **innovation form** includes a Kalman gain $$K_f$$:

$$
x(k+1) = A x(k) + B u(k) + K_f e(k)
$$

$$
y(k) = C x(k) + D u(k) + e(k)
$$

where $$e(k) = y(k) - C x(k) - D u(k)$$ is the innovation (one-step prediction
error).

**Relationship to FIR.** The Markov parameters of the state-space model are:

$$
g_0 = D, \quad g_k = C A^{k-1} B \quad \text{for } k \geq 1
$$

The steady-state gain is:

$$
K = C(I - A)^{-1} B + D
$$

provided $$I - A$$ is non-singular (i.e., the system is stable and has no
eigenvalue at exactly 1).


### 2.2 Block-Hankel Matrices

The key data structure in subspace identification is the **block-Hankel matrix**.
Given a signal $$z(k) \in \mathbb{R}^{n_z}$$ for $$k = 0, 1, \ldots, N-1$$,
the block-Hankel matrix with $$f$$ block rows is:

$$
\mathcal{H}_f(z) = \begin{bmatrix}
z(0) & z(1) & z(2) & \cdots & z(N-f) \\
z(1) & z(2) & z(3) & \cdots & z(N-f+1) \\
\vdots & \vdots & \vdots & \ddots & \vdots \\
z(f-1) & z(f) & z(f+1) & \cdots & z(N-1)
\end{bmatrix}
\in \mathbb{R}^{(f \cdot n_z) \times (N - f + 1)}
$$

Each row block $$i$$ (for $$i = 0, \ldots, f-1$$) contains the signal
shifted by $$i$$ samples. The matrix has a constant-along-anti-diagonals
structure (Hankel property).

**Past/future partitioning.** The combined Hankel matrices for inputs
and outputs are split into "past" and "future" portions:

$$
\mathcal{H}_{f+p}(u) = \begin{bmatrix} U_p \\ U_f \end{bmatrix}, \quad
\mathcal{H}_{f+p}(y) = \begin{bmatrix} Y_p \\ Y_f \end{bmatrix}
$$

where:

- $$U_p \in \mathbb{R}^{(p \cdot n_u) \times N_c}$$ -- past inputs ($$p$$ = past horizon)
- $$U_f \in \mathbb{R}^{(f \cdot n_u) \times N_c}$$ -- future inputs ($$f$$ = future horizon)
- $$Y_p, Y_f$$ -- analogous for outputs
- $$N_c = N - (f + p) + 1$$ -- number of columns

The past data is also stacked into a combined past matrix:

$$
W_p = \begin{bmatrix} U_p \\ Y_p \end{bmatrix}
\in \mathbb{R}^{p(n_u + n_y) \times N_c}
$$


### 2.3 Projections

Two types of projections are used in subspace identification.

**Orthogonal projection.** The orthogonal projection of the rows of $$A$$
onto the row space of $$B$$:

$$
\Pi_B(A) = A B^T (B B^T)^{-1} B
$$

This projects $$A$$ onto the subspace spanned by the rows of $$B$$,
giving the component of $$A$$ that can be "explained" by $$B$$.

The **orthogonal complement** projection removes the component explained by $$B$$:

$$
\Pi_B^\perp(A) = A - \Pi_B(A) = A - A B^T (B B^T)^{-1} B
$$

**Oblique projection.** The oblique projection of $$A$$ along the row space
of $$B$$ onto the row space of $$C$$:

$$
A /_{B} C = A \begin{bmatrix} B \\ C \end{bmatrix}^{\dagger} \begin{bmatrix} 0 \\ C \end{bmatrix}
$$

where $$\dagger$$ denotes the Moore-Penrose pseudoinverse. This projects $$A$$
onto the subspace of $$C$$ while removing ("along") the subspace of $$B$$.

**Interpretation.** In subspace identification:

- $$A = Y_f$$ (future outputs -- what we want to predict)
- $$B = U_f$$ (future inputs -- known, must be removed)
- $$C = W_p$$ (past data -- what we condition on)

The oblique projection $$Y_f /_{U_f} W_p$$ gives the component of future
outputs that depends on past data, with the effect of future inputs removed.
This component contains the state information.


### 2.4 N4SID Algorithm

N4SID (Numerical Algorithms for Subspace State Space System Identification)
was developed by Van Overschee and De Moor (1994). It is the most widely
used subspace algorithm.

**Algorithm:**

1. **Construct Hankel matrices** $$U_p, U_f, Y_p, Y_f$$ with horizons $$f$$ and $$p$$.

2. **Compute the oblique projection:**

   $$
   \mathcal{O}_i = Y_f /_{U_f} W_p
   $$

   This is the estimate of the weighted observability matrix times the state
   sequence.

3. **SVD of the oblique projection:**

   $$
   \mathcal{O}_i = U_s \Sigma_s V_s^T
   $$

   The singular values $$\sigma_1 \geq \sigma_2 \geq \cdots$$ reveal the
   system order: there should be a clear gap between $$\sigma_{n_x}$$ and
   $$\sigma_{n_x + 1}$$.

4. **Select model order** $$n_x$$ (see Section 2.7).

5. **Extract the extended observability matrix:**

   $$
   \Gamma_f = U_s[:, 1:n_x] \cdot \text{diag}(\sqrt{\sigma_1}, \ldots, \sqrt{\sigma_{n_x}})
   $$

   The observability matrix has the structure:

   $$
   \Gamma_f = \begin{bmatrix} C \\ CA \\ CA^2 \\ \vdots \\ CA^{f-1} \end{bmatrix}
   $$

6. **Extract system matrices:**

   - $$C$$ is the first $$n_y$$ rows of $$\Gamma_f$$:

     $$
     C = \Gamma_f[1:n_y, :]
     $$

   - $$A$$ from the shift property of the observability matrix:

     $$
     \Gamma_f^{\uparrow} A = \Gamma_f^{\downarrow}
     $$

     where $$\Gamma_f^{\uparrow}$$ is $$\Gamma_f$$ with the last $$n_y$$
     rows removed and $$\Gamma_f^{\downarrow}$$ is $$\Gamma_f$$ with the
     first $$n_y$$ rows removed. Then:

     $$
     A = (\Gamma_f^{\uparrow})^{\dagger} \Gamma_f^{\downarrow}
     $$

   - $$B$$ and $$D$$ are found by solving the state and output equations
     in a least-squares sense:

     $$
     \begin{bmatrix} X_{k+1} \\ Y_k \end{bmatrix}
     = \begin{bmatrix} A & B \\ C & D \end{bmatrix}
     \begin{bmatrix} X_k \\ U_k \end{bmatrix}
     + \text{residual}
     $$

     where $$X_k$$ is the estimated state sequence obtained from the
     pseudoinverse of the observability matrix:

     $$
     X = \Gamma_f^{\dagger} \mathcal{O}_i
     $$


### 2.5 MOESP Algorithm

MOESP (Multivariable Output-Error State Space), developed by Verhaegen and
Dewilde (1992), uses a different projection strategy than N4SID.

**Key difference from N4SID.** Instead of the oblique projection, MOESP
projects $$Y_f$$ onto the orthogonal complement of the row space of $$U_f$$:

$$
Y_f^{\perp} = \Pi_{U_f}^{\perp}(Y_f) = Y_f - Y_f U_f^T (U_f U_f^T)^{-1} U_f
$$

This removes the direct influence of future inputs from the future outputs.
The remaining signal contains only the state-dependent component.

**Algorithm:**

1. Compute $$Y_f^{\perp} = \Pi_{U_f}^{\perp}(Y_f)$$
2. SVD: $$Y_f^{\perp} = U_s \Sigma_s V_s^T$$
3. Select order $$n_x$$ from the singular value gap
4. Extract $$\Gamma_f = U_s[:, 1:n_x] \cdot \text{diag}(\sqrt{\sigma_1}, \ldots)$$
5. Extract $$A, B, C, D$$ as in N4SID

**Advantages over N4SID.** MOESP can be more numerically stable because the
orthogonal projection is easier to compute than the oblique projection.
It is also slightly more robust when the input is not sufficiently exciting.

**Disadvantage.** MOESP may give less accurate state estimates because the
orthogonal projection discards information that the oblique projection retains.


### 2.6 CVA Algorithm

Canonical Variate Analysis (CVA), developed by Larimore (1990), applies
statistical weighting based on the covariance structure of the data.

**Key idea.** CVA finds the linear combinations of past data that have
maximum correlation with future outputs. This is a canonical correlation
analysis between the past and future data matrices.

**Algorithm:**

1. Remove future input contribution:

   $$
   Y_f^{\perp} = \Pi_{U_f}^{\perp}(Y_f), \quad W_p^{\perp} = \Pi_{U_f}^{\perp}(W_p)
   $$

2. Compute covariance matrices:

   $$
   \Sigma_{ff} = \frac{1}{N_c} Y_f^{\perp} (Y_f^{\perp})^T, \quad
   \Sigma_{pp} = \frac{1}{N_c} W_p^{\perp} (W_p^{\perp})^T
   $$

   $$
   \Sigma_{fp} = \frac{1}{N_c} Y_f^{\perp} (W_p^{\perp})^T
   $$

3. Compute inverse square roots via Cholesky decomposition:

   $$
   \Sigma_{ff} = L_f L_f^T, \quad \Sigma_{pp} = L_p L_p^T
   $$

4. SVD of the weighted cross-covariance:

   $$
   L_f^{-1} \Sigma_{fp} L_p^{-T} = U_s \Sigma_s V_s^T
   $$

   The singular values $$\sigma_i$$ are the canonical correlations.

5. Select order and recover the observability matrix:

   $$
   \Gamma_f = L_f U_s[:, 1:n_x] \cdot \text{diag}(\sqrt{\sigma_1}, \ldots)
   $$

**Statistical interpretation.** The canonical correlations $$\sigma_i$$
measure the predictive power of each state component. A canonical correlation
close to 1 means the corresponding state direction is highly predictable from
past data; close to 0 means it is essentially noise. This makes CVA naturally
suited for order selection.

**Advantages of CVA.**

- Statistically optimal weighting: gives the minimum-variance state estimates
  under Gaussian noise assumptions
- Built-in order selection via canonical correlations
- More robust to colored noise than N4SID/MOESP

**Disadvantages.**

- Requires the covariance matrices to be non-singular, which may fail with
  very short data sets or redundant signals
- More computationally expensive due to the Cholesky decompositions


### 2.7 Model Order Selection

The model order $$n_x$$ is the number of state variables and is determined
from the singular values of the projection SVD.

**Singular value gap criterion.** Plot the singular values on a logarithmic
scale. A clear "gap" between $$\sigma_{n_x}$$ and $$\sigma_{n_x+1}$$
indicates that the first $$n_x$$ singular values capture the true system
dynamics while the remaining ones represent noise.

Formally, compute the ratio:

$$
r_i = \frac{\sigma_i}{\sigma_{i+1}}, \quad i = 1, 2, \ldots
$$

The estimated order is:

$$
\hat{n}_x = \arg\max_{i} r_i
$$

subject to $$1 \leq \hat{n}_x \leq n_x^{\max}$$.

**Energy criterion (alternative).** Select the smallest $$n_x$$ such that:

$$
\frac{\sum_{i=1}^{n_x} \sigma_i^2}{\sum_{i=1}^{r} \sigma_i^2} \geq \eta
$$

where $$\eta$$ is a threshold (e.g., 0.99 or 99% of the total energy) and
$$r$$ is the rank of the projection matrix.

**Relative threshold criterion.** Select the smallest $$n_x$$ such that:

$$
\frac{\sigma_{n_x + 1}}{\sigma_1} < \tau
$$

where $$\tau$$ is the threshold (default 0.05). This is the method used
by default in the Azeotrope implementation.

**Practical guidelines:**

| System Type | Typical $$n_x$$ |
|---|---|
| SISO with dead time $$d$$ and one time constant | $$d + 1$$ to $$d + 2$$ |
| SISO with oscillatory dynamics | $$d + 2$$ to $$d + 4$$ |
| MIMO with $$n_y$$ outputs | $$\sum_j (d_j + 1)$$ to $$2 \cdot n_y \cdot \max(d_j + 2)$$ |
| General rule of thumb | 1 per dominant time constant + 1 per dead time step |

**Over-fitting risk.** Choosing $$n_x$$ too large introduces noise-fitting:
the extra states capture random fluctuations in the data rather than true
dynamics. This leads to poor prediction on new data. Under-fitting ($$n_x$$
too small) misses important dynamics but is generally safer for controller
design.


### 2.8 Stability Enforcement

Subspace identification does not inherently guarantee that the identified
system is stable (all eigenvalues of $$A$$ inside the unit circle). For
controller design, stability is essential.

**Eigenvalue reflection.** If eigenvalue $$\lambda_i$$ of $$A$$ satisfies
$$|\lambda_i| \geq 1$$, it is reflected inside the unit circle:

$$
\lambda_i^{\text{stable}} = \frac{\lambda_i}{|\lambda_i|} \cdot 0.99
$$

The stabilized $$A$$ matrix is reconstructed:

$$
A_{\text{stable}} = V \, \text{diag}(\lambda_1^{\text{stable}}, \ldots, \lambda_{n_x}^{\text{stable}}) \, V^{-1}
$$

where $$V$$ is the eigenvector matrix of the original $$A$$.

**Trade-off.** Eigenvalue reflection preserves the direction (mode shape)
of each eigenvalue but modifies its magnitude. For eigenvalues that are
only slightly outside the unit circle (e.g., $$|\lambda| = 1.001$$), this
distortion is negligible. For strongly unstable eigenvalues, it can
significantly alter the model, and the root cause (incorrect data, wrong
order selection, or a genuinely unstable process) should be investigated.


### 2.9 Kalman Gain Estimation

After identifying $$(A, B, C, D)$$, the Kalman gain $$K_f$$ is estimated
from the one-step prediction residuals.

1. Simulate the identified model forward in time with zero Kalman gain:

   $$
   \hat{x}(k+1) = A \hat{x}(k) + B u(k)
   $$

   $$
   \hat{y}(k) = C \hat{x}(k) + D u(k)
   $$

2. Compute innovations: $$e(k) = y(k) - \hat{y}(k)$$

3. Estimate the process and measurement noise covariances $$Q$$ and $$R$$
   from the innovation sequence, then solve the discrete algebraic Riccati
   equation (DARE) for the optimal Kalman gain.

Alternatively, a simpler approach estimates $$K_f$$ directly by regression
of state updates on innovations, which is the method used in the implementation.


### 2.10 Conversion to Step Response

The identified state-space model $$(A, B, C, D)$$ is converted to a
step response sequence for use in the DMC-style controller:

**Markov parameters (FIR):**

$$
g_0 = D
$$

$$
g_k = C A^{k-1} B, \quad k = 1, 2, \ldots, N-1
$$

**Step response:**

$$
S_0 = D
$$

$$
S_k = S_{k-1} + C A^{k-1} B = D + \sum_{i=0}^{k-1} C A^i B
$$

This can be computed efficiently by iterating:

$$
P_0 = I_{n_x}
$$

$$
S_k = S_{k-1} + C P_{k-1} B, \quad P_k = P_{k-1} \cdot A
$$

The matrix power $$A^k$$ is never computed explicitly (which would be
numerically unstable for large $$k$$); instead, $$P_k = A^k$$ is accumulated
one multiplication at a time.


---

## 3. Constrained Identification

### 3.1 Motivation

In many industrial applications, the process engineer knows certain properties
of the process that the identification algorithm should respect:

- **Sign constraints**: Increasing the coolant flow should *always* decrease
  the reactor temperature (negative gain).
- **Dead-time constraints**: The response of a temperature sensor downstream
  of a heat exchanger cannot start before the fluid transport delay.
- **Gain relationships**: Mass balance dictates that the ratio of two gains
  equals the stoichiometric ratio.
- **Magnitude bounds**: The gain of a particular channel must lie within a
  known range from first-principles calculations.

Unconstrained identification may violate these properties due to noise,
insufficient excitation, or collinear inputs. Constrained identification
incorporates process knowledge as hard constraints on the identified
parameters.


### 3.2 Formulation

The constrained identification problem is:

$$
\min_{\theta} \; \| Y - \Phi \theta \|_F^2 + \alpha \| \theta \|_F^2
$$

$$
\text{subject to:} \quad h_j(\theta) = 0, \quad j = 1, \ldots, n_{\text{eq}}
$$

$$
\phantom{\text{subject to:}} \quad g_j(\theta) \geq 0, \quad j = 1, \ldots, n_{\text{ineq}}
$$

where:

- $$\alpha \| \theta \|_F^2$$ is Tikhonov regularization (prevents overfitting),
- $$h_j(\theta) = 0$$ are equality constraints,
- $$g_j(\theta) \geq 0$$ are inequality constraints.

The constraints are linear or nearly linear in the parameters, making this
a quadratic program (QP) or a linearly constrained least-squares problem.


### 3.3 Gain Constraints

The steady-state gain for channel $$(p, q)$$ is the sum of all FIR coefficients
for that channel:

$$
K^{(p,q)} = \sum_{k=0}^{n-1} g_k^{(p,q)} = \sum_{k=0}^{n-1} \theta_{k \cdot n_u + q, \; p}
$$

**Positive gain constraint:**

$$
K^{(p,q)} \geq 0 \quad \Leftrightarrow \quad a^T_{\text{gain}} \, \text{vec}(\theta) \geq 0
$$

where $$a_{\text{gain}}$$ is a vector with ones at the positions corresponding
to the $$(p, q)$$ channel coefficients.

**Negative gain constraint:**

$$
K^{(p,q)} \leq 0 \quad \Leftrightarrow \quad -a^T_{\text{gain}} \, \text{vec}(\theta) \geq 0
$$

**Bounded gain constraint:**

$$
K_{\min} \leq K^{(p,q)} \leq K_{\max}
$$

This is equivalent to two inequality constraints:

$$
a^T_{\text{gain}} \, \text{vec}(\theta) \geq K_{\min}
$$

$$
-a^T_{\text{gain}} \, \text{vec}(\theta) \geq -K_{\max}
$$


### 3.4 Dead-Time Constraints

A dead time of $$d$$ samples for channel $$(p, q)$$ means the first $$d$$
FIR coefficients must be zero:

$$
g_k^{(p,q)} = 0, \quad k = 0, 1, \ldots, d-1
$$

These are equality constraints on individual elements of $$\theta$$:

$$
\theta_{k \cdot n_u + q, \; p} = 0, \quad k = 0, \ldots, d-1
$$

In the vectorized formulation, each constraint is a row in an equality
constraint matrix with a single non-zero entry.


### 3.5 Gain Ratio Constraints

Mass and energy balances impose ratios between gains. For example, if the
gain from MV 1 to CV 1 should be twice the gain from MV 2 to CV 1:

$$
\frac{K^{(1,1)}}{K^{(1,2)}} = r
$$

This is rewritten as a linear constraint:

$$
K^{(1,1)} - r \cdot K^{(1,2)} = 0
$$

or, expanding:

$$
\sum_{k=0}^{n-1} \theta_{k n_u + 0, \; 0} - r \sum_{k=0}^{n-1} \theta_{k n_u + 1, \; 0} = 0
$$

In practice, an exact ratio constraint is often too restrictive. A tolerance
$$\pm \epsilon$$ is allowed:

$$
\left| K^{(1,1)} - r \cdot K^{(1,2)} \right| \leq \epsilon
$$

This is implemented as two inequality constraints.


### 3.6 Solver

The constrained identification problem is solved using Sequential Least Squares
Programming (SLSQP), which handles equality and inequality constraints on
a smooth objective function. SLSQP is an iterative algorithm that:

1. Approximates the Lagrangian Hessian using BFGS updates
2. Solves a quadratic subproblem at each iteration
3. Uses a line search to ensure descent

The **gradient** of the objective with respect to the vectorized parameters is:

$$
\nabla J = -2 \, \text{vec}(\Phi^T (Y - \Phi \theta)) + 2 \alpha \, \text{vec}(\theta)
$$

The unconstrained DLS solution is used as the initial guess $$\theta_0$$,
which typically provides a warm start close to the constrained optimum.

**Convergence.** SLSQP converges quadratically near the solution (super-linear
convergence of the BFGS approximation). Typical convergence is achieved in
50-200 iterations for problems with up to several hundred parameters and
tens of constraints. The algorithm terminates when the function value
change is below $$10^{-10}$$.


---

## 4. Closed-Loop Identification

### 4.1 The Feedback Problem

When identification data is collected while a controller is running, the
input $$u$$ is correlated with the output noise through the feedback loop:

$$
y(k) = G(q) u(k) + H(q) e(k)
$$

$$
u(k) = r(k) - C(q) y(k)
$$

where $$G(q)$$ is the plant transfer function, $$H(q)$$ is the noise model,
$$C(q)$$ is the controller, $$r(k)$$ is the setpoint, and $$e(k)$$ is white
noise. Substituting the second equation into the first:

$$
y(k) = G(q) [r(k) - C(q) y(k)] + H(q) e(k)
$$

$$
[I + G(q) C(q)] y(k) = G(q) r(k) + H(q) e(k)
$$

The key problem is that $$u(k)$$ depends on past values of $$y(k)$$, which
in turn depend on past values of $$e(k)$$. Therefore, $$u(k)$$ and $$e(k)$$
are correlated, and the standard open-loop identification methods (DLS,
open-loop subspace) produce **biased** estimates of $$G(q)$$.

**Magnitude of bias.** The bias depends on the controller gain and the
noise-to-signal ratio. In aggressive controllers (high gain), the bias can
be severe. In loosely controlled systems (low gain or manual mode with
occasional adjustments), the bias may be tolerable.


### 4.2 Instrumental Variable (IV) Method

The IV method uses an external signal that is correlated with the input
$$u$$ but uncorrelated with the noise $$e$$. The setpoint $$r(k)$$ is the
natural instrument: it influences $$u$$ through the controller but is
(by assumption) chosen independently of the noise.

**Algorithm:**

1. Build block-Hankel matrices $$U_p, U_f, Y_p, Y_f$$ from the input-output data.

2. Build setpoint Hankel matrices $$R_p, R_f$$ from the setpoint data.

3. Construct the instrument matrix:

   $$
   Z = \begin{bmatrix} R_p \\ Y_p \end{bmatrix}
   $$

   Past outputs are included because they are correlated with the state
   (needed for state estimation) and, under the assumption that the noise
   has finite memory, past outputs are asymptotically uncorrelated with
   future noise.

4. Compute the IV-projected output:

   $$
   \mathcal{O}_{\text{IV}} = \frac{1}{N_c} Y_f Z^T \left( \frac{1}{N_c} Z Z^T + \lambda I \right)^{-1} Z
   $$

   where $$\lambda$$ is a small regularization parameter.

5. SVD of $$\mathcal{O}_{\text{IV}}$$ and extraction of system matrices
   follows the same procedure as open-loop subspace identification.

**Requirements:**

- Setpoint variations during the test (step tests on setpoints are ideal)
- The setpoints must be sufficiently exciting (varied enough to span
  the input space)
- The setpoint changes should be uncorrelated with external disturbances

**Limitations:**

- If setpoints were not varied (pure load rejection test), IV cannot be used
- The method assumes the noise model $$H(q)$$ has finite impulse response,
  which is approximately true for ARMA noise models


### 4.3 Two-Stage Method

The two-stage method does not require setpoint data. It identifies the
controller first, then uses it to reconstruct an "open-loop equivalent"
input.

**Stage 1: Controller identification.** Estimate the controller transfer
function $$\hat{C}(q)$$ from the $$(y, u)$$ data using an ARX model:

$$
u(k) = \sum_{i=1}^{n_{\text{arx}}} K_i \, y(k-i) + v(k)
$$

where $$v(k)$$ is the controller's innovation (the part of $$u$$ not
explained by past $$y$$). This is solved by ridge regression:

$$
\hat{K}_{\text{arx}} = (\Phi_c^T \Phi_c + \alpha I)^{-1} \Phi_c^T U
$$

where $$\Phi_c$$ is the Toeplitz matrix of lagged outputs and $$U$$ is
the input vector.

**Stage 2: Innovation reconstruction.** Compute the innovation input:

$$
v(k) = u(k) - \hat{C}(q) y(k) = u(k) - \sum_{i=1}^{n_{\text{arx}}} \hat{K}_i \, y(k-i)
$$

The innovation $$v(k)$$ is (approximately) uncorrelated with the noise
$$e(k)$$, so standard open-loop subspace identification can be applied to
the pair $$(v, y)$$.

**Advantages:**

- Does not require setpoint data
- Can work with arbitrary controller structures

**Disadvantages:**

- Error in Stage 1 (controller estimation) propagates to Stage 2
- The ARX model may not accurately represent the actual controller,
  especially for nonlinear or complex controllers
- The regularization parameter $$\alpha$$ requires tuning


### 4.4 Regularized Direct Method

The simplest closed-loop approach applies Tikhonov regularization directly
to the subspace identification Hankel matrices.

**Algorithm:**

1. Construct Hankel matrices and compute the oblique projection as in
   open-loop N4SID.

2. Regularize the inversion step:

   Instead of:

   $$
   \mathcal{O}_i = Y_f \begin{bmatrix} U_f \\ W_p \end{bmatrix}^{\dagger}
   \begin{bmatrix} 0 \\ W_p \end{bmatrix}
   $$

   use:

   $$
   M = \frac{1}{N_c} \begin{bmatrix} U_f \\ W_p \end{bmatrix}
   \begin{bmatrix} U_f \\ W_p \end{bmatrix}^T
   $$

   $$
   \mathcal{O}_i = \frac{1}{N_c} Y_f \begin{bmatrix} U_f \\ W_p \end{bmatrix}^T
   \left( M + \lambda \frac{\text{tr}(M)}{n_M} I \right)^{-1}
   S_p W_p
   $$

   where $$S_p$$ is a selector matrix that picks out the $$W_p$$ rows,
   and $$\lambda$$ is the regularization strength.

3. Proceed with SVD and system matrix extraction as usual.

**Effect of regularization.** The regularization shrinks the estimated
parameters toward zero, which:

- Reduces the variance of the estimates (beneficial when data is noisy)
- Introduces bias toward a lower-gain model (which may or may not be
  acceptable)
- Suppresses the feedback-induced bias (the main goal)

The regularization strength $$\lambda$$ controls the trade-off. Typical
values range from 0.01 to 1.0.

**When to use.** This is the recommended default for closed-loop
identification when:

- No setpoint data is available
- The controller gain is moderate (not extremely aggressive)
- A rough model is acceptable (for initial controller design or model
  updating)


---

## 5. CV Grouping

### 5.1 Why Grouping

Large MIMO systems in industrial practice may have 20, 50, or even 100 CVs
and a comparable number of MVs. Full MIMO subspace identification of such
systems faces several challenges:

- **Computational cost**: The Hankel matrices have dimensions proportional to
  $$f \cdot n_y$$ and $$p \cdot (n_u + n_y)$$. For $$n_y = 50$$ and
  $$f = 20$$, the future output Hankel has 1000 rows, requiring SVD of
  matrices that may exceed available memory.

- **Model order explosion**: The total state dimension scales with the number
  of outputs. A 50-CV system might need $$n_x = 100+$$ states, which is
  computationally intractable and overfits the data.

- **Sparse interaction structure**: In practice, most CVs interact with only
  a subset of MVs. A column temperature on tray 10 of a distillation column
  is strongly influenced by reboiler duty and reflux flow but weakly by
  a distant side-draw flow. Identifying a full MIMO model unnecessarily
  estimates these weak interactions.

CV grouping decomposes the large MIMO problem into smaller sub-problems,
each tractable for subspace identification.


### 5.2 Auto-Grouping by Cross-Correlation

The auto-grouping algorithm uses agglomerative (hierarchical) clustering on
the pairwise correlation matrix of the CV signals.

**Algorithm:**

1. **Compute the correlation matrix:**

   $$
   \rho_{ij} = \frac{\text{Cov}(y_i, y_j)}{\sigma_{y_i} \sigma_{y_j}}
   $$

   where $$y_i, y_j$$ are time series of CVs $$i$$ and $$j$$.

2. **Define a distance metric:**

   $$
   d_{ij} = 1 - |\rho_{ij}|
   $$

   CVs with high absolute correlation (positive or negative) are "close"
   in this metric.

3. **Agglomerative clustering:**

   Starting with each CV in its own cluster, iteratively merge the two
   closest clusters until the distance threshold is reached. The linkage
   criterion is "average" (UPGMA):

   $$
   d(C_a, C_b) = \frac{1}{|C_a| |C_b|} \sum_{i \in C_a, j \in C_b} d_{ij}
   $$

   Clusters are merged when $$d(C_a, C_b) < 1 - \rho_{\text{threshold}}$$,
   where $$\rho_{\text{threshold}}$$ is the correlation threshold (default 0.5).

4. **Size enforcement:** If a cluster exceeds the maximum group size
   (default 6), it is split into sub-clusters of at most that size.

**Rationale.** CVs with high correlation share common dynamics (they respond
to the same MVs with similar time constants). Identifying them together
captures their cross-coupling accurately. CVs with low correlation respond
to different MVs or with very different dynamics and can be identified
independently.


### 5.3 MISO Decomposition

The simplest grouping strategy places each CV in its own group, resulting
in a set of MISO (Multiple Input, Single Output) identification problems:

$$
\text{Group } j: \quad y_j(k) = f(u_1(k), u_2(k), \ldots, u_{n_u}(k))
$$

Each MISO problem uses all $$n_u$$ inputs but only one output. The state
dimension is typically much smaller (1-5 states per MISO problem).

**Advantages:**

- Simple, parallelizable, no cross-coupling issues
- Each sub-model can use a different model order

**Disadvantages:**

- Ignores CV-CV coupling (e.g., if CV 1 and CV 2 share a common mode,
  MISO decomposition may identify it inconsistently)
- Total state count may be larger than a well-grouped MIMO identification


### 5.4 Block-Diagonal Assembly

After per-group identification, the individual state-space models are
assembled into a single block-diagonal model.

If group $$g$$ has state-space matrices $$(A_g, B_g, C_g, D_g)$$ with
state dimension $$n_{x,g}$$, the combined model is:

$$
A = \text{blkdiag}(A_1, A_2, \ldots, A_G)
$$

$$
B = \begin{bmatrix} B_1 \\ B_2 \\ \vdots \\ B_G \end{bmatrix}, \quad
C = \text{row-permuted}(C_1, C_2, \ldots, C_G), \quad
D = \text{row-permuted}(D_1, D_2, \ldots, D_G)
$$

The $$C$$ and $$D$$ matrices must be rearranged so that the rows correspond
to the original CV ordering. Specifically, if group $$g$$ contains CV
indices $$\{i_{g,1}, i_{g,2}, \ldots\}$$, then:

$$
C_{\text{combined}}[i_{g,j}, \; n_{x,<g} : n_{x,<g} + n_{x,g}] = C_g[j, :]
$$

where $$n_{x,<g} = \sum_{h < g} n_{x,h}$$ is the cumulative state offset.

The total state dimension is $$n_x^{\text{total}} = \sum_g n_{x,g}$$.

The step response and gain matrix of the combined model are computed by
overlaying the per-group results onto the full $$(n_y \times n_u)$$ matrix,
with zeros for channel pairs not present in any group.


---

## 6. Data Conditioning

### 6.1 Overview

Industrial step-test data arrives from plant historians (e.g., OSIsoft PI,
Honeywell PHD, Yokogawa Exaquantum) and inevitably contains:

- **Sensor faults**: frozen readings (flatline), spikes from electrical
  interference, out-of-range values from sensor calibration issues
- **Communication dropouts**: NaN gaps from network interruptions
- **Compression artifacts**: historian data compression creates irregular
  time spacing and artificial step-like patterns
- **Slow drifts**: ambient temperature changes, catalyst deactivation,
  fouling -- not part of the dynamic model

The data conditioning pipeline detects and corrects these issues before
identification. Each step is optional and configurable.


### 6.2 Cutoff Detection and Bad-Data Replacement

**Cutoff detection.** Each variable has upper and lower engineering limits
$$[L_{\text{lo}}, L_{\text{hi}}]$$ beyond which readings are physically
impossible or instrument-limited:

$$
\text{bad}_{\text{cutoff}}(k) = \begin{cases}
\text{true} & \text{if } y(k) > L_{\text{hi}} \text{ or } y(k) < L_{\text{lo}} \\
\text{false} & \text{otherwise}
\end{cases}
$$

**Action options:**

- **Reject**: Mark the sample as bad (NaN) and replace later
- **Clamp**: Replace with the limit value: $$y(k) \leftarrow \min(\max(y(k), L_{\text{lo}}), L_{\text{hi}})$$

**Bad-data replacement methods.** Once samples are marked as bad (from
cutoff, flatline, or spike detection), they must be replaced. Three strategies
are available:

1. **Interpolate**: Linear interpolation between the last good value before
   the bad segment and the first good value after:

   $$
   y_{\text{replaced}}(k) = y_{\text{before}} + \frac{k - k_{\text{before}}}{k_{\text{after}} - k_{\text{before}}} (y_{\text{after}} - y_{\text{before}})
   $$

   This is the default and generally the best choice for short gaps.

2. **Last-good hold**: Hold the last known good value:

   $$
   y_{\text{replaced}}(k) = y(k_{\text{last good}})
   $$

   Simpler but introduces artificial flatlines.

3. **Average**: Replace with the mean of all good samples:

   $$
   y_{\text{replaced}}(k) = \bar{y}_{\text{good}}
   $$

   Only appropriate for short random dropouts in stationary data.

A **maximum consecutive bad** guard (default 50) prevents run-away
replacement. If a bad segment exceeds this length, the samples are left
as NaN (and the segment should be excluded from identification).


### 6.3 Flatline Detection

A flatline (frozen sensor) is detected using a consecutive-sample accumulator.

**Algorithm.** Initialize $$r = 0$$ (run length counter). For each sample
$$k = 1, 2, \ldots, N-1$$:

$$
r \leftarrow \begin{cases}
r + 1 & \text{if } |y(k) - y(k-1)| < \epsilon_{\text{flat}} \\
0 & \text{otherwise}
\end{cases}
$$

$$
\text{bad}_{\text{flatline}}(k) = (r \geq n_{\text{flat}})
$$

where:

- $$\epsilon_{\text{flat}}$$ is the flatline threshold (minimum expected
  change per sample; set to 0.1% of the variable's range)
- $$n_{\text{flat}}$$ is the flatline period (number of consecutive samples
  required to trigger; adapted based on the coefficient of variation)

**Auto-configuration.** The flatline period is set adaptively:

$$
n_{\text{flat}} = \text{clip}\left(30 + 330 \cdot (1 - \text{CV}), \; 30, \; 360\right)
$$

where $$\text{CV} = \sigma_{\Delta y} / \sigma_y$$ is the coefficient of
variation of the first differences. Low-variance signals (small CV) need
shorter periods to catch flatlines; high-variance signals need longer
periods to avoid false positives.


### 6.4 Spike Detection with Reclassification

**Detection.** A spike is a sample-to-sample jump exceeding a threshold:

$$
\text{spike candidate}(k) = (|y(k) - y(k-1)| > \epsilon_{\text{spike}})
$$

where $$\epsilon_{\text{spike}} = 5 \sigma_{\Delta y}$$ (5 times the
first-difference standard deviation).

**Reclassification.** Not every threshold crossing is a spike -- some are
genuine step changes (e.g., an operator changing a setpoint). The
reclassification logic distinguishes the two:

1. When a threshold crossing occurs at time $$k$$, start a pending batch
   and set $$r = 1$$.
2. For subsequent samples, if $$|y(k) - y(k-1)| \leq \epsilon_{\text{spike}}$$,
   increment $$r$$.
3. If $$r \geq n_{\text{reclassify}}$$ (default 3), the new level has
   persisted -- reclassify as a genuine step change and clear the pending batch.
4. If another threshold crossing occurs before persistence, finalize the
   pending batch as confirmed spikes (mark them bad).

**Intuition.** A true spike goes up and comes back down within 1-2 samples.
A genuine step change goes up and stays at the new level. The persistence
counter distinguishes the two.


### 6.5 Steady-State Detection

Steady-state detection identifies time periods where the process is not
actively responding to input changes. These periods are useful for:

- Estimating noise statistics ($$\sigma^2$$)
- Calibrating disturbance models
- Filtering out data where no dynamic information is present

The implementation uses the **Aspen IQ dual exponential filter algorithm**.

**Algorithm.** For each variable, maintain two exponential filters:

- **Heavy (slow) filter**: tracks the long-term trend

  $$
  H(k) = \alpha_h \cdot y(k) + (1 - \alpha_h) \cdot H(k-1)
  $$

- **Light (fast) filter**: responds quickly to transients

  $$
  L(k) = \alpha_l \cdot y(k) + (1 - \alpha_l) \cdot L(k-1)
  $$

where $$\alpha_l = \alpha_h \cdot r_f$$ with $$r_f \geq 1$$ being the
filter ratio (default 5.0). The light filter has a larger smoothing constant
and therefore responds faster.

**Decision criterion.** The variable is at steady state when the two filters
agree:

$$
\text{is\_steady}(k) = \left( |H(k) - L(k)| \leq 3\sigma \right)
$$

where $$\sigma$$ is the noise standard deviation.

**Intuition.** During a transient (step response), the light filter tracks
the change quickly while the heavy filter lags behind. The difference
$$|H - L|$$ becomes large. At steady state, both filters converge to the
same value and the difference is small (within the noise band).

**Plant-wide indicator.** Individual variable indicators are combined using
weighted voting:

$$
\text{SSTOTAL}(k) = \frac{\sum_{i} w_i \cdot \text{SS}_i(k)}{\sum_{i} w_i}
$$

where $$w_i$$ is the importance rank of variable $$i$$ (0-10 scale) and
$$\text{SS}_i(k) \in \{0, 100\}$$ is the per-variable indicator.

The plant is considered at steady state when:

$$
\text{SSTOTAL}(k) \geq 50\%
$$

**Auto-configuration.** The heavy filter constant $$\alpha_h$$ is set based
on the noise-to-signal ratio:

$$
\alpha_h = \text{clip}(0.15 \cdot (1 - r_n), \; 0.01, \; 0.3)
$$

where $$r_n = \sigma_{\Delta y} / \sigma_y$$. Noisy signals get smaller
$$\alpha_h$$ (more smoothing); clean signals get larger $$\alpha_h$$
(faster tracking).


### 6.6 Resampling

Industrial historian data often arrives at 1-second intervals, but process
dynamics operate on much longer time scales (30 seconds to 5 minutes).
Resampling (downsampling) to an appropriate period:

1. **Reduces noise**: averaging over a window of $$m$$ samples reduces the
   noise standard deviation by $$\sqrt{m}$$
2. **Reduces the number of FIR coefficients needed**: a process with a
   5-minute settling time needs $$n = 300$$ coefficients at 1-second sampling
   but only $$n = 5$$ at 60-second sampling
3. **Improves regression conditioning**: fewer parameters relative to data points

**Trade-off analysis.** Two metrics quantify the resampling trade-off:

- **Noise ratio**: $$r_{\text{noise}} = \sigma_{\Delta y, \text{resampled}} / \sigma_{\Delta y, \text{raw}}$$

  Values less than 1 indicate noise reduction. Lower is better.

- **Signal preservation**: $$p_{\text{signal}} = (\sigma_{y, \text{resampled}} / \sigma_{y, \text{raw}}) \times 100\%$$

  Values close to 100% indicate the resampled signal retains the original
  variability. Higher is better.

The optimal resample period is the one that achieves good noise reduction
($$r_{\text{noise}} < 0.5$$) while preserving signal content
($$p_{\text{signal}} > 90\%$$).

**Aggregation methods:**

- **Mean**: Average all samples in each bin. Best noise reduction.
- **Last**: Take the last sample in each bin. Preserves exact values.
- **First**: Take the first sample in each bin. Preserves exact values.


### 6.7 Output Transforms

Some process variables have skewed or heavy-tailed distributions that
degrade linear model identification. Applying a monotonic transform can
make the variable approximately Gaussian.

**Available transforms:**

| Transform | Forward $$z = f(y)$$ | Inverse $$y = f^{-1}(z)$$ | Use Case |
|---|---|---|---|
| Log | $$z = \ln(y + a)$$ | $$y = e^z - a$$ | Concentrations, flow rates |
| Log10 | $$z = \log_{10}(y + a)$$ | $$y = 10^z - a$$ | pH, order-of-magnitude variables |
| Sqrt | $$z = \sqrt{y}$$ | $$y = z^2$$ | Variance-stabilizing |
| Logit | $$z = \ln\frac{y}{1-y}$$ | $$y = \frac{1}{1 + e^{-z}}$$ | Fractions, compositions (0-1) |
| Power | $$z = \text{sgn}(y)|y|^c$$ | $$y = \text{sgn}(z)|z|^{1/c}$$ | General nonlinearity |
| Box-Cox | $$z = \frac{y^\lambda - 1}{\lambda}$$ | $$y = (z\lambda + 1)^{1/\lambda}$$ | Auto-fitted optimal transform |
| Shift-Rate-Power | $$z = b(y + a)^c$$ | $$y = (z/b)^{1/c} - a$$ | General with shift |
| PWLN | piecewise linear | piecewise linear | Valve characteristics |

**Box-Cox transform.** The Box-Cox family is parameterized by $$\lambda$$:

$$
z = \begin{cases}
\frac{y^\lambda - 1}{\lambda} & \lambda \neq 0 \\
\ln(y) & \lambda = 0
\end{cases}
$$

The optimal $$\lambda$$ is found by maximum likelihood estimation, which
in practice means trying a range of $$\lambda$$ values and selecting the
one that makes the transformed data closest to Gaussian.

**Auto-selection via Shapiro-Wilk test.** The implementation evaluates
all candidate transforms and selects the one whose forward output is
closest to a Gaussian distribution, as measured by the Shapiro-Wilk
$$W$$ statistic:

$$
W = \frac{\left(\sum_{i=1}^n a_i z_{(i)}\right)^2}{\sum_{i=1}^n (z_i - \bar{z})^2}
$$

where $$z_{(i)}$$ are the order statistics and $$a_i$$ are tabulated
constants. $$W$$ ranges from 0 to 1, with 1 indicating perfect normality.

**Importance for APC.** In an APC controller, the bias update (output
correction) operates in the transform domain. The transform must be
invertible so that predictions can be converted back to engineering units
for display, constraint checking, and steady-state target calculation.


---

## 7. Model Quality Assessment

### 7.1 Coefficient of Determination (R-squared)

The coefficient of determination $$R^2$$ measures the fraction of output
variance explained by the model:

$$
R^2 = 1 - \frac{SS_{\text{res}}}{SS_{\text{tot}}} = 1 - \frac{\sum_k (y(k) - \hat{y}(k))^2}{\sum_k (y(k) - \bar{y})^2}
$$

where:

- $$SS_{\text{res}}$$ is the sum of squared residuals
- $$SS_{\text{tot}}$$ is the total sum of squares (variance of the output)
- $$\hat{y}(k)$$ is the model prediction
- $$\bar{y}$$ is the sample mean

**Interpretation:**

| $$R^2$$ | Interpretation |
|---|---|
| $$> 0.90$$ | Excellent fit |
| $$0.80 - 0.90$$ | Good fit, adequate for control |
| $$0.50 - 0.80$$ | Fair fit, investigate data quality |
| $$< 0.50$$ | Poor fit, model may not be useful |

**Caution.** $$R^2$$ can be misleadingly high for data with large trends
(the model merely tracks the trend) or misleadingly low for data with
dominant noise (the model is correct but the SNR is low). Always examine
$$R^2$$ alongside residual analysis.


### 7.2 RMSE and NRMSE

**Root Mean Square Error (RMSE):**

$$
\text{RMSE} = \sqrt{\frac{1}{N} \sum_{k=1}^{N} (y(k) - \hat{y}(k))^2}
$$

RMSE has the same units as the output variable, making it directly
interpretable by process engineers (e.g., "the model prediction error
is typically 0.5 degrees C").

**Normalized RMSE (NRMSE):**

$$
\text{NRMSE} = \frac{\text{RMSE}}{y_{\max} - y_{\min}}
$$

NRMSE normalizes by the range of the output, allowing comparison across
variables with different scales. Values below 0.05 (5%) are generally
considered good.


### 7.3 Condition Number of the Regression Matrix

The condition number $$\kappa(\Phi)$$ of the regression matrix quantifies
how sensitive the identified parameters are to perturbations in the data.

$$
\kappa(\Phi) = \frac{\sigma_{\max}(\Phi)}{\sigma_{\min}(\Phi)}
$$

**Physical causes of ill-conditioning:**

- **Correlated inputs**: If two MVs are always moved together, their columns
  in $$\Phi$$ are nearly parallel, making it impossible to separate their
  individual effects.
- **Insufficient excitation**: If an MV was barely moved during the test,
  its column in $$\Phi$$ has small norm, inflating the condition number.
- **High model order**: More coefficients $$n$$ relative to data samples
  $$N$$ reduces the effective degrees of freedom.

**Remedies:**

- Use Ridge regularization (Section 1.6)
- Extend the step test with better MV excitation
- Reduce the model length $$n$$
- Remove redundant MVs


### 7.4 Ljung-Box Test

See Section 1.10 for the full mathematical description.


### 7.5 Cross-Correlation Analysis

Cross-correlation analysis evaluates the independence and excitation quality
of the MV input signals. This is a pre-identification check on data quality.

**Auto-correlation function (ACF).** For signal $$u_j$$:

$$
\hat{R}_{u_j u_j}(\tau) = \frac{1}{N \sigma_{u_j}^2} \sum_{k=\tau+1}^{N} (u_j(k) - \bar{u}_j)(u_j(k - \tau) - \bar{u}_j)
$$

The ACF decay rate indicates the decorrelation time of the input. Fast decay
(dropping below $$1/e$$ within a few samples) indicates good random excitation.
Slow decay indicates drifts or periodic content.

**Cross-correlation function (CCF).** Between signals $$u_i$$ and $$u_j$$:

$$
\hat{R}_{u_i u_j}(\tau) = \frac{1}{N \sigma_{u_i} \sigma_{u_j}} \sum_{k} (u_i(k) - \bar{u}_i)(u_j(k - \tau) - \bar{u}_j)
$$

High cross-correlation means the MVs were moved together, making their
individual effects difficult to separate.

**Quality grading.** The peak absolute cross-correlation determines the
quality grade:

| Peak $$|\hat{R}_{u_i u_j}|$$ | Grade | Interpretation |
|---|---|---|
| $$< 0.30$$ | IDEAL | Independent inputs, reliable identification |
| $$0.30 - 0.50$$ | ACCEPTABLE | Some coupling, model may show interaction artifacts |
| $$0.50 - 0.80$$ | POOR | Significant coupling, gains may be unreliable |
| $$> 0.80$$ | UNACCEPTABLE | Inputs are effectively collinear, cannot separate effects |

**Periodicity detection.** The ACF is also checked for secondary peaks
(after the initial decay), which indicate periodic content in the input.
Periodic inputs reduce the effective excitation and can cause bias in
FIR identification.


### 7.6 Model Uncertainty Analysis

Model uncertainty is assessed in both the frequency domain and the time
domain, with an A/B/C/D grading system.

#### 7.6.1 Frequency-Domain Uncertainty

The frequency response of the FIR model is:

$$
H(\omega) = \sum_{k=0}^{n-1} g_k \, e^{-j\omega k}
$$

where $$\omega$$ is the frequency in radians per sample. The magnitude
$$|H(\omega)|$$ is the Bode magnitude plot.

The uncertainty in $$|H(\omega)|$$ is propagated from the coefficient
variances. If $$\sigma_{g_k}$$ is the standard deviation of coefficient
$$g_k$$, then:

$$
\text{Var}(|H(\omega)|) \approx \sum_{k=0}^{n-1} \sigma_{g_k}^2
$$

This approximation treats the basis functions $$e^{-j\omega k}$$ as
orthogonal (which is exact only at the DFT frequencies) and uses a
first-order Taylor expansion of the magnitude function.

The $$\pm 2\sigma$$ confidence bands on the magnitude are:

$$
|H(\omega)|_{\pm 2\sigma} = |H(\omega)| \pm 2\sqrt{\sum_k \sigma_{g_k}^2}
$$


#### 7.6.2 Time-Domain Uncertainty

The step response confidence bands are derived from the FIR confidence
intervals by cumulative summation. If the FIR coefficient $$g_k$$ has
a confidence interval $$[g_k^{\text{lo}}, g_k^{\text{hi}}]$$, then the
step response half-width at step $$k$$ is approximately:

$$
\delta S_k = \frac{S_k^{\text{hi}} - S_k^{\text{lo}}}{2}
$$

where the cumulative effect of parameter uncertainty grows with $$k$$
(because later step response values are sums of more coefficients, and
uncertainties add in quadrature).


#### 7.6.3 Grading

Each MV-CV channel is graded on two criteria:

**Steady-state uncertainty grade:**

| Grade | $$\delta K / |K|$$ | Interpretation |
|---|---|---|
| A | $$< 10\%$$ | Highly certain gain |
| B | $$10 - 25\%$$ | Acceptable uncertainty |
| C | $$25 - 50\%$$ | Significant uncertainty |
| D | $$> 50\%$$ | Gain is poorly determined |

**Dynamic uncertainty grade:**

| Grade | $$\max_k \delta S_k / |K|$$ | Interpretation |
|---|---|---|
| A | $$< 20\%$$ | Clean dynamics |
| B | $$20 - 50\%$$ | Moderate uncertainty in shape |
| C | $$50 - 100\%$$ | Significant dynamic uncertainty |
| D | $$> 100\%$$ | Dynamics are poorly determined |

The overall grade is the worse of the two.

**Signal-to-noise ratio (SNR):**

$$
\text{SNR} = 10 \log_{10} \frac{\text{mean}(S_k^2)}{\text{mean}(\delta S_k^2)} \quad \text{[dB]}
$$


### 7.7 Gain Matrix Analysis

The steady-state gain matrix $$K \in \mathbb{R}^{n_y \times n_u}$$ encodes
the fundamental controllability of the system.

#### 7.7.1 Gain Matrix Condition Number

$$
\kappa(K) = \frac{\sigma_{\max}(K)}{\sigma_{\min}(K)}
$$

A high condition number means the system has "difficult" directions where
small MV changes produce large CV responses and "easy" directions where
large MV changes produce small CV responses. This makes control design
challenging.

| $$\kappa(K)$$ | Controllability |
|---|---|
| $$< 10$$ | Easy to control |
| $$10 - 20$$ | Moderate interactions |
| $$20 - 100$$ | Significant interactions, careful tuning needed |
| $$> 100$$ | Near-singular, may need MV/CV pairing changes |


#### 7.7.2 Relative Gain Array (RGA)

The RGA (Bristol, 1966) is defined for square gain matrices:

$$
\Lambda = K \circ (K^{-1})^T
$$

where $$\circ$$ denotes element-wise (Hadamard) product.

**Properties of the RGA:**

1. All rows and columns sum to 1
2. $$\Lambda_{ij}$$ measures the interaction between MV $$j$$ and CV $$i$$
3. $$\Lambda_{ij} = 1$$: no interaction through other loops
4. $$\Lambda_{ij} > 1$$: other loops amplify the effect of MV $$j$$ on CV $$i$$
5. $$\Lambda_{ij} < 0$$: the sign of the gain reverses when other loops are
   closed (dangerous)
6. $$\Lambda_{ij} = 0$$: MV $$j$$ has no effect on CV $$i$$ in steady state

**Pairing guideline.** For decentralized control, pair MV $$j$$ with the
CV $$i$$ that has the largest positive RGA element in column $$j$$. Avoid
pairing with negative RGA elements.

**Interpretation for MPC.** In a full multivariable MPC controller, the
RGA is less directly relevant (the controller handles all interactions
simultaneously), but it still provides useful diagnostic information:

- Large off-diagonal RGA elements indicate strong interaction, requiring
  careful tuning of the move suppression weights
- Negative diagonal RGA elements indicate fundamental problems with the
  MV-CV pairing in the controller design


#### 7.7.3 Colinearity Analysis

Two MV columns of the gain matrix are **colinear** if they have similar
effect on all CVs:

$$
\cos \angle(K_{:,i}, K_{:,j}) = \frac{|K_{:,i}^T K_{:,j}|}{\|K_{:,i}\| \|K_{:,j}\|} \approx 1
$$

Colinear MVs provide redundant control authority. The controller cannot
independently manipulate the CVs using these MVs, leading to:

- Large, opposing MV moves that cancel out
- High sensitivity to model errors
- Potential for MV limit violations

**Severity grading:**

| Cosine Similarity | Severity | Action |
|---|---|---|
| $$> 0.98$$ | High | Remove or constrain one MV |
| $$0.95 - 0.98$$ | Medium | Monitor MV moves closely |
| $$0.90 - 0.95$$ | Low | Generally acceptable |


#### 7.7.4 Sub-Matrix Scanning

For large systems, the condition number of the full gain matrix may be
acceptable, but particular sub-combinations of MVs and CVs may be
ill-conditioned. Sub-matrix scanning evaluates all $$\binom{n_y}{m} \times \binom{n_u}{m}$$
square sub-matrices of size $$m \times m$$ for $$m = 2, 3, 4$$.

Each sub-matrix is tested for:

$$
\kappa(K_{\text{sub}}) > \kappa_{\text{threshold}}
$$

where $$\kappa_{\text{threshold}} = 100$$ by default. Problematic sub-matrices
are reported, sorted by condition number (worst first).


### 7.8 Quality Scorecard

The quality scorecard aggregates all assessment metrics into a traffic-light
grading system with five categories:

1. **DATA QUALITY**: NaN count, outlier count, sample count
2. **MV EXCITATION**: Move count per MV, move amplitude distribution
3. **MODEL FIT**: R-squared, RMSE, residual whiteness, condition number
4. **CONTROLLABILITY**: Gain matrix condition, RGA, colinearity
5. **UNCERTAINTY**: Steady-state and dynamic uncertainty grades

Each category receives a grade:

- **GREEN**: No issues, model is reliable
- **YELLOW**: Minor issues, model may need attention
- **RED**: Significant issues, model may be unreliable

The **overall grade** is the worst of all categories.

**Grading thresholds (selected):**

| Metric | GREEN | YELLOW | RED |
|---|---|---|---|
| NaN percentage | $$< 2\%$$ | $$2 - 10\%$$ | $$> 10\%$$ |
| Sample count | $$> 300$$ | $$100 - 300$$ | $$< 100$$ |
| MV moves per MV | $$\geq 6$$ | $$3 - 5$$ | $$< 3$$ |
| R-squared | $$> 0.80$$ | $$0.50 - 0.80$$ | $$< 0.50$$ |
| Gain matrix $$\kappa$$ | $$< 20$$ | $$20 - 100$$ | $$> 100$$ |
| Ljung-Box p-value | $$> 0.05$$ | -- | $$\leq 0.05$$ |


---

## 8. Curve Operations

### 8.1 Overview

After identification, the step response curves may need manual adjustments
to incorporate engineering knowledge, correct known biases, or create
synthetic models for channels that could not be identified from data. Curve
operations modify the cumulative step response $$S(k)$$ for $$k = 0, 1, \ldots, n-1$$.

All operations are defined on a single channel's step response vector
$$S \in \mathbb{R}^n$$. The impulse (FIR) response is:

$$
g_k = S_k - S_{k-1}, \quad g_0 = S_0
$$

Operations that modify the dynamics (FIRSTORDER, SECONDORDER, LEADLAG,
CONVOLUTE) work on the FIR coefficients and rebuild the step response:

$$
S_k^{\text{new}} = \sum_{i=0}^{k} g_i^{\text{new}}
$$


### 8.2 SHIFT -- Dead-Time Adjustment

$$
S_{\text{new}}(k) = \begin{cases}
0 & k < d \\
S(k - d) & k \geq d
\end{cases}
$$

where $$d$$ is the shift in samples (positive = add delay, negative = remove
delay).

**Negative shift (remove delay):** For $$d < 0$$:

$$
S_{\text{new}}(k) = \begin{cases}
S(k + |d|) & k < n - |d| \\
S(n - 1) & k \geq n - |d|
\end{cases}
$$

The tail is held at the final value to preserve the steady-state gain.

**Use case.** Adjust the identified dead time without re-running identification.
This is common when the dead time was estimated incorrectly due to sampling
effects (the true dead time is between two sample periods).


### 8.3 GAIN -- Gain Multiplier

$$
S_{\text{new}}(k) = \gamma \cdot S(k)
$$

where $$\gamma$$ is the gain multiplier. This scales the entire step response
uniformly, changing both the transient and steady-state values by the same
factor.

**Effect on steady-state gain:** $$K_{\text{new}} = \gamma \cdot K$$

**Use case.** Adjust the gain when the identified value is known to be biased
(e.g., from a different operating point or from process knowledge).


### 8.4 GSCALE -- Gain Scaling to Target

$$
S_{\text{new}}(k) = \frac{K_{\text{target}}}{K} \cdot S(k)
$$

where $$K = S(n-1)$$ is the current steady-state gain and $$K_{\text{target}}$$
is the desired gain.

This preserves the dynamic shape (time constants, dead time) while adjusting
only the magnitude.

**Difference from GAIN.** GSCALE sets the gain to a specific target value;
GAIN multiplies the existing gain by a factor.


### 8.5 RATE -- Convert to Impulse Response

$$
g_k = S_k - S_{k-1}, \quad g_0 = S_0
$$

This converts the step response to the impulse (FIR) response. The output
is the rate of change of the step response, which shows the instantaneous
dynamic response at each time step.

**Use case.** Diagnostic visualization. The FIR coefficients reveal the
timing and magnitude of the initial response, overshoot, and oscillatory
behavior more clearly than the cumulative step response.


### 8.6 RSCALE -- Rate Scaling

$$
g_k^{\text{new}} = f \cdot g_k
$$

$$
S_{\text{new}}(k) = \sum_{i=0}^{k} g_i^{\text{new}} = f \cdot S(k)
$$

Scale the impulse response coefficients by factor $$f$$, then rebuild the
step response.

**Note.** For uniform scaling, RSCALE is equivalent to GAIN. The distinction
is important when RSCALE is applied selectively to a subset of coefficients
(not implemented in the current version, but the infrastructure supports it).


### 8.7 FIRSTORDER -- Apply First-Order Dynamics

This convolves the existing step response with a first-order filter,
effectively slowing down or speeding up the response.

The first-order filter has the discrete-time impulse response:

$$
h_k = \alpha (1 - \alpha)^k, \quad \alpha = \frac{\Delta t}{\tau + \Delta t}
$$

where $$\tau$$ is the filter time constant and $$\Delta t$$ is the sample
period.

**Algorithm:**

1. Convert step response to FIR: $$g_k = S_k - S_{k-1}$$
2. Filter the FIR coefficients:

   $$
   g_k^{\text{filtered}} = \alpha \cdot g_k + (1 - \alpha) \cdot g_{k-1}^{\text{filtered}}
   $$

   with $$g_{-1}^{\text{filtered}} = 0$$.

3. Rebuild the step response: $$S_k^{\text{new}} = \sum_{i=0}^{k} g_i^{\text{filtered}}$$

**Effect.** The filtered step response has the same steady-state gain but
slower dynamics. The effective time constant is approximately $$\tau_{\text{eff}} \approx \tau_{\text{orig}} + \tau$$.

**Use case.** Slow down an identified model that appears too fast due to
noise or unmodeled dynamics.


### 8.8 SECONDORDER -- Apply Second-Order Dynamics

Cascade of two first-order filters with time constants $$\tau_1$$ and $$\tau_2$$:

$$
S^{\text{new}} = \text{FIRSTORDER}(\text{FIRSTORDER}(S, \tau_1), \tau_2)
$$

For **equal time constants** ($$\tau_1 = \tau_2 = \tau$$), the continuous-time
step response of the cascaded system is:

$$
S(t) = K \left(1 - \left(1 + \frac{t}{\tau}\right) e^{-t/\tau}\right)
$$

For **distinct time constants** ($$\tau_1 \neq \tau_2$$):

$$
S(t) = K \left(1 - \frac{\tau_1 e^{-t/\tau_1} - \tau_2 e^{-t/\tau_2}}{\tau_1 - \tau_2}\right)
$$

**Use case.** Create a more sluggish response with S-shaped transient (no
overshoot). Common for modeling heat transfer processes.


### 8.9 LEADLAG -- Lead-Lag Compensation

Applies a lead-lag transfer function:

$$
G_{\text{LL}}(s) = \frac{\tau_{\text{lead}} s + 1}{\tau_{\text{lag}} s + 1}
$$

In discrete time, this is:

$$
g_k^{\text{out}} = b_0 g_k^{\text{in}} + b_1 g_{k-1}^{\text{in}} + a g_{k-1}^{\text{out}}
$$

where:

$$
a = e^{-\Delta t / \tau_{\text{lag}}}
$$

$$
b_0 = \frac{\tau_{\text{lead}}}{\Delta t}(1 - a) + a
$$

$$
b_1 = -\frac{\tau_{\text{lead}}}{\Delta t}(1 - a)
$$

**Effect:**

- $$\tau_{\text{lead}} > \tau_{\text{lag}}$$: Speeds up the response (lead)
- $$\tau_{\text{lead}} < \tau_{\text{lag}}$$: Slows down the response (lag)
- $$\tau_{\text{lead}} = \tau_{\text{lag}}$$: No change (unity transfer function)

**Use case.** Fine-tune the dynamic shape of an identified model. For
example, if the model shows too much lag, a lead-lag with
$$\tau_{\text{lead}} > \tau_{\text{lag}}$$ can compensate.


### 8.10 CONVOLUTE -- Convolution of Two Step Responses

Given two step responses $$S_A$$ and $$S_B$$, the convolution produces a
new step response representing the series connection of the two systems.

**Algorithm:**

1. Convert both to FIR: $$g_A = \text{diff}(S_A)$$, $$g_B = \text{diff}(S_B)$$
2. Convolve the FIR coefficients:

   $$
   g_{\text{conv}}(k) = \sum_{i=0}^{k} g_A(i) \cdot g_B(k - i)
   $$

   (truncated to the original length $$n$$)

3. Rebuild: $$S_{\text{conv}}(k) = \sum_{i=0}^{k} g_{\text{conv}}(i)$$

**Properties:**

- The gain of the convolution is the product of the individual gains:
  $$K_{\text{conv}} = K_A \cdot K_B$$
- The dead time of the convolution is the sum of the individual dead times
- The effective time constants are combined (the convolution of two
  first-order responses is a second-order response)

**Use case.** Model a cascaded system where the dynamics of two sub-systems
are known separately. For example, convolving a valve dynamics model with
a process model to get the total MV-to-CV response.


### 8.11 ROTATE -- Time-Axis Scaling

$$
S_{\text{new}}(k) = S(\lfloor k \cdot f \rfloor)
$$

where $$f = 1 + \theta / 90$$ and $$\theta$$ is the rotation angle in
degrees. The step response is interpolated onto a stretched or compressed
time axis.

- $$\theta > 0$$ (positive rotation): Compress the time axis -- response
  appears faster
- $$\theta < 0$$ (negative rotation): Stretch the time axis -- response
  appears slower

The interpolation uses linear interpolation between sample points, with
the tail value held constant for extrapolation beyond the original length.

**Use case.** Uniform scaling of all time constants and dead time by the
same factor, which is useful when the sample period was incorrectly
specified or when adjusting a model from one operating condition to another
where all dynamics scale uniformly.


### 8.12 Curve Creation Operations

These operations create step response curves from scratch, without
requiring prior identification data.

#### ZERO

$$
S_k = 0, \quad k = 0, 1, \ldots, n-1
$$

A zero-gain model. Used to explicitly indicate that an MV has no effect
on a particular CV.


#### UNITY

$$
S_k = 1, \quad k = 0, 1, \ldots, n-1
$$

A unity-gain, zero-dead-time, instantaneous response. Used as a starting
point for manual model building.


#### FIRSTORDER_CREATE

$$
S_k = K \left(1 - e^{-(k - d) \Delta t / \tau}\right) \quad \text{for } k \geq d
$$

$$
S_k = 0 \quad \text{for } k < d
$$

Creates a first-order-plus-dead-time (FOPTD) step response from
parameters $$(K, \tau, d)$$:

- $$K$$: steady-state gain
- $$\tau$$: time constant (seconds)
- $$d$$: dead time (samples)
- $$\Delta t$$: sample period (seconds)

**Use case.** Create a model from first-principles estimates or from
simple bump-test measurements (gain, time constant, dead time) without
running the full FIR identification.


#### SECONDORDER_CREATE

For distinct time constants $$\tau_1 \neq \tau_2$$:

$$
S_k = K \left(1 - \frac{\tau_1 e^{-(k-d)\Delta t/\tau_1} - \tau_2 e^{-(k-d)\Delta t/\tau_2}}{\tau_1 - \tau_2}\right)
$$

For equal time constants $$\tau_1 = \tau_2 = \tau$$:

$$
S_k = K \left(1 - \left(1 + \frac{(k-d)\Delta t}{\tau}\right) e^{-(k-d)\Delta t/\tau}\right)
$$

Both for $$k \geq d$$; $$S_k = 0$$ for $$k < d$$.

**Use case.** Create a higher-order model that better matches processes
with S-shaped step responses (heat exchangers, distillation trays).


### 8.13 Operation Chaining

Multiple curve operations can be applied in sequence (a "chain"). Each
operation takes the output of the previous one as its input:

$$
S^{(0)} \xrightarrow{\text{op}_1} S^{(1)} \xrightarrow{\text{op}_2} S^{(2)} \xrightarrow{\cdots} S^{(m)}
$$

The chain is recorded as a list of operation records, each containing the
operation type and its parameters. This allows:

- **Reproducibility**: the exact sequence of modifications is logged
- **Undo**: the chain can be truncated to revert to an earlier state
- **Auditability**: process engineers can review what was changed and why

**Example chain:**

1. Start with identified step response
2. SHIFT by 2 samples (add dead time discovered from process knowledge)
3. GSCALE to gain = 1.5 (match steady-state plant test data)
4. FIRSTORDER with $$\tau = 30$$ s (add unmodeled mixing dynamics)

The final model incorporates both data-driven identification and
engineering knowledge.


---

## Appendix A: Mathematical Proofs and Derivations

### A.1 Derivation of the DLS Normal Equations

Starting from the objective:

$$
J(\theta) = \| Y - \Phi \theta \|_F^2 = \text{tr}\left[(Y - \Phi\theta)^T(Y - \Phi\theta)\right]
$$

Expanding:

$$
J = \text{tr}(Y^T Y) - 2\text{tr}(Y^T \Phi \theta) + \text{tr}(\theta^T \Phi^T \Phi \theta)
$$

Setting the matrix derivative to zero:

$$
\frac{\partial J}{\partial \theta} = -2 \Phi^T Y + 2 \Phi^T \Phi \theta = 0
$$

Solving:

$$
\Phi^T \Phi \theta = \Phi^T Y
$$

$$
\theta = (\Phi^T \Phi)^{-1} \Phi^T Y
$$


### A.2 Derivation of the Ridge Estimator

The regularized objective:

$$
J_\alpha(\theta) = \| Y - \Phi \theta \|_F^2 + \alpha \| \theta \|_F^2
$$

$$
= \text{tr}(Y^T Y) - 2\text{tr}(Y^T \Phi \theta) + \text{tr}(\theta^T \Phi^T \Phi \theta) + \alpha \text{tr}(\theta^T \theta)
$$

Setting the derivative to zero:

$$
\frac{\partial J_\alpha}{\partial \theta} = -2\Phi^T Y + 2(\Phi^T \Phi + \alpha I)\theta = 0
$$

$$
\theta_\alpha = (\Phi^T \Phi + \alpha I)^{-1} \Phi^T Y
$$


### A.3 Bias of the Ridge Estimator

The expected value of the Ridge estimator:

$$
\mathbb{E}[\hat{\theta}_\alpha] = (\Phi^T \Phi + \alpha I)^{-1} \Phi^T \Phi \, \theta_{\text{true}}
$$

The bias is:

$$
\text{Bias} = \mathbb{E}[\hat{\theta}_\alpha] - \theta_{\text{true}} = -\alpha (\Phi^T \Phi + \alpha I)^{-1} \theta_{\text{true}}
$$

The bias is proportional to $$\alpha$$ and in the direction of $$-\theta_{\text{true}}$$
(shrinkage toward zero).


### A.4 Covariance of the Ridge Estimator

$$
\text{Cov}(\hat{\theta}_\alpha) = \sigma^2 (\Phi^T \Phi + \alpha I)^{-1} \Phi^T \Phi (\Phi^T \Phi + \alpha I)^{-1}
$$

For $$\alpha > 0$$, this is always smaller (in the positive semi-definite
sense) than the DLS covariance $$\sigma^2 (\Phi^T \Phi)^{-1}$$.


### A.5 Observability Matrix Structure

The extended observability matrix of the system $$(A, C)$$ with horizon $$f$$ is:

$$
\Gamma_f = \begin{bmatrix} C \\ CA \\ CA^2 \\ \vdots \\ CA^{f-1} \end{bmatrix}
\in \mathbb{R}^{(f \cdot n_y) \times n_x}
$$

The key property exploited by subspace identification is the **shift structure**:

$$
\Gamma_f^{\downarrow} = \Gamma_f^{\uparrow} A
$$

where $$\Gamma_f^{\downarrow}$$ removes the first $$n_y$$ rows and
$$\Gamma_f^{\uparrow}$$ removes the last $$n_y$$ rows.

This allows $$A$$ to be extracted from the observability matrix without
knowing it a priori:

$$
A = (\Gamma_f^{\uparrow})^{\dagger} \Gamma_f^{\downarrow}
$$


### A.6 Why the Oblique Projection Recovers the State Sequence

The fundamental subspace identity (Van Overschee & De Moor, 1996) states that
for the true system:

$$
Y_f = \Gamma_f X_f + H_f^d U_f + H_f^s E_f
$$

where $$X_f$$ is the state sequence at the boundary between past and future,
$$H_f^d$$ is the deterministic block-Toeplitz input-to-output matrix, and
$$H_f^s$$ is the stochastic block-Toeplitz noise-to-output matrix.

The oblique projection $$Y_f /_{U_f} W_p$$:

1. Removes the $$H_f^d U_f$$ term (by projecting along $$U_f$$)
2. Recovers $$\Gamma_f X_f$$ (because $$X_f$$ is a function of past data $$W_p$$)
3. The noise term $$H_f^s E_f$$ becomes small as $$N_c \to \infty$$

Therefore:

$$
Y_f /_{U_f} W_p \approx \Gamma_f X_f
$$

and the SVD of this product reveals the column space of $$\Gamma_f$$ and the
row space of $$X_f$$.


---

## Appendix B: Practical Guidelines for Process Engineers

### B.1 Choosing an Identification Method

| Situation | Recommended Method |
|---|---|
| Open-loop step test, SISO or small MIMO | FIR (DLS) |
| Open-loop, collinear or short test | FIR (Ridge) |
| Closed-loop, setpoints varied | Closed-loop IV or FIR (COR) |
| Closed-loop, no setpoint data | Closed-loop regularized direct |
| Large MIMO (> 10 CVs) | Subspace (N4SID) with CV grouping |
| Need to enforce gain signs/dead times | Constrained FIR |
| Quick estimate from bump test | FIRSTORDER_CREATE or SECONDORDER_CREATE |

### B.2 Step Test Design

For reliable identification:

1. **Duration**: At least 2x the longest settling time of the system
2. **Number of moves**: At least 3 up-and-down moves per MV (6+ is ideal)
3. **Move size**: At least 3x the noise standard deviation of the CV
4. **Move timing**: Randomize the timing to avoid periodic correlation
5. **MV independence**: Move MVs at different times to avoid collinearity
6. **Steady-state periods**: Include quiet periods between moves for
   noise estimation

### B.3 Troubleshooting Poor Models

| Symptom | Likely Cause | Fix |
|---|---|---|
| High condition number | Collinear MVs or short test | Ridge; extend test |
| Low R-squared | Noise, missing DV, or nonlinearity | Check data; add DVs; try subspace |
| Non-white residuals | Model too short or missing dynamics | Increase $$n$$; try subspace |
| Wrong gain sign | Closed-loop bias or collinearity | Use COR method; add constraints |
| Oscillatory step response | Noise or interaction artifact | Smooth; check cross-correlation |
| Very noisy FIR tail | Insufficient data or too many coefficients | Reduce $$n$$; increase smoothing |

### B.4 Model Length Selection

The model length $$n$$ (in sample periods) should be:

$$
n \approx 1.5 \times \frac{t_{95\%}}{\Delta t}
$$

where $$t_{95\%}$$ is the 95% settling time of the slowest channel and
$$\Delta t$$ is the sample period.

| Process Type | Typical $$t_{95\%}$$ | Typical $$n$$ (at 1-min sampling) |
|---|---|---|
| Flow control | 1-5 min | 3-10 |
| Pressure control | 5-15 min | 10-25 |
| Temperature control | 15-60 min | 25-90 |
| Composition control | 30-120 min | 50-180 |
| Distillation column | 60-300 min | 90-450 |


---

## Appendix C: References

1. **Ljung, L.** (1999). *System Identification: Theory for the User*,
   2nd ed. Prentice Hall. -- The definitive textbook on system identification.

2. **Van Overschee, P. and De Moor, B.** (1996). *Subspace Identification
   for Linear Systems*. Kluwer Academic. -- Comprehensive treatment of
   N4SID, MOESP, and CVA algorithms.

3. **Verhaegen, M. and Dewilde, P.** (1992). "Subspace model identification,
   Part 1: The output-error state-space model identification class of
   algorithms." *Int. J. Control*, 56(5):1187-1210.

4. **Larimore, W.E.** (1990). "Canonical variate analysis in identification,
   filtering, and adaptive control." *Proc. 29th IEEE CDC*, pp. 596-604.

5. **Qin, S.J.** (2006). "An overview of subspace identification."
   *Computers & Chemical Engineering*, 30(10-12):1502-1513.

6. **Qin, S.J. and Badgwell, T.A.** (2003). "A survey of industrial model
   predictive control technology." *Control Engineering Practice*, 11:733-764.

7. **Cutler, C.R. and Ramaker, B.L.** (1980). "Dynamic matrix control -- a
   computer control algorithm." *Proc. Joint Automatic Control Conference*.

8. **Bristol, E.H.** (1966). "On a new measure of interaction for
   multivariable process control." *IEEE Trans. Automatic Control*,
   11(1):133-134.

9. **Rhinehart, R.R.** (2013). "Automated steady and transient state
   identification in noisy processes." *Proc. American Control Conference*.

10. **Box, G.E.P. and Cox, D.R.** (1964). "An analysis of transformations."
    *J. Royal Statistical Society, Series B*, 26(2):211-252.

11. **Savitzky, A. and Golay, M.J.E.** (1964). "Smoothing and differentiation
    of data by simplified least squares procedures." *Analytical Chemistry*,
    36(8):1627-1639.

12. **Ljung, G.M. and Box, G.E.P.** (1978). "On a measure of lack of fit in
    time series models." *Biometrika*, 65(2):297-303.

13. **Tikhonov, A.N.** (1963). "Solution of incorrectly formulated problems
    and the regularization method." *Soviet Mathematics*, 4:1035-1038.

14. **Rawlings, J.B., Mayne, D.Q., and Diehl, M.** (2017). *Model Predictive
    Control: Theory, Computation, and Design*, 2nd ed. Nob Hill Publishing.

15. **Van den Hof, P.M.J. and Schrama, R.J.P.** (1995). "Identification and
    control -- closed-loop issues." *Automatica*, 31(12):1751-1770.

16. **Kuntz, S. and Rawlings, J.B.** (2024). *Subspace Methods for
    Closed-Loop System Identification*. Lecture Notes.


---

## Appendix D: Worked Examples

### D.1 SISO First-Order-Plus-Dead-Time Identification

**Problem.** A temperature sensor (CV) responds to a cooling valve position
(MV) with an approximate first-order-plus-dead-time dynamic:

$$
G(s) = \frac{-2.5 \, e^{-3s}}{30s + 1}
$$

at a sample period $$\Delta t = 1$$ minute. The engineer has 500 samples
of step-test data with measurement noise $$\sigma = 0.3$$ degrees C.

**Step 1: Choose parameters.**

- Model length: $$n = 1.5 \times 95\% \text{ settling time} / \Delta t = 1.5 \times (3 + 3 \times 30) / 1 = 1.5 \times 93 \approx 140$$.

  Since the data is only 500 samples, use $$n = 90$$ to maintain adequate
  regression conditioning ($$N - n + 1 = 411$$ rows vs. $$n = 90$$ columns).

- Method: DLS (open-loop data).

- Smoothing: Pipeline (exponential + Savitzky-Golay + asymptotic).

**Step 2: Build the regression.**

The Toeplitz matrix $$\Phi \in \mathbb{R}^{411 \times 90}$$ is constructed
from the MV data. Each row contains 90 consecutive MV values in reverse order.

**Step 3: Solve and check diagnostics.**

- Condition number: $$\kappa(\Phi) = 45$$ -- well-conditioned.
- R-squared: $$R^2 = 0.91$$ -- good fit.
- Ljung-Box p-value: 0.23 -- residuals are white.
- Identified gain: $$K = -2.48$$ (true: $$-2.5$$, error: 0.8%).
- Identified dead time: 3 samples (matches exactly).

**Step 4: Smoothing.**

The raw FIR shows random fluctuations in the tail ($$k > 60$$). After
pipeline smoothing:

- Exponential decay forces the tail toward zero
- Savitzky-Golay removes sample-to-sample jitter
- Asymptotic projection ensures the last coefficients are exactly zero

The smoothed step response closely matches the theoretical FOPTD curve.


### D.2 2x2 MIMO Wood-Berry Distillation Column

**Problem.** The Wood-Berry binary distillation column has the transfer
function matrix:

$$
G(s) = \begin{bmatrix}
\frac{12.8 \, e^{-s}}{16.7s + 1} & \frac{-18.9 \, e^{-3s}}{21.0s + 1} \\
\frac{6.6 \, e^{-7s}}{10.9s + 1} & \frac{-19.4 \, e^{-3s}}{14.4s + 1}
\end{bmatrix}
$$

with inputs (reflux flow, steam flow) and outputs (overhead composition,
bottoms composition).

**Identification setup:**

- Sample period: $$\Delta t = 1$$ min
- Model length: $$n = 120$$ (2 hours, adequate for the slowest channel
  with $$\tau = 21$$ min and $$d = 7$$ min)
- Data: 1000 samples with both MVs stepped independently
- Method: DLS

**Gain matrix comparison:**

|  | True | Identified | Error |
|---|---|---|---|
| $$K_{11}$$ | 12.80 | 12.65 | 1.2% |
| $$K_{12}$$ | -18.90 | -18.72 | 1.0% |
| $$K_{21}$$ | 6.60 | 6.78 | 2.7% |
| $$K_{22}$$ | -19.40 | -19.15 | 1.3% |

**Cross-correlation check.** If the two MVs were stepped at the same time,
the cross-correlation would be high and the identified gains unreliable.
In this example, the MVs were stepped independently, giving a peak
cross-correlation of 0.15 (IDEAL grade).

**RGA analysis:**

$$
\Lambda = \begin{bmatrix} 2.01 & -1.01 \\ -1.01 & 2.01 \end{bmatrix}
$$

The RGA diagonal elements greater than 1 indicate significant interaction.
The negative off-diagonal elements indicate that the cross-coupling partially
counteracts the direct effects.


### D.3 Constrained Identification Example

**Problem.** Identifying a heat exchanger model where the engineer knows:

1. Increasing hot-oil flow (MV1) must increase outlet temperature (CV1):
   $$K_{11} > 0$$
2. The dead time from MV1 to CV1 is at least 2 minutes ($$d \geq 2$$)
3. The gain ratio between MV1 and MV2 effects on CV1 is approximately 3:1

**Setup:**

```
constraints = [
    GainConstraint(cv=0, mv=0, sign="positive"),
    DeadTimeConstraint(cv=0, mv=0, min_samples=2),
    GainRatioConstraint(cv=0, mv_num=0, mv_den=1, ratio=3.0, tol=0.3),
]
```

**Result.** The constrained identification produces a model where:

- $$K_{11} = 1.85 > 0$$ (positive, as required)
- First two FIR coefficients are exactly zero (dead time enforced)
- $$K_{11} / K_{12} = 2.87$$ (within the $$3.0 \pm 0.3$$ tolerance)

The unconstrained DLS on the same data gave $$K_{11} = -0.12$$ (wrong sign)
due to collinear inputs and high noise. The constrained solution incorporates
engineering knowledge to produce a physically meaningful model.


---

## Appendix E: Glossary

| Term | Definition |
|---|---|
| **APC** | Advanced Process Control -- the umbrella term for multivariable control technologies in the process industries |
| **ARX** | AutoRegressive with eXogenous input -- a parametric model structure: $$A(q)y(k) = B(q)u(k) + e(k)$$ |
| **Bias update** | The correction applied at each controller cycle to account for unmeasured disturbances and model mismatch |
| **Block-Hankel matrix** | A matrix with a Hankel (constant anti-diagonal) structure where each element is a block (vector or matrix) |
| **Canonical correlation** | A measure of the linear relationship between two sets of variables, found by CVA |
| **Condition number** | The ratio of the largest to smallest singular value of a matrix; measures sensitivity to perturbation |
| **CV** | Controlled Variable -- a process measurement that the controller tries to maintain at or near a target |
| **DARE** | Discrete Algebraic Riccati Equation -- used to compute optimal Kalman and LQR gains |
| **Dead time** | The time delay between an input change and the first measurable output response |
| **DMC** | Dynamic Matrix Control -- the original MPC algorithm using step response models (Cutler & Ramaker, 1980) |
| **DV** | Disturbance Variable -- a measured but uncontrollable process input (e.g., ambient temperature) |
| **FIR** | Finite Impulse Response -- a model where the output depends on a finite number of past inputs |
| **FOPTD** | First-Order Plus Dead Time -- the simplest parametric process model: $$G(s) = Ke^{-ds}/(\tau s + 1)$$ |
| **Frobenius norm** | The square root of the sum of squared elements of a matrix: $$\|A\|_F = \sqrt{\sum_{ij} a_{ij}^2}$$ |
| **Gain matrix** | The steady-state input-output relationship: $$\Delta y_{\text{ss}} = K \Delta u$$ |
| **Hankel matrix** | A matrix where each ascending skew-diagonal is constant |
| **Historian** | Industrial database that stores time-series process data (e.g., OSIsoft PI, Honeywell PHD) |
| **Innovation** | The one-step-ahead prediction error: $$e(k) = y(k) - \hat{y}(k|k-1)$$ |
| **Instrumental variable** | A variable correlated with the regressor but uncorrelated with the noise, used to obtain consistent estimates |
| **Kalman gain** | The optimal weighting for updating state estimates based on new measurements |
| **Markov parameter** | The impulse response coefficient at a specific lag; the matrix $$g_k = CA^{k-1}B$$ for $$k \geq 1$$ |
| **MIMO** | Multiple-Input Multiple-Output |
| **MISO** | Multiple-Input Single-Output |
| **Model horizon** | The number of step response coefficients ($$n$$) used to represent the process dynamics |
| **MPC** | Model Predictive Control |
| **MV** | Manipulated Variable -- a process input that the controller can adjust (e.g., valve position, setpoint) |
| **Normal equations** | The system $$\Phi^T\Phi\theta = \Phi^TY$$ whose solution gives the least-squares estimate |
| **Observability matrix** | The matrix $$\Gamma = [C; CA; CA^2; \ldots]$$ whose rank determines whether all states can be reconstructed from outputs |
| **Persistent excitation** | A condition on the input signal ensuring that the regression matrix has full rank |
| **Pseudoinverse** | The Moore-Penrose generalized inverse $$A^{\dagger}$$, satisfying $$AA^{\dagger}A = A$$ |
| **QP** | Quadratic Program -- an optimization problem with a quadratic objective and linear constraints |
| **RGA** | Relative Gain Array -- a measure of process interaction (Bristol, 1966) |
| **Ridge regression** | Least squares with an L2 penalty on the parameters: $$\min \|Y - \Phi\theta\|^2 + \alpha\|\theta\|^2$$ |
| **Settling time** | The time for the step response to reach and stay within a specified percentage of its final value |
| **SISO** | Single-Input Single-Output |
| **SNR** | Signal-to-Noise Ratio, typically expressed in decibels |
| **SSD** | Steady-State Detection |
| **Step response** | The output trajectory when a unit step input is applied, starting from zero initial conditions |
| **Subspace identification** | A family of algorithms (N4SID, MOESP, CVA) that identify state-space models from data using SVD of projected Hankel matrices |
| **SVD** | Singular Value Decomposition: $$A = U\Sigma V^T$$ |
| **Tikhonov regularization** | Addition of a penalty $$\alpha\|\theta\|^2$$ to the least-squares objective to improve conditioning |
| **Toeplitz matrix** | A matrix where each descending diagonal is constant; the regression matrix in FIR identification has block-Toeplitz structure |
| **White noise** | A random process with zero mean, constant variance, and zero autocorrelation at all non-zero lags |


---

*Document version 1.0. Generated for the Azeotrope APC identification suite.*
*Last updated: 2026-04-11.*
