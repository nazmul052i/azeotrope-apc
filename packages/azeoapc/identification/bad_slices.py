"""Bad interpolated slices: mark bad ranges that get linearly interpolated
rather than excluded (which removes rows entirely).

In DMC3 "bad slices" are time ranges where the data is unreliable.
There are two modes:

1. **Exclude** — remove the rows entirely (existing segment excluded_ranges).
2. **Interpolate** — keep the rows but replace values with linear
   interpolation between the last good point before and the first good
   point after the slice.

Mode 2 is important because FIR identification uses a Toeplitz matrix
that requires contiguous data.  Excluding rows creates gaps that break
the regression.  Interpolating preserves the row count and continuity.

Usage::

    slices = [
        BadSlice(start=100, end=120, mode="interpolate"),
        BadSlice(start=300, end=310, mode="interpolate", columns=["TI101"]),
        BadSlice(start=500, end=550, mode="exclude"),
    ]
    df_clean, report = apply_bad_slices(df, slices)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TimeStamp = Union[str, int, pd.Timestamp]


@dataclass
class BadSlice:
    """Definition of one bad data slice."""
    start: TimeStamp
    end: TimeStamp
    mode: str = "interpolate"     # "interpolate" or "exclude"
    columns: Optional[List[str]] = None  # None = all columns
    description: str = ""


@dataclass
class BadSliceReport:
    """Diagnostic counters."""
    n_slices: int = 0
    n_interpolated_samples: int = 0
    n_excluded_rows: int = 0
    per_slice: List[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Bad slices: {self.n_slices} slices, "
            f"{self.n_interpolated_samples} interpolated, "
            f"{self.n_excluded_rows} excluded"]
        for s in self.per_slice:
            lines.append(f"  {s['start']}-{s['end']}: {s['mode']} ({s['n_affected']} samples)")
        return "\n".join(lines)


def _resolve_indices(
    df: pd.DataFrame,
    start: TimeStamp,
    end: TimeStamp,
) -> Tuple[int, int]:
    """Resolve start/end to integer positions."""
    if isinstance(df.index, pd.DatetimeIndex):
        ts_start = pd.Timestamp(start)
        ts_end = pd.Timestamp(end)
        mask = (df.index >= ts_start) & (df.index <= ts_end)
        positions = np.where(mask)[0]
        if len(positions) == 0:
            return 0, 0
        return int(positions[0]), int(positions[-1]) + 1
    else:
        return int(start), int(end)


def apply_bad_slices(
    df: pd.DataFrame,
    slices: Sequence[BadSlice],
) -> Tuple[pd.DataFrame, BadSliceReport]:
    """Apply bad slices to a DataFrame.

    Interpolated slices: values are replaced with linear interpolation.
    Excluded slices: rows are removed.

    Returns (df_out, report).
    """
    df_out = df.copy()
    report = BadSliceReport(n_slices=len(slices))

    # Process interpolated slices first (they preserve row count)
    for bs in slices:
        if bs.mode != "interpolate":
            continue

        lo, hi = _resolve_indices(df_out, bs.start, bs.end)
        if lo >= hi:
            continue

        cols = bs.columns or list(df_out.columns)
        cols = [c for c in cols if c in df_out.columns
                and pd.api.types.is_numeric_dtype(df_out[c])]

        n_affected = 0
        for col in cols:
            values = df_out[col].to_numpy(dtype=float)
            # Get boundary values for interpolation
            before_val = values[lo - 1] if lo > 0 else np.nan
            after_val = values[hi] if hi < len(values) else np.nan

            if np.isfinite(before_val) and np.isfinite(after_val):
                interp = np.linspace(before_val, after_val, hi - lo + 2)[1:-1]
                df_out.iloc[lo:hi, df_out.columns.get_loc(col)] = interp
            elif np.isfinite(before_val):
                df_out.iloc[lo:hi, df_out.columns.get_loc(col)] = before_val
            elif np.isfinite(after_val):
                df_out.iloc[lo:hi, df_out.columns.get_loc(col)] = after_val
            n_affected += hi - lo

        report.n_interpolated_samples += n_affected
        report.per_slice.append({
            "start": bs.start, "end": bs.end,
            "mode": "interpolate", "n_affected": hi - lo,
        })

    # Process excluded slices (remove rows)
    exclude_mask = np.zeros(len(df_out), dtype=bool)
    for bs in slices:
        if bs.mode != "exclude":
            continue

        lo, hi = _resolve_indices(df_out, bs.start, bs.end)
        if lo >= hi:
            continue

        exclude_mask[lo:hi] = True
        n_rows = hi - lo
        report.per_slice.append({
            "start": bs.start, "end": bs.end,
            "mode": "exclude", "n_affected": n_rows,
        })

    n_excluded = int(exclude_mask.sum())
    if n_excluded > 0:
        df_out = df_out.loc[~exclude_mask]
        report.n_excluded_rows = n_excluded

    return df_out, report
