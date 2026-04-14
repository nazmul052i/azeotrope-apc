"""CV grouping for subspace identification.

Large MIMO systems (20+ CVs) can't be identified in one shot -- the
Hankel matrices become too large and the model order explodes.  CV
grouping splits the problem into smaller sub-problems:

1. **auto** -- group CVs by cross-correlation (correlated CVs share
   dynamics so they should be identified together)
2. **one_per_group** -- each CV in its own group (MISO decomposition,
   like FIR but with subspace)
3. **all_in_one** -- all CVs in one group (full MIMO, original behavior)

After identification, the per-group state-space models are assembled
into a block-diagonal system.

Usage::

    groups = auto_group_cvs(y, cv_names, max_group_size=6)
    results = identify_grouped(u, y, groups, config)
    combined = combine_grouped_results(results)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

logger = logging.getLogger(__name__)


@dataclass
class CVGroup:
    """A group of CVs to identify together."""
    name: str
    cv_indices: List[int]
    cv_names: List[str] = field(default_factory=list)


def auto_group_cvs(
    y: np.ndarray,
    cv_names: Optional[List[str]] = None,
    max_group_size: int = 6,
    correlation_threshold: float = 0.5,
) -> List[CVGroup]:
    """Auto-group CVs by cross-correlation.

    CVs with high pairwise correlation share dynamics and should be
    identified together.  Uses agglomerative clustering on the
    absolute correlation matrix.

    Parameters
    ----------
    y : ndarray (N, ny)
        Output data.
    cv_names : list[str], optional
        CV names for labeling.
    max_group_size : int
        Maximum CVs per group.
    correlation_threshold : float
        Correlation above which CVs are grouped (0-1).
    """
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    if y.shape[0] < y.shape[1]:
        y = y.T

    ny = y.shape[1]
    if cv_names is None:
        cv_names = [f"CV{i}" for i in range(ny)]

    if ny <= max_group_size:
        return [CVGroup(name="all", cv_indices=list(range(ny)),
                        cv_names=list(cv_names))]

    # Compute correlation matrix
    corr = np.corrcoef(y.T)
    corr = np.nan_to_num(corr, nan=0.0)

    # Distance = 1 - |correlation|
    dist = 1.0 - np.abs(corr)
    np.fill_diagonal(dist, 0.0)

    # Condensed distance for scipy
    from scipy.spatial.distance import squareform
    dist_condensed = squareform(dist, checks=False)

    # Agglomerative clustering
    Z = linkage(dist_condensed, method="average")
    labels = fcluster(Z, t=1.0 - correlation_threshold, criterion="distance")

    # Build groups
    group_map: Dict[int, List[int]] = {}
    for i, label in enumerate(labels):
        group_map.setdefault(int(label), []).append(i)

    # Split oversized groups
    groups: List[CVGroup] = []
    for gid, indices in sorted(group_map.items()):
        while len(indices) > max_group_size:
            chunk = indices[:max_group_size]
            indices = indices[max_group_size:]
            groups.append(CVGroup(
                name=f"group_{len(groups)+1}",
                cv_indices=chunk,
                cv_names=[cv_names[i] for i in chunk],
            ))
        if indices:
            groups.append(CVGroup(
                name=f"group_{len(groups)+1}",
                cv_indices=indices,
                cv_names=[cv_names[i] for i in indices],
            ))

    logger.info("CV grouping: %d CVs -> %d groups: %s",
                ny, len(groups),
                [(g.name, len(g.cv_indices)) for g in groups])
    return groups


def one_per_group(
    ny: int,
    cv_names: Optional[List[str]] = None,
) -> List[CVGroup]:
    """One CV per group (MISO decomposition)."""
    if cv_names is None:
        cv_names = [f"CV{i}" for i in range(ny)]
    return [
        CVGroup(name=cv_names[i], cv_indices=[i], cv_names=[cv_names[i]])
        for i in range(ny)
    ]


def all_in_one_group(
    ny: int,
    cv_names: Optional[List[str]] = None,
) -> List[CVGroup]:
    """All CVs in one group (full MIMO)."""
    if cv_names is None:
        cv_names = [f"CV{i}" for i in range(ny)]
    return [CVGroup(name="all", cv_indices=list(range(ny)),
                    cv_names=list(cv_names))]


def identify_grouped(
    u: np.ndarray,
    y: np.ndarray,
    groups: List[CVGroup],
    config,
) -> List:
    """Run subspace identification for each CV group.

    Parameters
    ----------
    u : ndarray (N, nu)
    y : ndarray (N, ny)
    groups : list of CVGroup
    config : SubspaceConfig

    Returns
    -------
    list of SubspaceResult, one per group
    """
    from .subspace_ident import SubspaceIdentifier, SubspaceConfig

    results = []
    for group in groups:
        y_group = y[:, group.cv_indices]
        logger.info("Identifying group '%s': %d CVs (%s)",
                     group.name, len(group.cv_indices), group.cv_names)

        # Cap model order for this group
        group_cfg = SubspaceConfig(
            method=config.method,
            nx=config.nx,
            nx_max=min(config.max_states_per_cv_group, config.nx_max),
            f=config.f,
            p=config.p,
            dt=config.dt,
            estimate_K=config.estimate_K,
            force_stability=config.force_stability,
            force_zero_D=config.force_zero_D,
            sv_threshold=config.sv_threshold,
            detrend=config.detrend,
            remove_mean=config.remove_mean,
            differencing=config.differencing,
            double_diff=config.double_diff,
            oversampling_ratio=config.oversampling_ratio,
        )

        ident = SubspaceIdentifier(group_cfg)
        try:
            result = ident.identify(u, y_group)
            results.append(result)
        except Exception as e:
            logger.error("Group '%s' failed: %s", group.name, e)
            results.append(None)

    return results


def combine_grouped_results(
    groups: List[CVGroup],
    results: List,
    ny_total: int,
    nu: int,
    dt: float = 1.0,
    n_step: int = 120,
) -> dict:
    """Combine per-group results into a single block-diagonal model.

    Returns a dict with combined A, B, C, D, step response, gain matrix,
    and per-CV fit metrics.
    """
    # Compute step responses per group and assemble into full matrix
    step_full = [np.zeros((ny_total, nu)) for _ in range(n_step)]
    gain_full = np.zeros((ny_total, nu))
    fit_r2 = np.zeros(ny_total)
    fit_rmse = np.zeros(ny_total)

    # Block-diagonal state-space
    A_blocks = []
    B_blocks = []
    C_rows = []
    D_rows = []

    for group, result in zip(groups, results):
        if result is None:
            # Failed group -- zero gain
            for ci in group.cv_indices:
                C_rows.append(np.zeros((1, 0)))
                D_rows.append(np.zeros((1, nu)))
            continue

        # Step response
        group_step = result.to_step(n_step)
        for k in range(n_step):
            for gi, ci in enumerate(group.cv_indices):
                step_full[k][ci, :] = group_step[k][gi, :]

        # Gain
        group_gain = result.gain_matrix()
        for gi, ci in enumerate(group.cv_indices):
            gain_full[ci, :] = group_gain[gi, :]

        # Fit metrics
        for gi, ci in enumerate(group.cv_indices):
            if gi < len(result.fit_r2):
                fit_r2[ci] = result.fit_r2[gi]
                fit_rmse[ci] = result.fit_rmse[gi]

        # Block-diagonal SS
        A_blocks.append(result.A)
        B_blocks.append(result.B)

        ny_g = len(group.cv_indices)
        C_rows.append(result.C)
        D_rows.append(result.D)

    # Assemble block-diagonal A, B
    if A_blocks:
        from scipy.linalg import block_diag
        A_combined = block_diag(*A_blocks)
        B_combined = np.vstack(B_blocks) if B_blocks else np.zeros((0, nu))

        # C: need to map each group's C to the right state block
        nx_total = A_combined.shape[0]
        C_combined = np.zeros((ny_total, nx_total))
        D_combined = np.zeros((ny_total, nu))

        nx_offset = 0
        for group, result in zip(groups, results):
            if result is None:
                continue
            nx_g = result.A.shape[0]
            for gi, ci in enumerate(group.cv_indices):
                C_combined[ci, nx_offset:nx_offset + nx_g] = result.C[gi, :]
                D_combined[ci, :] = result.D[gi, :]
            nx_offset += nx_g
    else:
        A_combined = np.zeros((0, 0))
        B_combined = np.zeros((0, nu))
        C_combined = np.zeros((ny_total, 0))
        D_combined = np.zeros((ny_total, nu))

    return {
        "A": A_combined,
        "B": B_combined,
        "C": C_combined,
        "D": D_combined,
        "step": step_full,
        "gain_matrix": gain_full,
        "fit_r2": fit_r2,
        "fit_rmse": fit_rmse,
        "groups": groups,
        "n_groups": len(groups),
        "nx_total": A_combined.shape[0],
    }
