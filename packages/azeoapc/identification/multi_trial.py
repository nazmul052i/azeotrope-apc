"""Multiple identification trials per case.

Run FIR (or subspace) identification with different parameter sets
(TTSS / n_coeff, smoothing, method, ridge alpha) and compare results
side-by-side to pick the best.

Usage::

    trials = define_trials(base_config, vary={
        "n_coeff": [40, 60, 80, 120],
        "smooth":  ["pipeline", "exponential", "none"],
    })
    results = run_trials(u, y, trials)
    best = select_best_trial(results)
"""
from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrialConfig:
    """One trial's configuration (a variant of the base config)."""
    name: str
    params: Dict[str, Any]   # override keys applied to base config


@dataclass
class TrialResult:
    """Result of one trial run."""
    name: str
    config: Any           # the full IdentConfig used
    ident_result: Any     # IdentResult from FIR or SubspaceResult
    fit_r2: np.ndarray    # per-CV R²
    fit_rmse: np.ndarray  # per-CV RMSE
    mean_r2: float = 0.0
    mean_rmse: float = 0.0


@dataclass
class TrialComparison:
    """Side-by-side comparison of all trials."""
    trials: List[TrialResult] = field(default_factory=list)
    best_trial: Optional[str] = None
    best_metric: str = "r2"

    def summary(self) -> str:
        lines = [f"Trial Comparison ({len(self.trials)} trials, best by {self.best_metric})"]
        lines.append(f"  {'Trial':<25s}  {'Mean R²':>8s}  {'Mean RMSE':>10s}")
        lines.append(f"  {'-'*25}  {'-'*8}  {'-'*10}")
        for t in sorted(self.trials, key=lambda x: x.mean_r2, reverse=True):
            marker = " *" if t.name == self.best_trial else ""
            lines.append(
                f"  {t.name:<25s}  {t.mean_r2:>8.4f}  {t.mean_rmse:>10.4f}{marker}")
        return "\n".join(lines)


def define_trials(
    base_params: Dict[str, Any],
    vary: Dict[str, List[Any]],
) -> List[TrialConfig]:
    """Generate trial configs from a base config and parameter variations.

    Creates the Cartesian product of all varied parameters.

    Parameters
    ----------
    base_params : dict
        Base configuration parameters.
    vary : dict
        Keys to vary, each mapping to a list of values to try.

    Returns
    -------
    list[TrialConfig]
        One TrialConfig per combination.
    """
    keys = list(vary.keys())
    value_lists = [vary[k] for k in keys]
    trials = []

    for combo in product(*value_lists):
        params = dict(base_params)
        name_parts = []
        for k, v in zip(keys, combo):
            params[k] = v
            name_parts.append(f"{k}={v}")
        name = ", ".join(name_parts)
        trials.append(TrialConfig(name=name, params=params))

    return trials


def run_trials_fir(
    u: np.ndarray,
    y: np.ndarray,
    trials: List[TrialConfig],
) -> TrialComparison:
    """Run FIR identification for each trial configuration.

    Parameters
    ----------
    u : ndarray (N, nu)
        Input data.
    y : ndarray (N, ny)
        Output data.
    trials : list[TrialConfig]
        Trial configurations to run.

    Returns
    -------
    TrialComparison
    """
    from .fir_ident import FIRIdentifier, IdentConfig, IdentMethod, SmoothMethod

    comparison = TrialComparison()

    for trial in trials:
        try:
            params = dict(trial.params)
            # Coerce string values to enums
            if "method" in params and isinstance(params["method"], str):
                params["method"] = IdentMethod(params["method"])
            if "smooth" in params and isinstance(params["smooth"], str):
                params["smooth"] = SmoothMethod(params["smooth"])
            cfg = IdentConfig(**params)
            ident = FIRIdentifier(cfg)
            result = ident.identify(u, y)

            fit_r2 = np.array([ch.r_squared for ch in result.fits])
            fit_rmse = np.array([ch.rmse for ch in result.fits])

            tr = TrialResult(
                name=trial.name,
                config=cfg,
                ident_result=result,
                fit_r2=fit_r2,
                fit_rmse=fit_rmse,
                mean_r2=float(np.mean(fit_r2)),
                mean_rmse=float(np.mean(fit_rmse)),
            )
            comparison.trials.append(tr)
        except Exception as e:
            logger.warning("Trial '%s' failed: %s", trial.name, e)

    # Select best
    if comparison.trials:
        best = max(comparison.trials, key=lambda t: t.mean_r2)
        comparison.best_trial = best.name
        comparison.best_metric = "r2"

    return comparison


def select_best_trial(
    comparison: TrialComparison,
    metric: str = "r2",
) -> Optional[TrialResult]:
    """Select the best trial by metric."""
    if not comparison.trials:
        return None
    if metric == "r2":
        return max(comparison.trials, key=lambda t: t.mean_r2)
    elif metric == "rmse":
        return min(comparison.trials, key=lambda t: t.mean_rmse)
    return comparison.trials[0]
