"""HTML report generation for identification results.

Generates a comprehensive, print-ready HTML report summarising an
identification job: project metadata, data conditioning, tag assignments,
identification configuration, gain matrix, per-channel fit metrics,
model quality scorecard, and smart-config rationale.

No Qt dependencies -- pure Python + numpy + standard library only.

Usage::

    html = generate_html_report(project, ident_result,
                                cond_result=cond, scorecard=sc)
    save_report(html, "report.html", open_browser=True)
"""
from __future__ import annotations

import datetime
import html as html_mod
import os
import webbrowser
from typing import Any, List, Optional

import numpy as np


# ── Color palette (DeltaV Live Silver) ──────────────────────────────
_BG = "#ECECEC"
_TEXT = "#1A1A1A"
_BLUE = "#0066CC"
_GREEN = "#2E8B57"
_ORANGE = "#D9822B"
_RED = "#C0392B"
_BORDER = "#B0B0B0"
_HEADER_BG = "#D8D8D8"
_WHITE = "#FFFFFF"


# =====================================================================
#  Public API
# =====================================================================
def generate_html_report(
    project,
    ident_result,
    cond_result=None,
    scorecard=None,
    smart_report=None,
    output_path=None,
) -> str:
    """Generate a comprehensive HTML identification report.

    Parameters
    ----------
    project : IdentProject
        The identification project (metadata, tag assignments, configs).
    ident_result : IdentResult or SubspaceResult
        The identification result (gain matrix, fits, etc.).
    cond_result : ConditioningResult, optional
        Conditioning pipeline result (data quality stats).
    scorecard : ModelScorecard, optional
        Model quality scorecard with traffic-light grades.
    smart_report : SmartConfigReport, optional
        Auto-configuration report with rationale.
    output_path : str, optional
        If given, the HTML is written to this file path.

    Returns
    -------
    str
        The complete HTML document as a string.
    """
    sections = []
    sections.append(_section_project_info(project))
    sections.append(_section_data_summary(project, cond_result))
    sections.append(_section_tag_assignments(project))
    sections.append(_section_ident_config(project, ident_result))
    sections.append(_section_gain_matrix(project, ident_result))
    sections.append(_section_channel_fits(project, ident_result))
    sections.append(_section_scorecard(scorecard))
    sections.append(_section_smart_config(smart_report))

    body = "\n".join(s for s in sections if s)
    report_html = _wrap_document(body, _safe(project, "metadata.name", "Identification Report"))

    if output_path is not None:
        save_report(report_html, output_path)

    return report_html


def save_report(html: str, path: str, open_browser: bool = False) -> None:
    """Write the HTML report to a file.

    Parameters
    ----------
    html : str
        The HTML content.
    path : str
        Destination file path.
    open_browser : bool
        If True, open the saved file in the default web browser.
    """
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(html)

    if open_browser:
        webbrowser.open(f"file:///{abs_path.replace(os.sep, '/')}")


# =====================================================================
#  Helpers
# =====================================================================
def _esc(value: Any) -> str:
    """HTML-escape a value, returning 'N/A' for None."""
    if value is None:
        return "N/A"
    return html_mod.escape(str(value))


def _safe(obj, dotted_attr: str, default: Any = None) -> Any:
    """Safely traverse dotted attribute paths.  Returns *default* on any failure."""
    try:
        parts = dotted_attr.split(".")
        cur = obj
        for p in parts:
            cur = getattr(cur, p)
        return cur if cur is not None else default
    except Exception:
        return default


def _fmt(value, fmt: str = ".4f") -> str:
    """Format a numeric value, returning 'N/A' for None/NaN."""
    if value is None:
        return "N/A"
    try:
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return "N/A"
        return format(v, fmt)
    except (TypeError, ValueError):
        return _esc(value)


def _gain_color(value: float) -> str:
    """Return a background color for a gain matrix cell."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _WHITE
    if np.isnan(v) or abs(v) < 1e-10:
        return _WHITE
    return "#D5F5E3" if v > 0 else "#FDEBD0"  # light green / light orange


def _r2_color(r2: float) -> str:
    """Color-code an R-squared value."""
    try:
        v = float(r2)
    except (TypeError, ValueError):
        return _WHITE
    if v >= 0.9:
        return "#D5F5E3"
    if v >= 0.7:
        return "#FEF9E7"
    return "#FADBD8"


def _grade_color(grade: str) -> str:
    """Map a scorecard grade to a color."""
    g = (grade or "").upper()
    if g == "GREEN":
        return _GREEN
    if g == "YELLOW":
        return _ORANGE
    if g == "RED":
        return _RED
    return _TEXT


def _grade_badge(grade: str) -> str:
    """Render a grade as a styled badge."""
    color = _grade_color(grade)
    label = _esc(grade)
    return (
        f'<span style="display:inline-block; padding:2px 10px; '
        f'border-radius:3px; color:{_WHITE}; background:{color}; '
        f'font-weight:bold; font-size:0.85em;">{label}</span>'
    )


# =====================================================================
#  Document wrapper
# =====================================================================
def _wrap_document(body: str, title: str) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)} - Identification Report</title>
<style>
  @media print {{
    body {{ background: white; }}
    .page-break {{ page-break-before: always; }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Segoe UI", Calibri, Arial, sans-serif;
    font-size: 10pt;
    color: {_TEXT};
    background: {_BG};
    padding: 24px;
    line-height: 1.45;
  }}
  .report-container {{
    max-width: 960px;
    margin: 0 auto;
    background: {_WHITE};
    padding: 32px 40px;
    border: 1px solid {_BORDER};
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }}
  h1 {{
    font-size: 18pt;
    color: {_BLUE};
    border-bottom: 2px solid {_BLUE};
    padding-bottom: 6px;
    margin-bottom: 18px;
  }}
  h2 {{
    font-size: 12pt;
    color: {_BLUE};
    margin-top: 28px;
    margin-bottom: 10px;
    border-bottom: 1px solid {_BORDER};
    padding-bottom: 4px;
  }}
  h3 {{
    font-size: 10pt;
    color: {_TEXT};
    margin-top: 14px;
    margin-bottom: 6px;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 14px;
    font-size: 9pt;
  }}
  th {{
    background: {_HEADER_BG};
    font-weight: 600;
    text-align: left;
    padding: 5px 8px;
    border: 1px solid {_BORDER};
  }}
  td {{
    padding: 4px 8px;
    border: 1px solid {_BORDER};
    vertical-align: top;
  }}
  .meta-table {{ width: auto; }}
  .meta-table td {{ border: none; padding: 2px 12px 2px 0; }}
  .meta-table td:first-child {{ font-weight: 600; color: #555; white-space: nowrap; }}
  .gain-cell {{ text-align: right; font-family: "Consolas", "Courier New", monospace; }}
  .fit-cell {{ text-align: right; }}
  .note {{ color: #777; font-style: italic; margin: 6px 0; }}
  .footer {{
    margin-top: 32px;
    padding-top: 10px;
    border-top: 1px solid {_BORDER};
    font-size: 8pt;
    color: #888;
    text-align: center;
  }}
  ul {{ margin: 4px 0 4px 20px; }}
  li {{ margin-bottom: 2px; }}
  .finding {{ margin-left: 16px; }}
  .recommendation {{
    margin-left: 24px;
    color: {_BLUE};
    font-style: italic;
  }}
</style>
</head>
<body>
<div class="report-container">
<h1>{_esc(title)} &mdash; Identification Report</h1>
{body}
<div class="footer">
  Generated by Azeotrope APC Ident &nbsp;|&nbsp; {now}
</div>
</div>
</body>
</html>"""


# =====================================================================
#  Section builders
# =====================================================================
def _section_project_info(project) -> str:
    """Section 1: Project information."""
    meta = _safe(project, "metadata")
    name = _safe(meta, "name", "Untitled")
    author = _safe(meta, "author", "")
    created = _safe(meta, "created", "")
    modified = _safe(meta, "modified", "")
    notes = _safe(meta, "notes", "")
    data_src = _safe(project, "data_source_path", "")
    version = _safe(meta, "apc_ident_version", "")

    rows = [
        ("Project Name", _esc(name)),
        ("Author", _esc(author) if author else "Not specified"),
        ("Created", _esc(created) if created else "N/A"),
        ("Last Modified", _esc(modified) if modified else "N/A"),
        ("Data Source", _esc(data_src) if data_src else "Not specified"),
        ("APC Ident Version", _esc(version) if version else "N/A"),
    ]
    if notes:
        rows.append(("Notes", _esc(notes)))

    trs = "\n".join(f"<tr><td>{label}</td><td>{val}</td></tr>" for label, val in rows)
    return f"""<h2>1. Project Information</h2>
<table class="meta-table">
{trs}
</table>"""


def _section_data_summary(project, cond_result) -> str:
    """Section 2: Data summary."""
    report = _safe(cond_result, "report")
    if report is None:
        return f"""<h2>2. Data Summary</h2>
<p class="note">No conditioning result available.</p>"""

    n_in = _safe(report, "n_rows_in", "N/A")
    n_out = _safe(report, "n_rows_out", "N/A")
    n_seg = _safe(report, "n_segments", "N/A")
    n_nan = _safe(report, "n_nan_filled", 0)
    n_outliers = _safe(report, "n_outliers_clipped", 0)
    n_bad = _safe(report, "n_bad_quality", 0)
    n_holdout = _safe(report, "n_holdout", 0)
    n_excluded = _safe(report, "n_excluded_samples", 0)
    columns = _safe(report, "columns_used", [])

    # Try to extract sample period from conditioning config
    cfg = _safe(project, "conditioning")
    sample_period = _safe(cfg, "resample_period_sec")
    sample_str = f"{sample_period} s" if sample_period else "Original (not resampled)"

    rows = [
        ("Rows In", _esc(n_in)),
        ("Rows Out (conditioned)", _esc(n_out)),
        ("Segments", _esc(n_seg)),
        ("Sample Period", sample_str),
        ("Columns Used", _esc(len(columns)) if columns else "N/A"),
        ("NaN Values Filled", _esc(n_nan)),
        ("Outliers Clipped", _esc(n_outliers)),
        ("Bad-Quality Samples", _esc(n_bad)),
        ("Excluded Samples", _esc(n_excluded)),
        ("Hold-out Samples", _esc(n_holdout)),
    ]

    # Conditioning engine report
    ce_report = _safe(report, "conditioning_engine_report")
    if ce_report is not None:
        total_faults = _safe_call(ce_report, "total_faults", 0)
        if total_faults:
            rows.append(("Sensor Faults Detected", _esc(total_faults)))

    notes = _safe(report, "notes", [])
    notes_html = ""
    if notes:
        items = "\n".join(f"<li>{_esc(n)}</li>" for n in notes)
        notes_html = f"<h3>Notes</h3><ul>{items}</ul>"

    trs = "\n".join(f"<tr><td>{label}</td><td>{val}</td></tr>" for label, val in rows)
    return f"""<h2>2. Data Summary</h2>
<table class="meta-table">
{trs}
</table>
{notes_html}"""


def _safe_call(obj, method_name: str, default: Any = None) -> Any:
    """Call a method on obj, returning default on failure."""
    try:
        m = getattr(obj, method_name, None)
        if callable(m):
            return m()
        return default
    except Exception:
        return default


def _section_tag_assignments(project) -> str:
    """Section 3: Tag assignments table."""
    tags = _safe(project, "tag_assignments", [])
    if not tags:
        return f"""<h2>3. Tag Assignments</h2>
<p class="note">No tag assignments defined.</p>"""

    header = "<tr><th>#</th><th>CSV Column</th><th>Role</th><th>Controller Tag</th></tr>"
    rows = []
    for i, t in enumerate(tags, 1):
        role = _safe(t, "role", "Ignore")
        role_color = {
            "MV": _BLUE,
            "CV": _GREEN,
            "DV": _ORANGE,
        }.get(role, "#777")
        rows.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td>{_esc(_safe(t, 'column', ''))}</td>"
            f'<td style="color:{role_color}; font-weight:600;">{_esc(role)}</td>'
            f"<td>{_esc(_safe(t, 'controller_tag', ''))}</td>"
            f"</tr>"
        )

    return f"""<h2>3. Tag Assignments</h2>
<table>
{header}
{"".join(rows)}
</table>"""


def _section_ident_config(project, ident_result) -> str:
    """Section 4: Identification configuration."""
    # Try project config first, fall back to result config
    cfg = _safe(project, "ident")
    if cfg is None and ident_result is not None:
        cfg = _safe(ident_result, "config")
    if cfg is None:
        return f"""<h2>4. Identification Configuration</h2>
<p class="note">No configuration available.</p>"""

    # Gather parameters -- works for both IdentConfig and SubspaceConfig
    params = []

    # Common FIR params
    n_coeff = _safe(cfg, "n_coeff")
    if n_coeff is not None:
        params.append(("Model Length (n_coeff)", str(n_coeff)))
    dt = _safe(cfg, "dt")
    if dt is not None:
        params.append(("Sample Period (dt)", f"{dt} s"))
        if n_coeff is not None:
            horizon_s = float(n_coeff) * float(dt)
            params.append(("Model Horizon", f"{horizon_s:.0f} s ({horizon_s/60:.1f} min)"))
    method = _safe(cfg, "method")
    if method is not None:
        method_str = method.value if hasattr(method, "value") else str(method)
        params.append(("Method", method_str.upper()))
    ridge = _safe(cfg, "ridge_alpha")
    if ridge is not None:
        params.append(("Ridge Alpha", _fmt(ridge, ".2e")))
    params.append(("Prewhiten", str(_safe(cfg, "prewhiten", False))))
    params.append(("Detrend", str(_safe(cfg, "detrend", True))))
    params.append(("Remove Mean", str(_safe(cfg, "remove_mean", True))))
    conf = _safe(cfg, "confidence_level")
    if conf is not None:
        params.append(("Confidence Level", _fmt(conf, ".2f")))
    smooth = _safe(cfg, "smooth")
    if smooth is not None:
        smooth_str = smooth.value if hasattr(smooth, "value") else str(smooth)
        params.append(("Smoothing", smooth_str))
    lb = _safe(cfg, "ljung_box_lags")
    if lb is not None:
        params.append(("Ljung-Box Lags", str(lb)))

    # Subspace-specific
    nx = _safe(cfg, "nx")
    if nx is not None:
        params.append(("Model Order (nx)", str(nx)))
    f_horizon = _safe(cfg, "f")
    if f_horizon is not None:
        params.append(("Future Horizon (f)", str(f_horizon)))

    # Condition number from result
    cond = _safe(ident_result, "condition_number")
    if cond is not None:
        params.append(("Condition Number", _fmt(cond, ".1f")))

    trs = "\n".join(f"<tr><td>{label}</td><td>{val}</td></tr>" for label, val in params)
    return f"""<h2>4. Identification Configuration</h2>
<table class="meta-table">
{trs}
</table>"""


def _section_gain_matrix(project, ident_result) -> str:
    """Section 5: Steady-state gain matrix with color-coded cells."""
    if ident_result is None:
        return f"""<h2>5. Steady-State Gain Matrix</h2>
<p class="note">No identification result available.</p>"""

    gain = _safe_call(ident_result, "gain_matrix")
    if gain is None:
        gain = _safe(ident_result, "gain_matrix")
    if gain is None:
        return f"""<h2>5. Steady-State Gain Matrix</h2>
<p class="note">Gain matrix not available.</p>"""

    gain = np.atleast_2d(gain)
    ny, nu = gain.shape

    mv_cols = _safe(project, "mv_columns")
    cv_cols = _safe(project, "cv_columns")
    if callable(mv_cols):
        mv_cols = mv_cols()
    if callable(cv_cols):
        cv_cols = cv_cols()
    mv_names = mv_cols if mv_cols else [f"MV{j}" for j in range(nu)]
    cv_names = cv_cols if cv_cols else [f"CV{i}" for i in range(ny)]

    # Header row
    header_cells = "<th></th>" + "".join(f"<th>{_esc(n)}</th>" for n in mv_names)
    header = f"<tr>{header_cells}</tr>"

    # Data rows
    rows = []
    for i in range(ny):
        cells = f"<th>{_esc(cv_names[i] if i < len(cv_names) else f'CV{i}')}</th>"
        for j in range(nu):
            v = gain[i, j]
            bg = _gain_color(v)
            cells += (
                f'<td class="gain-cell" style="background:{bg};">'
                f"{_fmt(v, '+.4f')}</td>"
            )
        rows.append(f"<tr>{cells}</tr>")

    return f"""<h2>5. Steady-State Gain Matrix</h2>
<table>
{header}
{"".join(rows)}
</table>
<p style="font-size:8pt; color:#777;">
  <span style="background:#D5F5E3; padding:1px 6px; border:1px solid {_BORDER};">Positive</span>
  &nbsp;
  <span style="background:#FDEBD0; padding:1px 6px; border:1px solid {_BORDER};">Negative</span>
</p>"""


def _section_channel_fits(project, ident_result) -> str:
    """Section 6: Per-channel fit metrics."""
    if ident_result is None:
        return f"""<h2>6. Channel Fit Metrics</h2>
<p class="note">No identification result available.</p>"""

    cv_cols = _safe(project, "cv_columns")
    if callable(cv_cols):
        cv_cols = cv_cols()
    mv_cols = _safe(project, "mv_columns")
    if callable(mv_cols):
        mv_cols = mv_cols()

    # Try IdentResult.fits (list of ChannelFit)
    fits = _safe(ident_result, "fits")
    if fits:
        return _render_fir_fits(fits, cv_cols, mv_cols)

    # Try SubspaceResult.fit_r2 / fit_rmse / fit_nrmse
    fit_r2 = _safe(ident_result, "fit_r2")
    if fit_r2 is not None:
        return _render_subspace_fits(ident_result, cv_cols)

    return f"""<h2>6. Channel Fit Metrics</h2>
<p class="note">No fit metrics available.</p>"""


def _render_fir_fits(fits, cv_cols, mv_cols) -> str:
    """Render IdentResult.fits (list of ChannelFit) as a table."""
    header = (
        "<tr><th>CV</th><th>MV</th>"
        "<th>R&sup2;</th><th>RMSE</th><th>NRMSE</th>"
        "<th>Ljung-Box p</th><th>Residuals</th></tr>"
    )
    rows = []
    # Deduplicate: show aggregate per CV (fits has one per CV-MV pair,
    # but R2/RMSE are per-CV aggregates)
    seen_cv = {}
    for f in fits:
        cv_idx = f.cv_index
        if cv_idx in seen_cv:
            continue
        seen_cv[cv_idx] = True

        cv_name = cv_cols[cv_idx] if cv_cols and cv_idx < len(cv_cols) else f"CV{cv_idx}"
        r2 = f.r_squared
        bg_r2 = _r2_color(r2)
        lb_p = f.ljung_box_pvalue
        white_label = "White" if f.is_white else "Correlated"
        white_color = _GREEN if f.is_white else _ORANGE

        rows.append(
            f"<tr>"
            f"<td>{_esc(cv_name)}</td>"
            f"<td>(all)</td>"
            f'<td class="fit-cell" style="background:{bg_r2};">{_fmt(r2)}</td>'
            f'<td class="fit-cell">{_fmt(f.rmse)}</td>'
            f'<td class="fit-cell">{_fmt(f.nrmse)}</td>'
            f'<td class="fit-cell">{_fmt(lb_p, ".3f")}</td>'
            f'<td style="color:{white_color}; font-weight:600;">{white_label}</td>'
            f"</tr>"
        )

    return f"""<h2>6. Channel Fit Metrics</h2>
<table>
{header}
{"".join(rows)}
</table>
<p style="font-size:8pt; color:#777;">
  R&sup2; color coding:
  <span style="background:#D5F5E3; padding:1px 6px; border:1px solid {_BORDER};">&ge; 0.9</span>
  <span style="background:#FEF9E7; padding:1px 6px; border:1px solid {_BORDER};">&ge; 0.7</span>
  <span style="background:#FADBD8; padding:1px 6px; border:1px solid {_BORDER};">&lt; 0.7</span>
</p>"""


def _render_subspace_fits(result, cv_cols) -> str:
    """Render SubspaceResult fit arrays as a table."""
    fit_r2 = _safe(result, "fit_r2")
    fit_rmse = _safe(result, "fit_rmse")
    fit_nrmse = _safe(result, "fit_nrmse")
    ny = len(fit_r2) if fit_r2 is not None else 0

    header = "<tr><th>CV</th><th>R&sup2;</th><th>RMSE</th><th>NRMSE</th></tr>"
    rows = []
    for i in range(ny):
        cv_name = cv_cols[i] if cv_cols and i < len(cv_cols) else f"CV{i}"
        r2 = float(fit_r2[i]) if fit_r2 is not None else None
        rmse = float(fit_rmse[i]) if fit_rmse is not None else None
        nrmse = float(fit_nrmse[i]) if fit_nrmse is not None else None
        bg_r2 = _r2_color(r2) if r2 is not None else _WHITE

        rows.append(
            f"<tr>"
            f"<td>{_esc(cv_name)}</td>"
            f'<td class="fit-cell" style="background:{bg_r2};">{_fmt(r2)}</td>'
            f'<td class="fit-cell">{_fmt(rmse)}</td>'
            f'<td class="fit-cell">{_fmt(nrmse)}</td>'
            f"</tr>"
        )

    return f"""<h2>6. Channel Fit Metrics</h2>
<table>
{header}
{"".join(rows)}
</table>"""


def _section_scorecard(scorecard) -> str:
    """Section 7: Model quality scorecard."""
    if scorecard is None:
        return f"""<h2>7. Model Quality Scorecard</h2>
<p class="note">Not available.</p>"""

    overall = _safe(scorecard, "overall_grade", "N/A")
    categories = _safe(scorecard, "categories", [])

    cat_blocks = []
    for cat in (categories or []):
        name = _safe(cat, "name", "Unknown")
        grade = _safe(cat, "grade", "N/A")
        findings = _safe(cat, "findings", [])
        recommendations = _safe(cat, "recommendations", [])

        findings_html = ""
        if findings:
            items = "\n".join(f'<li class="finding">{_esc(f)}</li>' for f in findings)
            findings_html = f"<ul>{items}</ul>"

        rec_html = ""
        if recommendations:
            items = "\n".join(
                f'<li class="recommendation">{_esc(r)}</li>' for r in recommendations
            )
            rec_html = f"<ul>{items}</ul>"

        cat_blocks.append(
            f"<h3>{_esc(name)} &nbsp; {_grade_badge(grade)}</h3>"
            f"{findings_html}"
            f"{rec_html}"
        )

    return f"""<h2>7. Model Quality Scorecard &nbsp; {_grade_badge(overall)}</h2>
{"".join(cat_blocks)}"""


def _section_smart_config(smart_report) -> str:
    """Section 8: Smart configuration report."""
    if smart_report is None:
        return f"""<h2>8. Smart Configuration</h2>
<p class="note">Not available.</p>"""

    # Recommended settings summary
    settings = [
        ("n_coeff", _safe(smart_report, "n_coeff")),
        ("dt", f"{_safe(smart_report, 'dt', 0):.1f} s"),
        ("method", _safe(smart_report, "method", "")),
        ("smooth", _safe(smart_report, "smooth", "")),
        ("detrend", _safe(smart_report, "detrend")),
        ("prewhiten", _safe(smart_report, "prewhiten")),
        ("clip_sigma", _safe(smart_report, "clip_sigma")),
        ("holdout_fraction", _safe(smart_report, "holdout_fraction")),
    ]
    settings_rows = "\n".join(
        f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>" for k, v in settings
    )

    # Decision rationale
    recs = _safe(smart_report, "recommendations", [])
    rationale_rows = []
    for rec in (recs or []):
        param = _safe(rec, "parameter", "")
        value = _safe(rec, "value", "")
        reason = _safe(rec, "reason", "")
        confidence = _safe(rec, "confidence", "")
        conf_color = {
            "high": _GREEN,
            "medium": _ORANGE,
            "low": _RED,
        }.get(str(confidence).lower(), _TEXT)
        rationale_rows.append(
            f"<tr>"
            f"<td>{_esc(param)}</td>"
            f"<td>{_esc(value)}</td>"
            f'<td style="color:{conf_color}; font-weight:600;">{_esc(confidence)}</td>'
            f"<td>{_esc(reason)}</td>"
            f"</tr>"
        )

    # Warnings
    warnings = _safe(smart_report, "warnings", [])
    warnings_html = ""
    if warnings:
        items = "\n".join(
            f'<li style="color:{_RED};">{_esc(w)}</li>' for w in warnings
        )
        warnings_html = f"<h3>Warnings</h3><ul>{items}</ul>"

    # CV types
    cv_types = _safe(smart_report, "cv_types", {})
    cv_html = ""
    if cv_types:
        cv_rows = "\n".join(
            f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>"
            for k, v in cv_types.items()
        )
        cv_html = f"""<h3>CV Types</h3>
<table class="meta-table">
<tr><th>CV</th><th>Type</th></tr>
{cv_rows}
</table>"""

    # Excitation grades
    exc_grades = _safe(smart_report, "excitation_grades", {})
    exc_html = ""
    if exc_grades:
        exc_rows = "\n".join(
            f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>"
            for k, v in exc_grades.items()
        )
        exc_html = f"""<h3>MV Excitation</h3>
<table class="meta-table">
<tr><th>MV</th><th>Grade</th></tr>
{exc_rows}
</table>"""

    return f"""<h2>8. Smart Configuration</h2>
<h3>Recommended Settings</h3>
<table class="meta-table">
{settings_rows}
</table>

{cv_html}
{exc_html}
{warnings_html}

<h3>Decision Rationale</h3>
<table>
<tr><th>Parameter</th><th>Value</th><th>Confidence</th><th>Reason</th></tr>
{"".join(rationale_rows)}
</table>"""
