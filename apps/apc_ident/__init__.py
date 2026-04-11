"""APC Ident -- step-test model identification studio.

Mirrors the AspenTech DMC3 Model ID workflow as a standalone Python app.
Tabs follow the natural identification workflow:

  1. Data            -- load CSV/parquet, view trends, mark segments
  2. Tags            -- bind columns to controller MV/CV/DV roles
  3. Identification  -- pick method/n_coeff/smoothing/holdout, run
  4. Results         -- step response matrix, gain matrix, export bundle
  5. Validation      -- hold-out simulation, R^2/RMSE per CV

Output: a .apcmodel HDF5 bundle that apc_architect consumes via
``model: { type: bundle, source: ... }`` in its YAML config.
"""
