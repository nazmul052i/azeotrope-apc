"""Round-trip tests for the .apcident project file format."""
from __future__ import annotations

import os

import pytest

from azeoapc.identification import (
    ConditioningConfig, IdentConfig, IdentMethod, IdentProject,
    IdentProjectMetadata, Segment, SmoothMethod, TagAssignment,
    load_ident_project, save_ident_project,
)


def _make_project() -> IdentProject:
    p = IdentProject()
    p.metadata = IdentProjectMetadata(
        name="C-301 Furnace",
        author="N. Hasan",
        notes="First step test after turnaround",
    )
    p.data_source_path = "step_test_2026_04.csv"
    p.timestamp_col = "Time"
    p.segments = [
        Segment(
            name="MV1 step",
            start="2026-04-09T08:30:00",
            end="2026-04-09T11:00:00",
        ),
        Segment(
            name="MV2 step",
            start="2026-04-09T13:00:00",
            end="2026-04-09T15:30:00",
            excluded_ranges=[("2026-04-09T14:15:00", "2026-04-09T14:25:00")],
        ),
    ]
    p.tag_assignments = [
        TagAssignment(column="FIC101", role="MV", controller_tag="FIC-101.SP"),
        TagAssignment(column="FIC102", role="MV", controller_tag="FIC-102.SP"),
        TagAssignment(column="TI201",  role="CV", controller_tag="TI-201.PV"),
        TagAssignment(column="TI202",  role="CV", controller_tag="TI-202.PV"),
        TagAssignment(column="QC",     role="Ignore"),
    ]
    p.conditioning = ConditioningConfig(
        resample_period_sec=60.0,
        clip_sigma=3.5,
        holdout_fraction=0.2,
    )
    p.ident = IdentConfig(
        n_coeff=80, dt=60.0, method=IdentMethod.RIDGE,
        smooth=SmoothMethod.PIPELINE, ridge_alpha=0.5,
    )
    p.last_bundle_path = "c301_furnace.apcmodel"
    return p


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------
def test_save_load_round_trip(tmp_path):
    p = _make_project()
    out = str(tmp_path / "test.apcident")
    save_ident_project(p, out)
    assert os.path.exists(out)

    p2 = load_ident_project(out)
    assert p2.metadata.name == "C-301 Furnace"
    assert p2.metadata.author == "N. Hasan"
    assert p2.metadata.notes == "First step test after turnaround"
    assert p2.metadata.created   # populated by save
    assert p2.metadata.modified

    assert p2.data_source_path == "step_test_2026_04.csv"
    assert p2.timestamp_col == "Time"

    assert len(p2.segments) == 2
    assert p2.segments[0].name == "MV1 step"
    assert p2.segments[1].name == "MV2 step"
    assert len(p2.segments[1].excluded_ranges) == 1
    assert p2.segments[1].excluded_ranges[0][0] == "2026-04-09T14:15:00"

    assert len(p2.tag_assignments) == 5
    assert p2.tag_assignments[0].column == "FIC101"
    assert p2.tag_assignments[0].role == "MV"
    assert p2.tag_assignments[0].controller_tag == "FIC-101.SP"

    # Convenience accessors
    assert p2.mv_columns() == ["FIC101", "FIC102"]
    assert p2.cv_columns() == ["TI201", "TI202"]
    assert p2.controller_tag_for("TI201") == "TI-201.PV"

    assert p2.conditioning.resample_period_sec == 60.0
    assert p2.conditioning.clip_sigma == 3.5
    assert p2.conditioning.holdout_fraction == 0.2

    assert p2.ident.n_coeff == 80
    assert p2.ident.method == IdentMethod.RIDGE
    assert p2.ident.smooth == SmoothMethod.PIPELINE
    assert p2.ident.ridge_alpha == 0.5

    assert p2.last_bundle_path == "c301_furnace.apcmodel"


def test_modified_timestamp_updates_on_each_save(tmp_path):
    p = _make_project()
    out = str(tmp_path / "ts.apcident")
    save_ident_project(p, out)
    first = p.metadata.modified

    import time
    time.sleep(1.1)  # ISO timestamps are second-precision

    save_ident_project(p, out)
    second = p.metadata.modified
    assert second > first


def test_created_timestamp_preserved_across_saves(tmp_path):
    p = _make_project()
    out = str(tmp_path / "cts.apcident")
    save_ident_project(p, out)
    created_1 = p.metadata.created
    save_ident_project(p, out)
    assert p.metadata.created == created_1


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_ident_project(str(tmp_path / "nope.apcident"))


def test_empty_project_round_trips(tmp_path):
    p = IdentProject()
    out = str(tmp_path / "empty.apcident")
    save_ident_project(p, out)
    p2 = load_ident_project(out)
    assert p2.segments == []
    assert p2.tag_assignments == []
    assert p2.metadata.schema_version == 1


def test_path_rebase_on_save_as(tmp_path):
    """Save As to a different directory should rewrite relative file refs."""
    # First save in dir A
    dir_a = tmp_path / "projA"
    dir_a.mkdir()
    # Make a fake CSV next to it so the path resolves
    csv_a = dir_a / "data.csv"
    csv_a.write_text("dummy")

    p = _make_project()
    p.data_source_path = "data.csv"
    p.last_bundle_path = ""
    save_ident_project(p, str(dir_a / "x.apcident"))

    # Sanity: file ref still "data.csv" because old==new
    loaded = load_ident_project(str(dir_a / "x.apcident"))
    assert loaded.data_source_path == "data.csv"

    # Save As to a sibling dir
    dir_b = tmp_path / "projB"
    dir_b.mkdir()
    save_ident_project(loaded, str(dir_b / "x.apcident"))

    # The reference should now point UP one and back to projA
    loaded_b = load_ident_project(str(dir_b / "x.apcident"))
    # path should resolve to the original CSV
    resolved = os.path.normpath(os.path.join(
        os.path.dirname(loaded_b.source_path), loaded_b.data_source_path))
    assert os.path.normpath(str(csv_a)) == resolved
