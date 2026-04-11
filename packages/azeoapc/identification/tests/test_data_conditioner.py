"""Tests for the data conditioning pipeline."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from azeoapc.identification import (
    ConditioningConfig, DataConditioner, Segment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_df(
    n: int = 1000, with_dt_index: bool = True, with_quality: bool = False,
    with_outliers: int = 0, with_nans: int = 0, seed: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    mv1 = rng.normal(100, 5, n)
    mv2 = rng.normal(50, 2, n)
    cv1 = mv1 * 0.5 + mv2 * 0.3 + rng.normal(0, 0.5, n)
    cv2 = mv1 * 0.2 + rng.normal(0, 0.3, n)

    if with_outliers > 0:
        idx = rng.choice(n, size=with_outliers, replace=False)
        cv1[idx] = 9999.0   # huge outliers

    if with_nans > 0:
        idx = rng.choice(n, size=with_nans, replace=False)
        mv1[idx] = np.nan

    df = pd.DataFrame({"FIC101_SP": mv1, "FIC102_SP": mv2,
                        "TI201": cv1, "FI201": cv2})

    if with_dt_index:
        df.index = pd.date_range("2026-04-09 08:00", periods=n, freq="60s")

    if with_quality:
        q = np.array(["GOOD"] * n)
        # Mark every 50th sample BAD
        q[::50] = "BAD"
        df["QC"] = q

    return df


# ---------------------------------------------------------------------------
# Basic happy path
# ---------------------------------------------------------------------------
def test_basic_run_returns_arrays_with_expected_shape():
    df = _make_df(n=500)
    cond = DataConditioner()
    result = cond.run(
        df, mv_cols=["FIC101_SP", "FIC102_SP"],
        cv_cols=["TI201", "FI201"],
    )
    assert result.u_train.shape == (500, 2)
    assert result.y_train.shape == (500, 2)
    assert result.report.n_rows_in == 500
    assert result.report.n_rows_out == 500


def test_missing_columns_raises():
    df = _make_df(n=200)
    cond = DataConditioner()
    with pytest.raises(ValueError, match="not in dataframe"):
        cond.run(df, mv_cols=["NOT_A_TAG"], cv_cols=["TI201"])


def test_no_mv_or_cv_raises():
    df = _make_df(n=200)
    cond = DataConditioner()
    with pytest.raises(ValueError, match="At least one MV"):
        cond.run(df, mv_cols=[], cv_cols=["TI201"])


# ---------------------------------------------------------------------------
# Outlier clip
# ---------------------------------------------------------------------------
def test_outlier_clip_removes_huge_spikes():
    df = _make_df(n=500, with_outliers=10)
    cond = DataConditioner()
    cfg = ConditioningConfig(clip_sigma=3.0)
    result = cond.run(df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"],
                      config=cfg)
    # No surviving 9999 values
    assert result.y_train.max() < 1000
    assert result.report.n_outliers_clipped >= 10


def test_clip_sigma_zero_disables_clipping():
    df = _make_df(n=500, with_outliers=5)
    cond = DataConditioner()
    cfg = ConditioningConfig(clip_sigma=0.0)
    result = cond.run(df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"],
                      config=cfg)
    assert result.report.n_outliers_clipped == 0
    # Outliers survive
    assert result.y_train.max() > 1000


# ---------------------------------------------------------------------------
# NaN fill
# ---------------------------------------------------------------------------
def test_nan_fill_eliminates_all_nan():
    df = _make_df(n=500, with_nans=20)
    cond = DataConditioner()
    result = cond.run(df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"])
    assert not np.isnan(result.u_train).any()
    assert not np.isnan(result.y_train).any()
    assert result.report.n_nan_filled >= 20


# ---------------------------------------------------------------------------
# Segment selection
# ---------------------------------------------------------------------------
def test_segment_selection_keeps_only_named_window():
    df = _make_df(n=1000)
    # Window covers samples [200, 400) -> 200 samples
    seg = Segment(
        name="test1",
        start="2026-04-09 08:00:00" + "",   # placeholder; we use index ts below
    )
    # Actually pull the timestamps from the index for clarity
    seg.start = df.index[200]
    seg.end = df.index[399]

    cond = DataConditioner()
    result = cond.run(
        df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"],
        segments=[seg],
    )
    assert result.u_train.shape[0] == 200
    assert result.report.n_segments == 1


def test_excluded_range_punches_holes():
    df = _make_df(n=1000)
    seg = Segment(name="test1", start=df.index[100], end=df.index[599])
    # Excluded ranges remove [200..299] (100 samples)
    seg.excluded_ranges = [(df.index[200], df.index[299])]
    cond = DataConditioner()
    result = cond.run(
        df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"],
        segments=[seg],
    )
    assert result.report.n_excluded_samples == 100
    assert result.u_train.shape[0] == 500 - 100


def test_multiple_segments_concatenate():
    df = _make_df(n=1000)
    seg1 = Segment(name="A", start=df.index[100], end=df.index[199])  # 100 samples
    seg2 = Segment(name="B", start=df.index[400], end=df.index[549])  # 150 samples
    cond = DataConditioner()
    result = cond.run(
        df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"],
        segments=[seg1, seg2],
    )
    assert result.u_train.shape[0] == 250
    assert result.report.n_segments == 2


# ---------------------------------------------------------------------------
# Quality column
# ---------------------------------------------------------------------------
def test_quality_column_drops_bad_rows():
    df = _make_df(n=500, with_quality=True)
    cond = DataConditioner()
    cfg = ConditioningConfig(quality_col="QC", quality_good_value="GOOD")
    result = cond.run(
        df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"], config=cfg)
    # Every 50th of 500 = 10 BAD samples
    assert result.report.n_bad_quality == 10
    assert result.u_train.shape[0] == 490


# ---------------------------------------------------------------------------
# Resample
# ---------------------------------------------------------------------------
def test_resample_downsamples_to_uniform_period():
    df = _make_df(n=600)   # 600 samples at 60s -> 10 hours
    cond = DataConditioner()
    cfg = ConditioningConfig(resample_period_sec=300.0)  # 5 min
    result = cond.run(
        df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"], config=cfg)
    # 10 hours / 5 min = 120 samples (give or take edge)
    assert 110 < result.u_train.shape[0] < 130


def test_resample_skipped_when_no_datetime_index():
    df = _make_df(n=500, with_dt_index=False)
    cond = DataConditioner()
    cfg = ConditioningConfig(resample_period_sec=300.0)
    result = cond.run(
        df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"], config=cfg)
    assert result.report.n_resampled_to is None
    assert any("resample" in n for n in result.report.notes)


# ---------------------------------------------------------------------------
# Hold-out split
# ---------------------------------------------------------------------------
def test_holdout_carves_off_tail():
    df = _make_df(n=1000)
    cond = DataConditioner()
    cfg = ConditioningConfig(holdout_fraction=0.2)
    result = cond.run(
        df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"], config=cfg)
    assert result.u_train.shape[0] == 800
    assert result.u_holdout is not None
    assert result.u_holdout.shape[0] == 200
    assert result.y_holdout.shape[0] == 200
    assert result.report.n_holdout == 200


def test_holdout_zero_means_no_split():
    df = _make_df(n=500)
    cond = DataConditioner()
    result = cond.run(df, ["FIC101_SP", "FIC102_SP"], ["TI201", "FI201"])
    assert result.u_holdout is None
    assert result.y_holdout is None
    assert result.report.n_holdout == 0
