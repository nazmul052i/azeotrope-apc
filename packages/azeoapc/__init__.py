"""Azeotrope APC -- shared Python library.

This package contains the engine code that all the apps depend on:

  azeoapc.models       -- variable definitions, plant models, YAML config loader
  azeoapc.calculations -- user Python script runner (input/output calcs)
  azeoapc.sim_engine   -- per-cycle plant + MPC orchestrator
  azeoapc.layer3_nlp   -- nonlinear RTO (Layer 3) wrapping CasADi/IPOPT
  azeoapc.deployment   -- IO tags, OPC UA client/server, runtime cycle loop

Apps that consume this package:

  apc_architect -- the configuration / tuning / simulation studio
  apc_ident     -- step-test model identification (Phase C)
  apc_runtime   -- headless production controller cycle loop (Phase D)
  apc_historian -- timeseries store (Phase E)
  apc_manager   -- operator console + REST surface (Phase F)
"""

__version__ = "0.1.0"
