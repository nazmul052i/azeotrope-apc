"""Tag-based data exclusion rules and forward-fill with gap limits.

Industrial step-test data frequently contains periods that must be
excluded from identification: operator interventions, equipment trips,
controller mode changes, analyzer faults, etc.  Rather than manually
marking every bad window on a trend plot, engineers write *rules*
in the language they already think in:

    "Exclude when reactor temperature < 200 degC"
    "Exclude when feed flow == 0"
    "Exclude 2026-04-09 14:00 to 2026-04-09 14:30"

This module implements three rule types:

1. **ExclusionRule** -- tag-based conditional: compare a column against
   a threshold using standard operators (<, >, <=, >=, ==, !=).
   ``signal_only=True`` NaN-s the target tag only; ``False`` removes
   the entire row.

2. **ExclusionPeriod** -- absolute timestamp range removal.

3. **ForwardFillRule** -- per-tag gap filling with a configurable
   maximum gap width (``max_steps``).  Methods: ``hold`` (zero-order
   hold) or ``interpolate`` (linear interpolation).

Usage::

    rules = [
        ExclusionRule(tag="TI101", operator="<", value=200.0),
        ExclusionRule(tag="FI201", operator="==", value=0.0, signal_only=True),
    ]
    periods = [
        ExclusionPeriod(start="2026-04-09 14:00", end="2026-04-09 14:30"),
    ]
    fills = [
        ForwardFillRule(tag="AI301", max_steps=5, method="interpolate"),
    ]
    df_clean, report = apply_all_rules(df, rules, periods, fills)
"""
from __future__ import annotations

import logging
import operator as op
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TimeStamp = Union[str, pd.Timestamp]


# ---------------------------------------------------------------------------
# Rule dataclasses
# ---------------------------------------------------------------------------
@dataclass
class ExclusionRule:
    """Tag-based conditional exclusion.

    Rows (or individual tag values) where ``df[tag] <operator> value``
    is True are marked as bad.
    """
    tag: str
    operator: str            # "<", ">", "<=", ">=", "==", "!="
    value: float
    signal_only: bool = False  # True -> NaN the tag only; False -> drop row
    description: str = ""


@dataclass
class ExclusionPeriod:
    """Absolute timestamp range to remove."""
    start: TimeStamp
    end: TimeStamp
    description: str = ""


@dataclass
class ForwardFillRule:
    """Per-tag gap filling with a maximum gap width."""
    tag: str
    max_steps: int = 10      # max consecutive NaNs to fill
    method: str = "hold"     # "hold" (ffill) | "interpolate" (linear)
    description: str = ""


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class RulesReport:
    """Diagnostic counters for a rules run."""
    n_rows_in: int = 0
    n_rows_out: int = 0
    n_excluded_by_rules: int = 0
    n_excluded_by_periods: int = 0
    n_nan_by_signal_rules: int = 0
    n_forward_filled: int = 0
    per_rule: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Data rules: {self.n_rows_in} -> {self.n_rows_out} rows",
            f"  excluded by tag rules : {self.n_excluded_by_rules}",
            f"  excluded by periods   : {self.n_excluded_by_periods}",
            f"  NaN by signal rules   : {self.n_nan_by_signal_rules}",
            f"  forward-filled values : {self.n_forward_filled}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Operator map
# ---------------------------------------------------------------------------
_OPS = {
    "<": op.lt, ">": op.gt,
    "<=": op.le, ">=": op.ge,
    "==": op.eq, "!=": op.ne,
}


# ---------------------------------------------------------------------------
# Rule application
# ---------------------------------------------------------------------------
def apply_exclusion_rules(
    df: pd.DataFrame,
    rules: Sequence[ExclusionRule],
) -> Tuple[pd.DataFrame, int, int]:
    """Apply tag-based exclusion rules.

    Returns (df_out, n_rows_dropped, n_values_nan).
    """
    df_out = df.copy()
    n_rows_dropped = 0
    n_nan = 0

    for rule in rules:
        if rule.tag not in df_out.columns:
            logger.warning("ExclusionRule: tag '%s' not in DataFrame", rule.tag)
            continue
        func = _OPS.get(rule.operator)
        if func is None:
            raise ValueError(f"Unknown operator: {rule.operator!r}")

        mask = func(df_out[rule.tag], rule.value)
        # Handle NaN comparison (NaN comparisons return False, which is fine)
        mask = mask.fillna(False) if isinstance(mask, pd.Series) else mask
        n_match = int(mask.sum())

        if n_match == 0:
            continue

        if rule.signal_only:
            df_out.loc[mask, rule.tag] = np.nan
            n_nan += n_match
        else:
            df_out = df_out.loc[~mask]
            n_rows_dropped += n_match

    return df_out, n_rows_dropped, n_nan


def apply_exclusion_periods(
    df: pd.DataFrame,
    periods: Sequence[ExclusionPeriod],
) -> Tuple[pd.DataFrame, int]:
    """Remove rows within absolute timestamp ranges.

    Returns (df_out, n_rows_dropped).
    """
    if not periods:
        return df, 0

    if not isinstance(df.index, pd.DatetimeIndex):
        logger.warning("ExclusionPeriod requires DatetimeIndex; skipping")
        return df, 0

    df_out = df.copy()
    total_dropped = 0

    for period in periods:
        lo = pd.Timestamp(period.start)
        hi = pd.Timestamp(period.end)
        mask = (df_out.index >= lo) & (df_out.index <= hi)
        n = int(mask.sum())
        if n > 0:
            df_out = df_out.loc[~mask]
            total_dropped += n

    return df_out, total_dropped


def apply_forward_fills(
    df: pd.DataFrame,
    rules: Sequence[ForwardFillRule],
) -> Tuple[pd.DataFrame, int]:
    """Apply per-tag forward-fill with gap limits.

    Returns (df_out, n_values_filled).
    """
    df_out = df.copy()
    n_filled = 0

    for rule in rules:
        if rule.tag not in df_out.columns:
            logger.warning("ForwardFillRule: tag '%s' not in DataFrame", rule.tag)
            continue

        col = df_out[rule.tag]
        n_nan_before = int(col.isna().sum())

        if rule.method == "hold":
            df_out[rule.tag] = col.ffill(limit=rule.max_steps)
        elif rule.method == "interpolate":
            df_out[rule.tag] = col.interpolate(
                method="linear", limit=rule.max_steps,
                limit_direction="forward")
        else:
            raise ValueError(f"Unknown fill method: {rule.method!r}")

        n_nan_after = int(df_out[rule.tag].isna().sum())
        n_filled += max(0, n_nan_before - n_nan_after)

    return df_out, n_filled


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------
def apply_all_rules(
    df: pd.DataFrame,
    exclusion_rules: Optional[Sequence[ExclusionRule]] = None,
    exclusion_periods: Optional[Sequence[ExclusionPeriod]] = None,
    forward_fills: Optional[Sequence[ForwardFillRule]] = None,
) -> Tuple[pd.DataFrame, RulesReport]:
    """Apply all rule types sequentially and return a diagnostic report.

    Order: exclusion rules -> exclusion periods -> forward fills.
    """
    report = RulesReport(n_rows_in=len(df))
    df_work = df

    # Step 1: Tag-based exclusion
    if exclusion_rules:
        df_work, n_dropped, n_nan = apply_exclusion_rules(df_work, exclusion_rules)
        report.n_excluded_by_rules = n_dropped
        report.n_nan_by_signal_rules = n_nan

    # Step 2: Period exclusion
    if exclusion_periods:
        df_work, n_dropped = apply_exclusion_periods(df_work, exclusion_periods)
        report.n_excluded_by_periods = n_dropped

    # Step 3: Forward fills
    if forward_fills:
        df_work, n_filled = apply_forward_fills(df_work, forward_fills)
        report.n_forward_filled = n_filled

    report.n_rows_out = len(df_work)
    return df_work, report
