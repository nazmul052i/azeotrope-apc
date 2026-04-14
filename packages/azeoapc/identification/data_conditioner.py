"""Step-test data conditioning for FIR identification.

Promoted out of the standalone GUI into the shared library so multiple
apps (the apc_ident studio, batch CLIs, the runtime adaptive-modeling
loop) can share one canonical conditioning pipeline.

Pipeline (each step optional):

  1. Segment selection -- keep only the named time windows the engineer
     marked as "good" data.
  2. Excluded ranges  -- punch holes inside a segment where the operator
     intervened, an alarm fired, or the controller went off-line.
  3. Data exclusion rules -- tag-based conditional and period-based removal.
  4. Industrial data conditioning -- cutoff, flatline, spike detection with
     configurable bad-data replacement (interpolate/hold/mean).
  5. Resample         -- if the source has a datetime index, downsample
     (mean) or upsample (ffill) to a uniform sample period.
  6. Dynamic input filtering -- dead time + cascaded 1st/2nd-order filters.
  7. Forward-fill     -- collapse historian compression gaps.
  8. Outlier clip     -- mark points more than ``clip_sigma`` standard
     deviations from the local mean as bad and interpolate across them.
  9. Bad-quality mask -- if the source ships per-sample quality flags,
     drop or interpolate the BAD points.
 10. Output transforms -- normalize CV distributions for better FIR fit.
 11. Hold-out split   -- optionally carve a fraction of the conditioned
     samples off the tail to use as Validation tab test data.

Returns a ``ConditioningResult`` dataclass that holds the conditioned
arrays plus a diagnostic report (counts of NaN filled, outliers clipped,
samples excluded, etc.) so the GUI can show the engineer exactly what
the pipeline did.

See also
--------
- ``data_conditioning`` -- industrial-grade fault detection & replacement
- ``steady_state`` -- dual exponential filter steady-state detection
- ``resampling`` -- multi-rate analysis with noise/signal trade-off
- ``data_rules`` -- tag-based exclusion rules and forward-fill with limits
- ``dynamic_filter`` -- dead time + 1st/2nd-order input filtering
- ``transforms`` -- output transforms with Shapiro-Wilk auto-selection
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from .data_conditioning import (
    ConditioningEngineConfig,
    ConditioningEngineReport,
    auto_configure as auto_configure_conditioning,
    condition_dataframe as run_conditioning_engine,
)
from .data_rules import (
    ExclusionRule,
    ExclusionPeriod,
    ForwardFillRule,
    apply_all_rules,
)
from .dynamic_filter import (
    VariableFilter,
    filter_dataframe as run_dynamic_filter,
)
from .transforms import (
    OutputTransform,
    TransformMethod,
    auto_select_transform,
)

logger = logging.getLogger(__name__)

TimeStamp = Union[str, pd.Timestamp]


# ---------------------------------------------------------------------------
# Configuration + result dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Segment:
    """A named time window that contains usable step-test data."""
    name: str
    start: Optional[TimeStamp] = None
    end: Optional[TimeStamp] = None
    excluded_ranges: List[Tuple[TimeStamp, TimeStamp]] = field(default_factory=list)


@dataclass
class ConditioningConfig:
    """Knobs that drive the conditioning pipeline.

    All defaults are reasonable for refinery historian data sampled at
    1-minute intervals; the GUI surfaces these as form fields.
    """
    resample_period_sec: Optional[float] = None       # None -> leave as-is
    resample_aggregator: str = "mean"                  # mean | last | first
    fillna_method: str = "ffill"                       # ffill | bfill | linear
    clip_sigma: float = 4.0                            # 0 disables outlier clip
    quality_col: Optional[str] = None                  # column with GOOD/BAD flags
    quality_good_value: object = "GOOD"
    holdout_fraction: float = 0.0                      # 0..0.5; tail kept for validation

    # --- Industrial data conditioning (Tier 1) ---
    conditioning_engine: Optional[ConditioningEngineConfig] = None
    auto_configure_conditioning: bool = False          # auto-build from stats

    # --- Data exclusion rules (Tier 2) ---
    exclusion_rules: List[ExclusionRule] = field(default_factory=list)
    exclusion_periods: List[ExclusionPeriod] = field(default_factory=list)
    forward_fill_rules: List[ForwardFillRule] = field(default_factory=list)

    # --- Dynamic input filtering (Tier 2) ---
    input_filters: Dict[str, VariableFilter] = field(default_factory=dict)
    auto_tune_filters: bool = False                    # auto-tune from xcorr
    filter_dt: Optional[float] = None                  # sample period for filters

    # --- Output transforms (Tier 2) ---
    output_transforms: Dict[str, OutputTransform] = field(default_factory=dict)
    auto_select_transforms: bool = False               # auto via Shapiro-Wilk


@dataclass
class ConditioningReport:
    """Diagnostic counts -- the GUI shows these on the Data tab."""
    n_rows_in: int = 0
    n_rows_out: int = 0
    n_segments: int = 0
    n_excluded_samples: int = 0
    n_resampled_to: Optional[int] = None
    n_nan_filled: int = 0
    n_outliers_clipped: int = 0
    n_bad_quality: int = 0
    n_holdout: int = 0
    columns_used: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    # Industrial conditioning diagnostics
    conditioning_engine_report: Optional[ConditioningEngineReport] = None
    n_rule_excluded: int = 0
    n_period_excluded: int = 0
    n_rule_nan: int = 0
    n_rule_filled: int = 0
    n_inputs_filtered: int = 0
    n_outputs_transformed: int = 0

    def summary(self) -> str:
        lines = [
            f"Conditioning report",
            f"  rows in / out  : {self.n_rows_in} -> {self.n_rows_out}",
            f"  segments       : {self.n_segments}",
            f"  excluded samples: {self.n_excluded_samples}",
        ]
        if self.conditioning_engine_report:
            total = self.conditioning_engine_report.total_faults()
            if total > 0:
                lines.append(f"  sensor faults  : {total} "
                             f"(cutoff/flatline/spike)")
        if self.n_rule_excluded or self.n_rule_nan:
            lines.append(f"  rule excluded  : {self.n_rule_excluded} rows, "
                         f"{self.n_rule_nan} values NaN'd")
        if self.n_period_excluded:
            lines.append(f"  period excluded: {self.n_period_excluded} rows")
        if self.n_rule_filled:
            lines.append(f"  rule filled    : {self.n_rule_filled} values")
        if self.n_resampled_to is not None:
            lines.append(f"  resampled to   : {self.n_resampled_to} samples")
        if self.n_inputs_filtered:
            lines.append(f"  inputs filtered: {self.n_inputs_filtered} columns")
        lines += [
            f"  NaN filled     : {self.n_nan_filled}",
            f"  outliers clipped: {self.n_outliers_clipped}",
            f"  bad-quality    : {self.n_bad_quality}",
        ]
        if self.n_outputs_transformed:
            lines.append(f"  outputs transformed: {self.n_outputs_transformed}")
        lines.append(f"  hold-out tail  : {self.n_holdout}")
        if self.notes:
            lines.append(f"  notes:")
            lines += [f"    - {n}" for n in self.notes]
        return "\n".join(lines)


@dataclass
class ConditioningResult:
    """Output of one conditioning run.

    The training arrays go to the FIR identifier; the hold-out arrays
    go to the Validation tab. ``df_clean`` is the conditioned dataframe
    so the GUI can plot before/after.
    """
    u_train: np.ndarray            # (N_train, nu)
    y_train: np.ndarray            # (N_train, ny)
    u_holdout: Optional[np.ndarray] = None
    y_holdout: Optional[np.ndarray] = None
    df_clean: Optional[pd.DataFrame] = None
    mv_cols: List[str] = field(default_factory=list)
    cv_cols: List[str] = field(default_factory=list)
    report: ConditioningReport = field(default_factory=ConditioningReport)


# ---------------------------------------------------------------------------
# DataConditioner
# ---------------------------------------------------------------------------
class DataConditioner:
    """Stateless step-test data conditioner.

    Usage::

        cond = DataConditioner()
        result = cond.run(
            df, mv_cols=["FIC101_SP", "FIC102_SP"],
            cv_cols=["TI201", "FI201"],
            segments=[Segment("test1", "2026-04-09 08:30", "2026-04-09 11:00")],
            config=ConditioningConfig(resample_period_sec=60.0,
                                       holdout_fraction=0.2),
        )
        u_train, y_train = result.u_train, result.y_train
        print(result.report.summary())
    """

    def run(
        self,
        df: pd.DataFrame,
        mv_cols: Sequence[str],
        cv_cols: Sequence[str],
        segments: Optional[Sequence[Segment]] = None,
        config: Optional[ConditioningConfig] = None,
    ) -> ConditioningResult:
        cfg = config or ConditioningConfig()
        report = ConditioningReport()

        mv_cols = list(mv_cols)
        cv_cols = list(cv_cols)
        report.columns_used = mv_cols + cv_cols
        report.n_rows_in = len(df)

        if not mv_cols or not cv_cols:
            raise ValueError("At least one MV column and one CV column required")
        missing = [c for c in mv_cols + cv_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Columns not in dataframe: {missing}")

        # Step 1+2: segment selection + excluded ranges
        df_seg = self._apply_segments(df, segments, report)

        # Quality column filtering
        df_seg = self._apply_quality_mask(df_seg, cfg, report)

        # Restrict to the columns we need
        keep = mv_cols + cv_cols + (
            [cfg.quality_col] if cfg.quality_col and cfg.quality_col in df_seg.columns
            else []
        )
        df_work = df_seg[keep].copy()

        # Step 3: data exclusion rules (tag-based + period-based)
        df_work = self._apply_data_rules(df_work, cfg, report)

        # Step 4: industrial data conditioning (cutoff/flatline/spike)
        df_work = self._apply_conditioning_engine(
            df_work, mv_cols + cv_cols, cfg, report)

        # Step 5: resample if requested and we have a datetime index
        df_work = self._apply_resample(df_work, cfg, report)

        # Step 6: dynamic input filtering
        df_work = self._apply_dynamic_filters(
            df_work, mv_cols, cv_cols, cfg, report)

        # Step 7: forward-fill historian gaps
        df_work, n_filled = self._fill_nans(df_work, cfg)
        report.n_nan_filled = n_filled

        # Step 8: outlier clip
        df_work, n_clipped = self._clip_outliers(df_work, mv_cols + cv_cols, cfg)
        report.n_outliers_clipped = n_clipped

        # Final NaN safety pass
        df_work = df_work.ffill().bfill()

        # Step 9: output transforms
        df_work = self._apply_output_transforms(df_work, cv_cols, cfg, report)

        # Drop the quality column from the export but keep the conditioned df
        df_clean = df_work.copy()
        if cfg.quality_col and cfg.quality_col in df_work.columns:
            df_work = df_work.drop(columns=[cfg.quality_col])

        report.n_rows_out = len(df_work)

        # Step 10: hold-out split
        u, y, u_hold, y_hold, n_hold = self._split_holdout(
            df_work, mv_cols, cv_cols, cfg)
        report.n_holdout = n_hold

        return ConditioningResult(
            u_train=u, y_train=y,
            u_holdout=u_hold, y_holdout=y_hold,
            df_clean=df_clean,
            mv_cols=mv_cols, cv_cols=cv_cols,
            report=report,
        )

    # ------------------------------------------------------------------
    def _apply_data_rules(
        self,
        df: pd.DataFrame,
        cfg: ConditioningConfig,
        report: ConditioningReport,
    ) -> pd.DataFrame:
        """Apply tag-based exclusion rules, period exclusions, forward fills."""
        has_rules = (cfg.exclusion_rules or cfg.exclusion_periods
                     or cfg.forward_fill_rules)
        if not has_rules:
            return df
        df_out, rules_report = apply_all_rules(
            df, cfg.exclusion_rules, cfg.exclusion_periods,
            cfg.forward_fill_rules)
        report.n_rule_excluded = rules_report.n_excluded_by_rules
        report.n_period_excluded = rules_report.n_excluded_by_periods
        report.n_rule_nan = rules_report.n_nan_by_signal_rules
        report.n_rule_filled = rules_report.n_forward_filled
        return df_out

    # ------------------------------------------------------------------
    def _apply_conditioning_engine(
        self,
        df: pd.DataFrame,
        all_cols: Sequence[str],
        cfg: ConditioningConfig,
        report: ConditioningReport,
    ) -> pd.DataFrame:
        """Run industrial data conditioning (cutoff/flatline/spike)."""
        engine_cfg = cfg.conditioning_engine
        if engine_cfg is None and not cfg.auto_configure_conditioning:
            return df
        if engine_cfg is None:
            engine_cfg = auto_configure_conditioning(df, columns=list(all_cols))
        df_out, eng_report = run_conditioning_engine(
            df, engine_cfg, columns=list(all_cols))
        report.conditioning_engine_report = eng_report
        return df_out

    # ------------------------------------------------------------------
    def _apply_dynamic_filters(
        self,
        df: pd.DataFrame,
        mv_cols: Sequence[str],
        cv_cols: Sequence[str],
        cfg: ConditioningConfig,
        report: ConditioningReport,
    ) -> pd.DataFrame:
        """Apply dead-time + exponential input filters."""
        filters = dict(cfg.input_filters)

        if cfg.auto_tune_filters and cv_cols:
            from .dynamic_filter import auto_tune_all
            dt = cfg.filter_dt or cfg.resample_period_sec or 1.0
            tuned = auto_tune_all(df, mv_cols, cv_cols[0], dt)
            # Merge: manual overrides auto-tuned
            for col, filt in tuned.items():
                if col not in filters:
                    filters[col] = filt

        if not filters:
            return df

        dt = cfg.filter_dt or cfg.resample_period_sec or 1.0
        df_out = run_dynamic_filter(df, filters, dt)
        report.n_inputs_filtered = sum(
            1 for f in filters.values() if f.enabled)
        return df_out

    # ------------------------------------------------------------------
    def _apply_output_transforms(
        self,
        df: pd.DataFrame,
        cv_cols: Sequence[str],
        cfg: ConditioningConfig,
        report: ConditioningReport,
    ) -> pd.DataFrame:
        """Apply output transforms to CV columns."""
        transforms = dict(cfg.output_transforms)

        if cfg.auto_select_transforms:
            for col in cv_cols:
                if col not in transforms and col in df.columns:
                    values = df[col].dropna().to_numpy()
                    tf = auto_select_transform(values)
                    if tf.method != TransformMethod.NONE:
                        transforms[col] = tf

        if not transforms:
            return df

        df_out = df.copy()
        n_transformed = 0
        for col, tf in transforms.items():
            if col not in df_out.columns:
                continue
            if tf.method == TransformMethod.NONE:
                continue
            values = df_out[col].to_numpy(dtype=float)
            df_out[col] = tf.forward(values)
            n_transformed += 1

        report.n_outputs_transformed = n_transformed
        return df_out

    # ------------------------------------------------------------------
    def _apply_segments(
        self,
        df: pd.DataFrame,
        segments: Optional[Sequence[Segment]],
        report: ConditioningReport,
    ) -> pd.DataFrame:
        """Concatenate the named segments and punch out excluded ranges."""
        if not segments:
            report.n_segments = 0
            return df

        report.n_segments = len(segments)
        is_dt = isinstance(df.index, pd.DatetimeIndex)
        if not is_dt:
            report.notes.append(
                "segment selection requested but dataframe has no datetime index;"
                " using positional .loc which may behave unexpectedly")

        chunks: List[pd.DataFrame] = []
        n_excluded = 0
        for seg in segments:
            if is_dt:
                lo = pd.Timestamp(seg.start) if seg.start else df.index[0]
                hi = pd.Timestamp(seg.end) if seg.end else df.index[-1]
                mask = (df.index >= lo) & (df.index <= hi)
            else:
                lo = int(seg.start) if seg.start is not None else 0
                hi = int(seg.end) if seg.end is not None else len(df)
                mask = np.zeros(len(df), dtype=bool)
                mask[lo:hi] = True
            chunk = df.loc[mask].copy()

            # Punch out excluded ranges inside this segment
            for ex_start, ex_end in seg.excluded_ranges:
                if is_dt:
                    ex_lo = pd.Timestamp(ex_start)
                    ex_hi = pd.Timestamp(ex_end)
                    bad = (chunk.index >= ex_lo) & (chunk.index <= ex_hi)
                else:
                    ex_lo = int(ex_start)
                    ex_hi = int(ex_end)
                    bad = np.zeros(len(chunk), dtype=bool)
                    bad[ex_lo:ex_hi] = True
                n_excluded += int(bad.sum())
                chunk = chunk.loc[~bad]
            chunks.append(chunk)

        report.n_excluded_samples = n_excluded
        if not chunks:
            return df.iloc[0:0]
        return pd.concat(chunks)

    # ------------------------------------------------------------------
    def _apply_quality_mask(
        self,
        df: pd.DataFrame,
        cfg: ConditioningConfig,
        report: ConditioningReport,
    ) -> pd.DataFrame:
        if not cfg.quality_col or cfg.quality_col not in df.columns:
            return df
        bad = df[cfg.quality_col] != cfg.quality_good_value
        report.n_bad_quality = int(bad.sum())
        if report.n_bad_quality > 0:
            # Drop the bad rows; downstream interpolation re-fills them only
            # if the row order remains contiguous (it does after segment cat).
            df = df.loc[~bad]
        return df

    # ------------------------------------------------------------------
    def _apply_resample(
        self,
        df: pd.DataFrame,
        cfg: ConditioningConfig,
        report: ConditioningReport,
    ) -> pd.DataFrame:
        if cfg.resample_period_sec is None:
            return df
        if not isinstance(df.index, pd.DatetimeIndex):
            report.notes.append(
                "resample requested but dataframe has no datetime index;"
                " resample skipped")
            return df
        rule = f"{int(cfg.resample_period_sec)}s"
        agg = cfg.resample_aggregator
        if agg == "mean":
            out = df.resample(rule).mean()
        elif agg == "last":
            out = df.resample(rule).last()
        elif agg == "first":
            out = df.resample(rule).first()
        else:
            raise ValueError(f"unknown resample_aggregator: {agg}")
        report.n_resampled_to = len(out)
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _fill_nans(
        df: pd.DataFrame, cfg: ConditioningConfig,
    ) -> Tuple[pd.DataFrame, int]:
        n_before = int(df.isna().sum().sum())
        if cfg.fillna_method == "ffill":
            df = df.ffill().bfill()
        elif cfg.fillna_method == "bfill":
            df = df.bfill().ffill()
        elif cfg.fillna_method == "linear":
            num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            if num_cols:
                df[num_cols] = df[num_cols].interpolate(
                    method="linear", limit_direction="both")
            # Non-numeric columns get ffill as a sensible default
            df = df.ffill().bfill()
        return df, n_before

    # ------------------------------------------------------------------
    @staticmethod
    def _clip_outliers(
        df: pd.DataFrame, cols: Sequence[str], cfg: ConditioningConfig,
    ) -> Tuple[pd.DataFrame, int]:
        if cfg.clip_sigma <= 0:
            return df, 0
        n_clipped = 0
        numeric_cols = [c for c in cols
                        if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        for col in numeric_cols:
            series = df[col]
            mu = series.mean()
            sigma = series.std()
            if sigma > 1e-15:
                bad = (series - mu).abs() > cfg.clip_sigma * sigma
                k = int(bad.sum())
                if k > 0:
                    df.loc[bad, col] = np.nan
                    n_clipped += k
        # Interpolate only the numeric columns we just touched (string
        # columns like quality flags can't be interpolated linearly).
        if numeric_cols:
            df[numeric_cols] = df[numeric_cols].interpolate(
                method="linear", limit_direction="both")
        return df, n_clipped

    # ------------------------------------------------------------------
    @staticmethod
    def _split_holdout(
        df: pd.DataFrame,
        mv_cols: Sequence[str],
        cv_cols: Sequence[str],
        cfg: ConditioningConfig,
    ) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[np.ndarray], int]:
        u = df[list(mv_cols)].to_numpy(dtype=np.float64)
        y = df[list(cv_cols)].to_numpy(dtype=np.float64)
        n = len(u)
        frac = max(0.0, min(0.5, float(cfg.holdout_fraction)))
        if frac == 0.0 or n < 20:
            return u, y, None, None, 0
        n_hold = int(round(n * frac))
        if n_hold < 1:
            return u, y, None, None, 0
        return u[:-n_hold], y[:-n_hold], u[-n_hold:], y[-n_hold:], n_hold
