"""
batch_execution.py -- Batch case execution for MISO identification.

Supports running multiple identification cases (MISO decomposition)
sequentially, as used in DMC3-style model identification workflows.

The typical workflow:
    1. Define the full set of MVs and CVs.
    2. Decompose into one MISO case per CV (all MVs -> one CV).
    3. Run all cases and collect results.
    4. Report success/failure, timings, and diagnostics.

Usage::

    cases = generate_miso_cases(mv_cols, cv_cols, base_config)
    report = run_batch(cases, u_data, y_data)
    print(f"{report.n_success}/{len(report.cases)} cases succeeded")

Author : Azeotrope Process Control
License: Proprietary
"""
from __future__ import annotations

import logging
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from .fir_ident import FIRIdentifier, IdentConfig, IdentResult

logger = logging.getLogger(__name__)

Mat = NDArray[np.float64]


# =====================================================================
#  Data classes
# =====================================================================

@dataclass
class BatchCase:
    """A single identification case (typically one MISO sub-problem).

    Parameters
    ----------
    name : str
        Human-readable name for the case (e.g. ``"CV_ReactorTemp"``).
    mv_cols : List[str]
        Column names for the manipulated variables (inputs).
    cv_cols : List[str]
        Column names for the controlled variables (outputs).
        For MISO decomposition this is typically a single CV.
    config : IdentConfig
        Identification configuration for this case.
    """
    name: str
    mv_cols: List[str]
    cv_cols: List[str]
    config: IdentConfig


@dataclass
class BatchCaseResult:
    """Result of running a single batch case.

    Parameters
    ----------
    name : str
        Case name (mirrors ``BatchCase.name``).
    case : BatchCase
        The case definition that was executed.
    ident_result : Any
        The identification result object (``IdentResult`` or
        ``SubspaceResult``), or ``None`` if the case failed.
    elapsed_ms : float
        Wall-clock time for this case in milliseconds.
    success : bool
        Whether the case completed without error.
    error : str
        Error message if the case failed, empty string otherwise.
    """
    name: str
    case: BatchCase
    ident_result: Any = None
    elapsed_ms: float = 0.0
    success: bool = True
    error: str = ""


@dataclass
class BatchReport:
    """Aggregated report from running a full batch.

    Parameters
    ----------
    cases : List[BatchCaseResult]
        Individual case results, in execution order.
    total_elapsed_ms : float
        Total wall-clock time for the entire batch in milliseconds.
    n_success : int
        Number of cases that completed successfully.
    n_failed : int
        Number of cases that raised an error.
    """
    cases: List[BatchCaseResult] = field(default_factory=list)
    total_elapsed_ms: float = 0.0
    n_success: int = 0
    n_failed: int = 0

    def summary(self) -> str:
        """Return a human-readable one-line summary."""
        return (
            f"Batch: {self.n_success}/{len(self.cases)} succeeded, "
            f"{self.n_failed} failed, "
            f"total {self.total_elapsed_ms:.1f} ms"
        )

    def failed_cases(self) -> List[BatchCaseResult]:
        """Return only the failed cases."""
        return [c for c in self.cases if not c.success]

    def successful_cases(self) -> List[BatchCaseResult]:
        """Return only the successful cases."""
        return [c for c in self.cases if c.success]


# =====================================================================
#  MISO case generation
# =====================================================================

def generate_miso_cases(
    mv_cols: List[str],
    cv_cols: List[str],
    base_config: IdentConfig,
) -> List[BatchCase]:
    """Generate one MISO identification case per CV.

    This is the standard DMC3 decomposition: for each CV, identify a
    model from *all* MVs to that single CV.  Each case is independent
    and can be run in sequence.

    Parameters
    ----------
    mv_cols : list of str
        MV column names (inputs).
    cv_cols : list of str
        CV column names (outputs).
    base_config : IdentConfig
        Base identification configuration.  A deep copy is made for
        each case so cases can be modified independently.

    Returns
    -------
    list of BatchCase
        One ``BatchCase`` per CV, each with all MVs as inputs.
    """
    if not mv_cols:
        raise ValueError("mv_cols must not be empty")
    if not cv_cols:
        raise ValueError("cv_cols must not be empty")

    cases: List[BatchCase] = []
    for cv in cv_cols:
        case = BatchCase(
            name=f"CV_{cv}",
            mv_cols=list(mv_cols),
            cv_cols=[cv],
            config=deepcopy(base_config),
        )
        cases.append(case)
        logger.debug("Generated MISO case '%s': %d MVs -> %s", case.name, len(mv_cols), cv)

    logger.info(
        "Generated %d MISO cases (%d MVs x %d CVs)",
        len(cases), len(mv_cols), len(cv_cols),
    )
    return cases


def auto_generate_batch(
    df: pd.DataFrame,
    mv_cols: List[str],
    cv_cols: List[str],
    base_config: IdentConfig,
) -> List[BatchCase]:
    """Auto-generate and validate MISO cases from a DataFrame.

    Like :func:`generate_miso_cases`, but additionally validates that
    all specified columns exist in *df* and logs warnings for columns
    with excessive missing data.

    Parameters
    ----------
    df : pd.DataFrame
        The data to be used for identification.
    mv_cols : list of str
        MV column names (must be present in *df*).
    cv_cols : list of str
        CV column names (must be present in *df*).
    base_config : IdentConfig
        Base configuration for all cases.

    Returns
    -------
    list of BatchCase
        Generated cases, one per CV.

    Raises
    ------
    ValueError
        If any specified column is not found in *df*.
    """
    # Validate columns.
    all_cols = set(df.columns)
    missing_mv = [c for c in mv_cols if c not in all_cols]
    missing_cv = [c for c in cv_cols if c not in all_cols]
    if missing_mv:
        raise ValueError(f"MV columns not found in DataFrame: {missing_mv}")
    if missing_cv:
        raise ValueError(f"CV columns not found in DataFrame: {missing_cv}")

    # Warn about data quality.
    for col in mv_cols + cv_cols:
        nan_frac = df[col].isna().mean()
        if nan_frac > 0.5:
            logger.warning(
                "Column '%s' has %.1f%% missing data -- identification may "
                "be unreliable",
                col, nan_frac * 100,
            )
        elif nan_frac > 0.1:
            logger.info(
                "Column '%s' has %.1f%% missing data", col, nan_frac * 100
            )

    return generate_miso_cases(mv_cols, cv_cols, base_config)


# =====================================================================
#  Batch execution
# =====================================================================

def _extract_data(
    df_or_array: Union[pd.DataFrame, Mat],
    cols: List[str],
) -> Mat:
    """Extract a 2-D numpy array from a DataFrame or pass through raw array."""
    if isinstance(df_or_array, pd.DataFrame):
        return df_or_array[cols].to_numpy(dtype=np.float64)
    return np.asarray(df_or_array, dtype=np.float64)


def _run_single_case(
    case: BatchCase,
    u_data: Union[pd.DataFrame, Mat],
    y_data: Union[pd.DataFrame, Mat],
) -> BatchCaseResult:
    """Run a single identification case and return the result."""
    t0 = time.perf_counter()
    try:
        # Extract input/output matrices.
        if isinstance(u_data, pd.DataFrame):
            u = u_data[case.mv_cols].to_numpy(dtype=np.float64)
        else:
            u = np.asarray(u_data, dtype=np.float64)

        if isinstance(y_data, pd.DataFrame):
            y = y_data[case.cv_cols].to_numpy(dtype=np.float64)
        else:
            y = np.asarray(y_data, dtype=np.float64)

        # Ensure 2-D.
        if u.ndim == 1:
            u = u.reshape(-1, 1)
        if y.ndim == 1:
            y = y.reshape(-1, 1)

        # Run identification.
        identifier = FIRIdentifier(case.config)
        result = identifier.identify(u, y)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "Case '%s' completed in %.1f ms", case.name, elapsed_ms
        )
        return BatchCaseResult(
            name=case.name,
            case=case,
            ident_result=result,
            elapsed_ms=elapsed_ms,
            success=True,
        )

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.error(
            "Case '%s' failed after %.1f ms: %s", case.name, elapsed_ms, exc
        )
        return BatchCaseResult(
            name=case.name,
            case=case,
            ident_result=None,
            elapsed_ms=elapsed_ms,
            success=False,
            error=str(exc),
        )


def run_batch(
    cases: List[BatchCase],
    u_data: Union[pd.DataFrame, Mat],
    y_data: Union[pd.DataFrame, Mat],
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> BatchReport:
    """Run all identification cases sequentially.

    Parameters
    ----------
    cases : list of BatchCase
        Cases to execute.
    u_data : pd.DataFrame or ndarray
        Input (MV) data.  If a DataFrame, column names are used to
        select the relevant MVs for each case.  If a raw array, it is
        passed directly (must already be aligned to each case).
    y_data : pd.DataFrame or ndarray
        Output (CV) data.  Same conventions as *u_data*.
    progress_callback : callable, optional
        Called after each case with ``(case_index, total_cases,
        case_name)``.  Useful for UI progress bars.

    Returns
    -------
    BatchReport
        Aggregated results with per-case details and summary counts.
    """
    if not cases:
        logger.warning("run_batch called with empty case list")
        return BatchReport()

    total = len(cases)
    logger.info("Starting batch execution of %d cases", total)
    t_batch_start = time.perf_counter()

    results: List[BatchCaseResult] = []
    n_success = 0
    n_failed = 0

    for idx, case in enumerate(cases):
        logger.info(
            "Running case %d/%d: '%s' (%d MVs -> %d CVs)",
            idx + 1, total, case.name,
            len(case.mv_cols), len(case.cv_cols),
        )

        result = _run_single_case(case, u_data, y_data)
        results.append(result)

        if result.success:
            n_success += 1
        else:
            n_failed += 1

        if progress_callback is not None:
            try:
                progress_callback(idx + 1, total, case.name)
            except Exception as cb_exc:
                logger.warning(
                    "Progress callback raised an exception: %s", cb_exc
                )

    total_elapsed_ms = (time.perf_counter() - t_batch_start) * 1000.0

    report = BatchReport(
        cases=results,
        total_elapsed_ms=total_elapsed_ms,
        n_success=n_success,
        n_failed=n_failed,
    )
    logger.info(report.summary())
    return report
