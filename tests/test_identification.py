"""Comprehensive test suite for the azeoapc.identification package.

Covers all 25+ modules with edge cases, round-trip verification,
and integration tests.

Run: pytest tests/test_identification.py -v
"""
import os
import tempfile

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_df():
    """Small synthetic step-test DataFrame."""
    np.random.seed(42)
    N = 500
    idx = pd.date_range("2026-01-01", periods=N, freq="60s")
    u1 = np.zeros(N)
    u1[50:] = 1.0   # step at t=50
    u2 = np.zeros(N)
    u2[100:] = -0.5  # step at t=100
    # Simple FOPTD response
    y1 = np.zeros(N)
    y2 = np.zeros(N)
    for k in range(1, N):
        y1[k] = 0.95 * y1[k-1] + 0.05 * u1[max(0, k-3)]
        y2[k] = 0.97 * y2[k-1] + 0.03 * (u1[max(0, k-5)] - 0.5 * u2[max(0, k-2)])
    y1 += np.random.randn(N) * 0.01
    y2 += np.random.randn(N) * 0.01
    return pd.DataFrame({"MV1": u1, "MV2": u2, "CV1": y1, "CV2": y2}, index=idx)


@pytest.fixture
def u_y(sample_df):
    """Numpy arrays for identification."""
    u = sample_df[["MV1", "MV2"]].to_numpy()
    y = sample_df[["CV1", "CV2"]].to_numpy()
    return u, y


# ===========================================================================
# Tier 1: Data Conditioning
# ===========================================================================
class TestDataConditioning:
    def test_cutoff_detection(self):
        from azeoapc.identification import detect_cutoff_violations
        vals = np.array([1, 2, 3, 100, 4, 5], dtype=float)
        bad = detect_cutoff_violations(vals, upper=10, lower=0)
        assert bad[3] is True or bad[3] == True
        assert bad[0] is False or bad[0] == False

    def test_flatline_detection(self):
        from azeoapc.identification import detect_flatline
        vals = np.array([1]*20 + [2], dtype=float)
        flat = detect_flatline(vals, threshold=0.1, period=5)
        assert flat.sum() > 0

    def test_spike_detection(self):
        from azeoapc.identification import detect_spikes
        vals = np.array([1, 1, 1, 100, 1, 1, 1], dtype=float)
        spikes = detect_spikes(vals, threshold=10, reclassify_period=3)
        assert spikes.sum() > 0

    def test_replace_bad_data_interpolate(self):
        from azeoapc.identification import replace_bad_data, BadDataMethod
        vals = np.array([1.0, 2.0, 0.0, 4.0, 5.0])
        bad = np.array([False, False, True, False, False])
        rep, n_r, n_u = replace_bad_data(vals, bad, BadDataMethod.INTERPOLATE)
        assert abs(rep[2] - 3.0) < 0.1

    def test_auto_configure(self):
        from azeoapc.identification import auto_configure_conditioning
        df = pd.DataFrame({"A": np.random.randn(200) + 50})
        cfg = auto_configure_conditioning(df)
        assert "A" in cfg.variables

    def test_condition_dataframe(self):
        from azeoapc.identification import (
            auto_configure_conditioning, condition_dataframe_engine,
        )
        df = pd.DataFrame({"A": np.random.randn(100)})
        cfg = auto_configure_conditioning(df)
        df_out, report = condition_dataframe_engine(df, cfg)
        assert len(df_out) == len(df)


class TestSteadyState:
    def test_ssd(self, sample_df):
        from azeoapc.identification import compute_ssd, auto_configure_ssd
        cfg = auto_configure_ssd(sample_df, columns=["CV1"])
        result = compute_ssd(sample_df, cfg)
        assert result.n_samples == len(sample_df)
        assert 0 <= result.steady_fraction <= 1.0


class TestResampling:
    def test_resample(self, sample_df):
        from azeoapc.identification import resample_dataframe
        df_r = resample_dataframe(sample_df, period_sec=120)
        assert len(df_r) < len(sample_df)

    def test_analyze_rates(self, sample_df):
        from azeoapc.identification import analyze_resample_rates, suggest_resample_rate
        analysis = analyze_resample_rates(sample_df, candidates=[60, 120, 300])
        suggestion = suggest_resample_rate(analysis)
        assert len(analysis.aggregate) > 0


class TestDataRules:
    def test_exclusion_rule(self):
        from azeoapc.identification import ExclusionRule, apply_exclusion_rules
        df = pd.DataFrame({"T": [100, 200, 50, 300, 150]})
        rules = [ExclusionRule(tag="T", operator="<", value=100)]
        df_out, n_d, n_n = apply_exclusion_rules(df, rules)
        assert len(df_out) == 4


class TestDynamicFilter:
    def test_first_order(self):
        from azeoapc.identification import first_order_filter
        x = np.zeros(20)
        x[5:] = 1.0
        y = first_order_filter(x, tau=3.0, dt=1.0)
        assert y[-1] > 0.9
        assert y[5] < 0.5


class TestTransforms:
    def test_log_roundtrip(self):
        from azeoapc.identification import OutputTransform, TransformMethod
        tf = OutputTransform(method=TransformMethod.LOG, shift=1.0)
        y = np.array([1.0, 10.0, 100.0])
        assert np.allclose(tf.inverse(tf.forward(y)), y, atol=1e-10)

    def test_pwln_roundtrip(self):
        from azeoapc.identification import OutputTransform, TransformMethod
        tf = OutputTransform(
            method=TransformMethod.PWLN,
            breakpoints=[0, 25, 50, 75, 100],
            slopes=[0.5, 1.0, 1.5, 2.0])
        y = np.array([10.0, 30.0, 60.0, 90.0])
        assert np.allclose(tf.inverse(tf.forward(y)), y, atol=0.01)

    def test_auto_select(self):
        from azeoapc.identification import auto_select_transform
        y = np.exp(np.random.randn(200))  # log-normal
        tf = auto_select_transform(y)
        assert tf.method is not None


# ===========================================================================
# Tier 2: Identification
# ===========================================================================
class TestFIRIdent:
    def test_dls(self, u_y):
        from azeoapc.identification import FIRIdentifier, IdentConfig, IdentMethod
        u, y = u_y
        cfg = IdentConfig(n_coeff=30, dt=60.0, method=IdentMethod.DLS)
        result = FIRIdentifier(cfg).identify(u, y)
        assert result.ny == 2
        assert result.nu == 2
        assert len(result.fits) == 4  # 2x2

    def test_ridge(self, u_y):
        from azeoapc.identification import FIRIdentifier, IdentConfig, IdentMethod
        u, y = u_y
        cfg = IdentConfig(n_coeff=30, dt=60.0, method=IdentMethod.RIDGE)
        result = FIRIdentifier(cfg).identify(u, y)
        assert result.condition_number > 0

    def test_cor(self, u_y):
        from azeoapc.identification import FIRIdentifier, IdentConfig, IdentMethod
        u, y = u_y
        cfg = IdentConfig(n_coeff=30, dt=60.0, method=IdentMethod.COR)
        result = FIRIdentifier(cfg).identify(u, y)
        assert result.ny == 2


class TestSubspaceIdent:
    def test_n4sid(self, u_y):
        from azeoapc.identification import SubspaceIdentifier, SubspaceConfig
        u, y = u_y
        cfg = SubspaceConfig(f=15, dt=60.0)
        result = SubspaceIdentifier(cfg).identify(u, y)
        assert result.nx > 0
        assert result.A.shape == (result.nx, result.nx)

    def test_identify_ss(self, u_y):
        from azeoapc.identification import identify_ss
        u, y = u_y
        result = identify_ss(u, y, method="n4sid", f=10, dt=60.0)
        assert result.is_stable or not result.is_stable  # just doesn't crash

    def test_wood_berry(self):
        from azeoapc.identification import WoodBerrySimulator, identify_ss
        wb = WoodBerrySimulator(dt=1.0, noise_std=0.05)
        u = wb.generate_prbs(500, seed=42)
        y = wb.simulate(u, seed=42)
        result = identify_ss(u, y, f=15, dt=1.0)
        assert result.ny == 2 and result.nu == 2

    def test_expert_mode(self, u_y):
        from azeoapc.identification import SubspaceIdentifier, SubspaceConfig, SubspaceMethod
        u, y = u_y
        cfg = SubspaceConfig(f=10, dt=60.0, differencing=True, oversampling_ratio=2)
        result = SubspaceIdentifier(cfg).identify(u, y)
        assert result.nx > 0


# ===========================================================================
# Tier 3: Curve Operations & Assembly
# ===========================================================================
class TestCurveOps:
    def test_shift(self):
        from azeoapc.identification import apply_op, CurveOp, create_firstorder
        step = create_firstorder(60, gain=1.0, tau=10.0, dt=1.0)
        shifted = apply_op(CurveOp.SHIFT, step, shift=5)
        assert shifted[0] == 0.0
        # After shift, the value at index 10 should match original at index 5
        assert abs(shifted[10] - step[5]) < 1e-10

    def test_gain(self):
        from azeoapc.identification import apply_op, CurveOp, create_firstorder
        step = create_firstorder(60, gain=1.0, tau=10.0, dt=1.0)
        gained = apply_op(CurveOp.GAIN, step, gain=2.0)
        assert abs(gained[-1] - 2.0 * step[-1]) < 1e-10

    def test_zero_unity(self):
        from azeoapc.identification import apply_op, CurveOp, create_firstorder
        step = create_firstorder(60, gain=1.0, tau=10.0, dt=1.0)
        assert apply_op(CurveOp.ZERO, step).sum() == 0.0
        assert apply_op(CurveOp.UNITY, step)[-1] == 1.0

    def test_all_ops_dont_crash(self):
        from azeoapc.identification import apply_op, CurveOp, create_firstorder
        step = create_firstorder(60, gain=1.0, tau=10.0, dt=1.0)
        for op in [CurveOp.SHIFT, CurveOp.GAIN, CurveOp.GSCALE,
                   CurveOp.MULTIPLY, CurveOp.RATE, CurveOp.RSCALE,
                   CurveOp.FIRSTORDER, CurveOp.SECONDORDER,
                   CurveOp.LEADLAG, CurveOp.ROTATE,
                   CurveOp.ZERO, CurveOp.UNITY]:
            result = apply_op(op, step, shift=3, gain=2.0, target_gain=1.0,
                            scalar=1.5, factor=1.0, tau=5.0, tau1=3.0,
                            tau2=2.0, tau_lead=3.0, tau_lag=5.0,
                            dt=1.0, angle_deg=10.0)
            assert len(result) == len(step)


class TestModelAssembly:
    def test_assemble(self):
        from azeoapc.identification import ModelAssembler
        from azeoapc.identification.curve_operations import create_firstorder
        sr = np.zeros((2, 60, 2))
        sr[0, :, 0] = create_firstorder(60, 1.0, 10.0, 1.0)
        sr[0, :, 1] = create_firstorder(60, -0.5, 15.0, 1.0)
        sr[1, :, 0] = create_firstorder(60, 0.3, 8.0, 1.0)
        sr[1, :, 1] = create_firstorder(60, 0.8, 12.0, 1.0)

        asm = ModelAssembler(["CV1", "CV2"], ["MV1", "MV2"], n_coeff=60)
        asm.add_candidate("t1", sr, fit_r2=np.array([0.9, 0.8]))
        asm.auto_select()
        model = asm.build()
        assert model.step_response.shape == (2, 60, 2)
        assert model.gain_matrix.shape == (2, 2)


# ===========================================================================
# Tier 4: Analysis Tools
# ===========================================================================
class TestCrossCorrelation:
    def test_analyze(self, sample_df):
        from azeoapc.identification import analyze_cross_correlation
        result = analyze_cross_correlation(sample_df, ["MV1", "MV2"])
        assert "MV1" in result.auto_correlations
        assert result.worst_grade in ["IDEAL", "ACCEPTABLE", "POOR", "UNACCEPTABLE"]


class TestModelUncertainty:
    def test_analyze(self):
        from azeoapc.identification import analyze_uncertainty
        from azeoapc.identification.curve_operations import create_firstorder
        sr = np.zeros((2, 60, 2))
        sr[0, :, 0] = create_firstorder(60, 1.0, 10.0, 1.0)
        sr[1, :, 1] = create_firstorder(60, 0.5, 15.0, 1.0)
        report = analyze_uncertainty(sr, dt=1.0)
        assert len(report.channels) == 4
        assert all(ch.overall_grade in "ABCD" for ch in report.channels)


class TestGainMatrixAnalysis:
    def test_analyze(self):
        from azeoapc.identification import analyze_gain_matrix, compute_rga
        G = np.array([[1.0, -0.5], [0.3, 0.8]])
        report = analyze_gain_matrix(G, ["CV1", "CV2"], ["MV1", "MV2"])
        assert report.condition_number > 0
        rga = compute_rga(G)
        assert rga is not None
        assert rga.shape == (2, 2)


# ===========================================================================
# Tier 5: Multi-trial, Bad Slices, Ramp CV
# ===========================================================================
class TestMultiTrial:
    def test_define_trials(self):
        from azeoapc.identification import define_trials
        trials = define_trials({"n_coeff": 60}, vary={"n_coeff": [40, 60, 80]})
        assert len(trials) == 3

    def test_run_trials(self, u_y):
        from azeoapc.identification import define_trials, run_trials_fir
        u, y = u_y
        trials = define_trials(
            {"n_coeff": 30, "dt": 60.0, "method": "dls",
             "smooth": "none", "detrend": True, "remove_mean": True,
             "prewhiten": False},
            vary={"n_coeff": [20, 30]})
        comp = run_trials_fir(u, y, trials)
        assert len(comp.trials) == 2
        assert comp.best_trial is not None


class TestBadSlices:
    def test_interpolate(self):
        from azeoapc.identification import BadSlice, apply_bad_slices
        df = pd.DataFrame({"V": np.arange(100, dtype=float)})
        slices = [BadSlice(start=10, end=20, mode="interpolate")]
        df_out, report = apply_bad_slices(df, slices)
        assert len(df_out) == 100  # rows preserved
        assert report.n_interpolated_samples > 0

    def test_exclude(self):
        from azeoapc.identification import BadSlice, apply_bad_slices
        df = pd.DataFrame({"V": np.arange(100, dtype=float)})
        slices = [BadSlice(start=10, end=20, mode="exclude")]
        df_out, report = apply_bad_slices(df, slices)
        assert len(df_out) < 100
        assert report.n_excluded_rows > 0


class TestRampCV:
    def test_detect_ramp(self):
        from azeoapc.identification import detect_cv_type, CVType
        y = np.arange(200, dtype=float) + np.random.randn(200) * 0.1
        assert detect_cv_type(y) == CVType.RAMP

    def test_detect_normal(self):
        from azeoapc.identification import detect_cv_type, CVType
        y = np.random.randn(200)
        assert detect_cv_type(y) == CVType.NONE

    def test_typical_move_scale(self):
        from azeoapc.identification import typical_move_scale
        sr = np.ones((2, 60, 2))
        tm = np.array([5.0, 3.0])
        scaled = typical_move_scale(sr, tm)
        assert scaled[0, 0, 0] == 5.0
        assert scaled[0, 0, 1] == 3.0


# ===========================================================================
# Tier 6: Smart Config, Scorecard, Templates
# ===========================================================================
class TestSmartConfig:
    def test_smart_configure(self, sample_df):
        from azeoapc.identification import smart_configure
        report = smart_configure(sample_df, ["MV1", "MV2"], ["CV1", "CV2"])
        assert report.n_coeff > 0
        assert report.dt > 0
        assert report.method in ("dls", "ridge")


class TestScorecard:
    def test_build_scorecard(self, u_y):
        from azeoapc.identification import (
            FIRIdentifier, IdentConfig, IdentMethod,
            DataConditioner, ConditioningConfig,
            build_scorecard, Grade,
        )
        u, y = u_y
        cfg = IdentConfig(n_coeff=30, dt=60.0, method=IdentMethod.DLS)
        result = FIRIdentifier(cfg).identify(u, y)
        scorecard = build_scorecard(ident_result=result, mv_cols=["MV1", "MV2"],
                                     cv_cols=["CV1", "CV2"])
        assert scorecard.overall_grade in (Grade.GREEN, Grade.YELLOW, Grade.RED)
        assert len(scorecard.categories) >= 2


class TestProcessTemplates:
    def test_list_templates(self):
        from azeoapc.identification import list_templates
        templates = list_templates()
        assert "HEATER" in templates
        assert "DISTILLATION_COLUMN" in templates
        assert len(templates) >= 5

    def test_get_template(self):
        from azeoapc.identification import get_template
        t = get_template("heater")
        assert t.suggested_n_coeff > 0
        assert len(t.mv_defaults) > 0
        assert len(t.cv_defaults) > 0


# ===========================================================================
# Tier 7: Report Generation, DMC Import, Batch
# ===========================================================================
class TestReportGenerator:
    def test_generate_html(self, u_y):
        from azeoapc.identification import (
            FIRIdentifier, IdentConfig, IdentMethod,
            IdentProject,
        )
        from azeoapc.identification.report_generator import generate_html_report
        u, y = u_y
        cfg = IdentConfig(n_coeff=30, dt=60.0, method=IdentMethod.DLS)
        result = FIRIdentifier(cfg).identify(u, y)
        project = IdentProject()
        html = generate_html_report(project=project, ident_result=result)
        assert "<html" in html.lower()
        assert "Gain Matrix" in html or "gain" in html.lower()


class TestBatchExecution:
    def test_generate_miso(self):
        from azeoapc.identification import generate_miso_cases, IdentConfig
        cfg = IdentConfig(n_coeff=30, dt=60.0)
        cases = generate_miso_cases(
            ["MV1", "MV2"], ["CV1", "CV2"], cfg)
        assert len(cases) == 2  # one case per CV

    def test_run_batch(self, u_y):
        from azeoapc.identification import (
            generate_miso_cases, run_batch, IdentConfig,
        )
        u, y = u_y
        cfg = IdentConfig(n_coeff=30, dt=60.0)
        cases = generate_miso_cases(["MV1", "MV2"], ["CV1", "CV2"], cfg)
        report = run_batch(cases, u, y)
        assert report.n_success >= 0


# ===========================================================================
# Tier 8: Calculated Vectors
# ===========================================================================
class TestCalculatedVectors:
    def test_simple_expression(self):
        from azeoapc.identification import evaluate_expression
        df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        result = evaluate_expression("{A} + {B}", df)
        assert list(result) == [5, 7, 9]

    def test_rolling(self):
        from azeoapc.identification import evaluate_expression
        df = pd.DataFrame({"A": np.arange(20, dtype=float)})
        result = evaluate_expression("rolling_mean({A}, 5)", df)
        assert len(result) == 20

    def test_unsafe_rejected(self):
        from azeoapc.identification import evaluate_expression
        df = pd.DataFrame({"A": [1, 2, 3]})
        with pytest.raises(ValueError):
            evaluate_expression("__import__('os')", df)


# ===========================================================================
# Tier 9: Integration Tests
# ===========================================================================
class TestIntegration:
    def test_full_pipeline(self, sample_df):
        """Full pipeline: condition -> identify -> validate -> export."""
        from azeoapc.identification import (
            DataConditioner, ConditioningConfig, Segment,
            FIRIdentifier, IdentConfig, IdentMethod,
            bundle_from_ident, save_model_bundle, load_model_bundle,
        )

        # Condition
        cond = DataConditioner().run(
            sample_df, ["MV1", "MV2"], ["CV1", "CV2"],
            segments=[Segment("full")],
            config=ConditioningConfig(clip_sigma=4.0, holdout_fraction=0.2))
        assert cond.u_train.shape[1] == 2
        assert cond.y_train.shape[1] == 2

        # Identify
        cfg = IdentConfig(n_coeff=30, dt=60.0, method=IdentMethod.DLS)
        result = FIRIdentifier(cfg).identify(cond.u_train, cond.y_train)
        assert result.ny == 2 and result.nu == 2

        # Export bundle
        bundle = bundle_from_ident(
            result, name="test", mv_tags=["MV1", "MV2"],
            cv_tags=["CV1", "CV2"])
        assert bundle.fir.shape == (2, 30, 2)

        # Save and reload
        with tempfile.NamedTemporaryFile(suffix=".apcmodel", delete=False) as f:
            path = f.name
        try:
            save_model_bundle(bundle, path)
            loaded = load_model_bundle(path)
            assert loaded.ny == 2 and loaded.nu == 2
            assert np.allclose(loaded.fir, bundle.fir)
        finally:
            os.unlink(path)

    def test_subspace_pipeline(self, u_y):
        """Subspace identify -> export bundle."""
        from azeoapc.identification import (
            identify_ss, bundle_from_ident,
        )
        u, y = u_y
        result = identify_ss(u, y, method="n4sid", f=10, dt=60.0)

        # bundle_from_ident should auto-detect SubspaceResult
        bundle = bundle_from_ident(
            result, name="test_ss",
            mv_tags=["MV1", "MV2"], cv_tags=["CV1", "CV2"])
        assert bundle.A is not None
        assert bundle.fir is not None


# ===========================================================================
# Edge cases
# ===========================================================================
class TestEdgeCases:
    def test_empty_dataframe(self):
        from azeoapc.identification import auto_configure_conditioning
        df = pd.DataFrame()
        cfg = auto_configure_conditioning(df)
        assert len(cfg.variables) == 0

    def test_single_row(self):
        from azeoapc.identification import detect_flatline
        vals = np.array([1.0])
        flat = detect_flatline(vals, threshold=0.1, period=5)
        assert flat.sum() == 0

    def test_all_nan_column(self):
        from azeoapc.identification import auto_configure_conditioning
        df = pd.DataFrame({"A": [np.nan] * 100})
        cfg = auto_configure_conditioning(df)
        # Should not crash, may skip the column
        assert True

    def test_constant_column(self):
        from azeoapc.identification import detect_cv_type, CVType
        y = np.ones(200)
        result = detect_cv_type(y)
        assert result == CVType.NONE

    def test_very_short_data(self):
        from azeoapc.identification import FIRIdentifier, IdentConfig
        u = np.random.randn(15, 1)
        y = np.random.randn(15, 1)
        cfg = IdentConfig(n_coeff=5, dt=1.0)
        result = FIRIdentifier(cfg).identify(u, y)
        assert result.n_coeff == 5
