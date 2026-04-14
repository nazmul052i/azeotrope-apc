"""Pre-configured templates for common industrial process types.

Provides starting-point configurations so engineers don't build
identification projects from scratch.  Each template carries:

- Typical MV and CV names with units
- Suggested ``n_coeff`` and ``dt`` based on known dynamics
- Expected time-constant and dead-time ranges
- Typical move sizes for step testing
- Known CV types (ramp / pseudoramp for integrating outputs)
- Suggested identification method

Usage::

    from azeoapc.identification.process_templates import (
        get_template, list_templates, apply_template,
    )

    tmpl = get_template("HEATER")
    apply_template(project, tmpl)
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .fir_ident import IdentConfig, IdentMethod, SmoothMethod
from .ident_project import IdentProject, TagAssignment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------
@dataclass
class ProcessTemplate:
    """Describes a common industrial process type for identification."""

    name: str
    description: str
    mv_defaults: List[Dict[str, Any]]
    cv_defaults: List[Dict[str, Any]]
    suggested_n_coeff: int
    suggested_dt: float
    suggested_method: str
    notes: str

    # Additional metadata for documentation / UI hints
    typical_tau_range: tuple = (0.0, 0.0)       # (min, max) minutes
    typical_deadtime_range: tuple = (0.0, 0.0)  # (min, max) minutes


# ---------------------------------------------------------------------------
#  Template definitions
# ---------------------------------------------------------------------------

_HEATER = ProcessTemplate(
    name="HEATER",
    description="Fired heater / hot oil heater",
    mv_defaults=[
        {"name": "Fuel Gas Flow",        "typical_move": 2.0,  "unit": "%"},
        {"name": "Air Flow",             "typical_move": 3.0,  "unit": "%"},
        {"name": "Hot Oil Circulation",  "typical_move": 5.0,  "unit": "%"},
    ],
    cv_defaults=[
        {"name": "Outlet Temperature",      "unit": "degC", "cv_type": "normal"},
        {"name": "Bridge Wall Temperature", "unit": "degC", "cv_type": "normal"},
        {"name": "Stack Temperature",       "unit": "degC", "cv_type": "normal"},
        {"name": "O2 Analyzer",             "unit": "%",    "cv_type": "normal"},
        {"name": "Coil Inlet Temperature",  "unit": "degC", "cv_type": "normal"},
    ],
    suggested_n_coeff=90,
    suggested_dt=60.0,
    suggested_method="dls",
    typical_tau_range=(5.0, 30.0),
    typical_deadtime_range=(1.0, 5.0),
    notes=(
        "Fired heaters typically show self-regulating (non-integrating) "
        "dynamics on all CVs.  Fuel-to-temperature responses are first-order "
        "with moderate dead time.  Air flow mainly affects O2 and stack "
        "temperature.  Use 60 s sampling; 90 coefficients covers roughly "
        "1.5 hours which captures most settling behaviour.  DLS works well "
        "for open-loop step tests."
    ),
)

_DISTILLATION_COLUMN = ProcessTemplate(
    name="DISTILLATION_COLUMN",
    description="Distillation column (binary or multi-component)",
    mv_defaults=[
        {"name": "Reflux Flow",       "typical_move": 3.0, "unit": "%"},
        {"name": "Reboiler Duty",     "typical_move": 3.0, "unit": "%"},
        {"name": "Feed Rate",         "typical_move": 2.0, "unit": "%"},
        {"name": "Overhead Pressure", "typical_move": 1.0, "unit": "kPa"},
    ],
    cv_defaults=[
        {"name": "Top Temperature",     "unit": "degC", "cv_type": "normal"},
        {"name": "Bottom Temperature",  "unit": "degC", "cv_type": "normal"},
        {"name": "Top Composition",     "unit": "mol%", "cv_type": "normal"},
        {"name": "Bottom Composition",  "unit": "mol%", "cv_type": "normal"},
        {"name": "Column dP",           "unit": "kPa",  "cv_type": "normal"},
        {"name": "Accumulator Level",   "unit": "%",    "cv_type": "ramp"},
        {"name": "Sump Level",          "unit": "%",    "cv_type": "ramp"},
    ],
    suggested_n_coeff=150,
    suggested_dt=60.0,
    suggested_method="dls",
    typical_tau_range=(10.0, 60.0),
    typical_deadtime_range=(2.0, 15.0),
    notes=(
        "Columns are typically the slowest units in a refinery / chemical "
        "plant.  Composition responses can take 1-2 hours to settle.  "
        "Accumulator and sump levels are integrating (ramp-type) CVs and "
        "must be identified with the ramp model.  150 coefficients at 60 s "
        "covers 2.5 hours.  If the column has long holdup trays, increase "
        "n_coeff to 180.  DLS is preferred for open-loop tests; consider "
        "Ridge if feed rate is correlated with other MVs."
    ),
)

_REACTOR = ProcessTemplate(
    name="REACTOR",
    description="Continuous stirred-tank reactor (CSTR)",
    mv_defaults=[
        {"name": "Coolant Flow",  "typical_move": 3.0, "unit": "%"},
        {"name": "Feed Flow",     "typical_move": 2.0, "unit": "%"},
        {"name": "Catalyst Rate", "typical_move": 1.0, "unit": "%"},
    ],
    cv_defaults=[
        {"name": "Reactor Temperature", "unit": "degC", "cv_type": "normal"},
        {"name": "Conversion",          "unit": "%",    "cv_type": "normal"},
        {"name": "Product Quality",     "unit": "ppm",  "cv_type": "normal"},
        {"name": "Reactor Pressure",    "unit": "kPa",  "cv_type": "normal"},
        {"name": "Reactor Level",       "unit": "%",    "cv_type": "ramp"},
    ],
    suggested_n_coeff=90,
    suggested_dt=60.0,
    suggested_method="dls",
    typical_tau_range=(5.0, 20.0),
    typical_deadtime_range=(1.0, 10.0),
    notes=(
        "CSTR dynamics depend heavily on reaction kinetics and heat removal.  "
        "Temperature responses to coolant changes are typically fast "
        "(tau ~ 5-10 min) while quality / conversion responses can be slower "
        "(tau ~ 10-20 min) due to mixing.  Reactor level is integrating.  "
        "Use 60 s sampling for most reactors; reduce to 30 s for fast "
        "exothermic reactions.  90 coefficients covers 1.5 hours at 60 s."
    ),
)

_COMPRESSOR = ProcessTemplate(
    name="COMPRESSOR",
    description="Centrifugal or axial compressor",
    mv_defaults=[
        {"name": "Suction Valve",  "typical_move": 2.0, "unit": "%"},
        {"name": "Speed",          "typical_move": 1.0, "unit": "rpm"},
        {"name": "Recycle Valve",  "typical_move": 3.0, "unit": "%"},
    ],
    cv_defaults=[
        {"name": "Discharge Pressure", "unit": "kPa", "cv_type": "normal"},
        {"name": "Suction Pressure",   "unit": "kPa", "cv_type": "normal"},
        {"name": "Flow",               "unit": "%",   "cv_type": "normal"},
        {"name": "Surge Margin",       "unit": "%",   "cv_type": "normal"},
        {"name": "Power",              "unit": "kW",  "cv_type": "normal"},
    ],
    suggested_n_coeff=45,
    suggested_dt=15.0,
    suggested_method="dls",
    typical_tau_range=(0.5, 5.0),
    typical_deadtime_range=(0.0, 1.0),
    notes=(
        "Compressors are fast compared to heat-transfer or mass-transfer "
        "units.  Pressure and flow responses settle in seconds to a few "
        "minutes.  Use a short sample period (10-30 s) and a shorter model "
        "horizon (45 coefficients at 15 s = ~11 minutes).  Surge margin "
        "is a calculated variable that tracks discharge pressure and flow.  "
        "All CVs are self-regulating (no integrators).  Take care with "
        "move sizes near the surge line."
    ),
)

_BOILER = ProcessTemplate(
    name="BOILER",
    description="Industrial steam boiler / utility boiler",
    mv_defaults=[
        {"name": "Fuel Flow",           "typical_move": 2.0, "unit": "%"},
        {"name": "Feedwater Flow",      "typical_move": 3.0, "unit": "%"},
        {"name": "Air Flow",            "typical_move": 3.0, "unit": "%"},
        {"name": "Attemperator Spray",  "typical_move": 5.0, "unit": "%"},
    ],
    cv_defaults=[
        {"name": "Steam Pressure",    "unit": "kPa",  "cv_type": "normal"},
        {"name": "Steam Temperature", "unit": "degC", "cv_type": "normal"},
        {"name": "Drum Level",        "unit": "%",    "cv_type": "ramp"},
        {"name": "O2",                "unit": "%",    "cv_type": "normal"},
        {"name": "NOx",               "unit": "ppm",  "cv_type": "normal"},
    ],
    suggested_n_coeff=90,
    suggested_dt=60.0,
    suggested_method="dls",
    typical_tau_range=(5.0, 30.0),
    typical_deadtime_range=(1.0, 5.0),
    notes=(
        "Boilers combine combustion dynamics (fast) with steam-side dynamics "
        "(moderate) and drum level (integrating).  Drum level exhibits "
        "inverse response (shrink-swell) which makes it challenging -- the "
        "ramp model handles the integrating nature but the initial inverse "
        "dip requires enough coefficients to capture the transient.  "
        "90 coefficients at 60 s covers 1.5 hours.  O2 and NOx respond "
        "primarily to fuel-air ratio changes."
    ),
)


# ---------------------------------------------------------------------------
#  Registry
# ---------------------------------------------------------------------------
_TEMPLATES: Dict[str, ProcessTemplate] = {
    "HEATER": _HEATER,
    "DISTILLATION_COLUMN": _DISTILLATION_COLUMN,
    "REACTOR": _REACTOR,
    "COMPRESSOR": _COMPRESSOR,
    "BOILER": _BOILER,
}


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------
def list_templates() -> List[str]:
    """Return the names of all available process templates."""
    return sorted(_TEMPLATES.keys())


def get_template(name: str) -> ProcessTemplate:
    """Look up a process template by name (case-insensitive).

    Parameters
    ----------
    name : str
        Template name, e.g. ``"HEATER"``, ``"distillation_column"``.

    Returns
    -------
    ProcessTemplate
        A *copy* of the template so callers can modify it freely.

    Raises
    ------
    KeyError
        If *name* does not match any registered template.
    """
    key = name.strip().upper()
    if key not in _TEMPLATES:
        available = ", ".join(sorted(_TEMPLATES.keys()))
        raise KeyError(
            f"Unknown process template '{name}'.  "
            f"Available templates: {available}"
        )
    return copy.deepcopy(_TEMPLATES[key])


def apply_template(project: IdentProject, template: ProcessTemplate) -> None:
    """Apply a process template to an existing ident project in-place.

    Overwrites the project's identification config (``n_coeff``, ``dt``,
    ``method``) and populates tag assignments from the template's MV / CV
    defaults.  Existing tag assignments are cleared.

    Parameters
    ----------
    project : IdentProject
        The project to modify.
    template : ProcessTemplate
        The template to apply (obtained via :func:`get_template`).
    """
    # -- Identification settings -------------------------------------------
    project.ident.n_coeff = template.suggested_n_coeff
    project.ident.dt = template.suggested_dt

    method_str = template.suggested_method.lower()
    try:
        project.ident.method = IdentMethod(method_str)
    except ValueError:
        logger.warning(
            "Template method '%s' not in IdentMethod enum; leaving as-is.",
            method_str,
        )

    # -- Conditioning: match sample period to template dt ------------------
    project.conditioning.resample_period_sec = template.suggested_dt

    # -- Tag assignments from template defaults ----------------------------
    assignments: List[TagAssignment] = []

    for mv in template.mv_defaults:
        assignments.append(TagAssignment(
            column=mv["name"],
            role="MV",
            controller_tag="",
        ))

    for cv in template.cv_defaults:
        assignments.append(TagAssignment(
            column=cv["name"],
            role="CV",
            controller_tag="",
        ))

    project.tag_assignments = assignments

    # -- Metadata hint -----------------------------------------------------
    if not project.metadata.name:
        project.metadata.name = f"{template.name} identification"

    if not project.metadata.notes:
        project.metadata.notes = template.notes

    logger.info(
        "Applied template '%s': %d MVs, %d CVs, n_coeff=%d, dt=%.0f s",
        template.name,
        len(template.mv_defaults),
        len(template.cv_defaults),
        template.suggested_n_coeff,
        template.suggested_dt,
    )
