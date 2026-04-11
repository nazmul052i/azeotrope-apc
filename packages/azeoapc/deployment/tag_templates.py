"""Tag templates + built-in DMC3 parameter catalog.

A "template" is a dict that maps each application parameter (Measurement,
SetPoint, ValidityLowLimit, ...) to a NodeId pattern using the variable's
prefix/suffix/interface_point. Generate Tags expands the patterns into
concrete OPC UA NodeIds.

Patterns use Python str.format placeholders:
  {prefix}            -- measurement_prefix
  {suffix}            -- measurement_suffix
  {interface_point}   -- interface_point
  {tag}               -- the application variable tag (CV/MV name)
  {param}             -- the parameter name itself

Example: pattern "ns=2;s={tag}.{param}" with tag="TI-201.PV", param="Measurement"
expands to "ns=2;s=TI-201.PV.Measurement".
"""
from __future__ import annotations

from typing import Dict, List

from .tag_model import IOTag, ParamRole, VarType


# ---------------------------------------------------------------------------
# Built-in DMC3 parameter catalog -- subset of what Customize Connections
# exposes. Each entry: (parameter_name, role, default_datatype, applies_to_var_types)
# ---------------------------------------------------------------------------
BUILTIN_PARAMETERS: List[Dict] = [
    # ─────────── Per-CV (Input) parameters ───────────
    {"name": "Measurement",        "role": ParamRole.READ,       "dtype": "Real",    "applies": [VarType.INPUT]},
    {"name": "MeasurementStatus",  "role": ParamRole.READ,       "dtype": "Integer", "applies": [VarType.INPUT]},
    {"name": "ValidityLowLimit",   "role": ParamRole.DIAGNOSTIC, "dtype": "Real",    "applies": [VarType.INPUT, VarType.OUTPUT]},
    {"name": "ValidityHighLimit",  "role": ParamRole.DIAGNOSTIC, "dtype": "Real",    "applies": [VarType.INPUT, VarType.OUTPUT]},
    {"name": "EngLowLimit",        "role": ParamRole.DIAGNOSTIC, "dtype": "Real",    "applies": [VarType.INPUT, VarType.OUTPUT]},
    {"name": "EngHighLimit",       "role": ParamRole.DIAGNOSTIC, "dtype": "Real",    "applies": [VarType.INPUT, VarType.OUTPUT]},
    {"name": "OprLowLimit",        "role": ParamRole.READ_WRITE, "dtype": "Real",    "applies": [VarType.INPUT, VarType.OUTPUT]},
    {"name": "OprHighLimit",       "role": ParamRole.READ_WRITE, "dtype": "Real",    "applies": [VarType.INPUT, VarType.OUTPUT]},
    # ─────────── Per-MV (Output) parameters ───────────
    {"name": "SetPoint",           "role": ParamRole.WRITE,      "dtype": "Real",    "applies": [VarType.OUTPUT]},
    {"name": "SetPointFeedback",   "role": ParamRole.READ,       "dtype": "Real",    "applies": [VarType.OUTPUT]},
    {"name": "ManualMode",         "role": ParamRole.READ,       "dtype": "Boolean", "applies": [VarType.OUTPUT]},
    # ─────────── Per-DV (Disturbance) parameters ───────────
    {"name": "Measurement",        "role": ParamRole.READ,       "dtype": "Real",    "applies": [VarType.DISTURBANCE]},
    {"name": "MeasurementStatus",  "role": ParamRole.READ,       "dtype": "Integer", "applies": [VarType.DISTURBANCE]},
    # ─────────── General controller telemetry ───────────
    {"name": "ControllerStatus",   "role": ParamRole.WRITE,      "dtype": "Integer", "applies": [VarType.GENERAL]},
    {"name": "ApplicationCycle",   "role": ParamRole.WRITE,      "dtype": "Integer", "applies": [VarType.GENERAL]},
    {"name": "AlgorithmRunCount",  "role": ParamRole.WRITE,      "dtype": "Integer", "applies": [VarType.GENERAL]},
    {"name": "AlgorithmFailureCount","role": ParamRole.WRITE,    "dtype": "Integer", "applies": [VarType.GENERAL]},
    {"name": "AbortIndicator",     "role": ParamRole.WRITE,      "dtype": "Boolean", "applies": [VarType.GENERAL]},
    {"name": "MasterOnOffRequest", "role": ParamRole.READ,       "dtype": "Boolean", "applies": [VarType.GENERAL]},
    {"name": "MasterOnOffStatus",  "role": ParamRole.WRITE,      "dtype": "Boolean", "applies": [VarType.GENERAL]},
    {"name": "WatchdogCounter",    "role": ParamRole.WRITE,      "dtype": "Integer", "applies": [VarType.GENERAL]},
    {"name": "AvgPredictionError", "role": ParamRole.WRITE,      "dtype": "Real",    "applies": [VarType.GENERAL]},
    {"name": "ActualMoves",        "role": ParamRole.WRITE,      "dtype": "Real",    "applies": [VarType.GENERAL]},
]


def default_parameters_for(var_type: VarType) -> List[Dict]:
    """Return the subset of BUILTIN_PARAMETERS that apply to a variable type."""
    return [p for p in BUILTIN_PARAMETERS if var_type in p["applies"]]


# ---------------------------------------------------------------------------
# Templates -- maps parameter -> NodeId pattern
# ---------------------------------------------------------------------------
TAG_TEMPLATES: Dict[str, Dict[str, str]] = {
    # Default: namespace 2, string identifier "Plant.{tag}.{param}"
    "default": {
        "Measurement":        "ns=2;s=Plant.{tag}.PV",
        "MeasurementStatus":  "ns=2;s=Plant.{tag}.Status",
        "SetPoint":           "ns=2;s=Plant.{tag}.SP",
        "SetPointFeedback":   "ns=2;s=Plant.{tag}.SP_FB",
        "ManualMode":         "ns=2;s=Plant.{tag}.Manual",
        "ValidityLowLimit":   "ns=2;s=Plant.{tag}.ValidLo",
        "ValidityHighLimit":  "ns=2;s=Plant.{tag}.ValidHi",
        "EngLowLimit":        "ns=2;s=Plant.{tag}.EngLo",
        "EngHighLimit":       "ns=2;s=Plant.{tag}.EngHi",
        "OprLowLimit":        "ns=2;s=Plant.{tag}.OprLo",
        "OprHighLimit":       "ns=2;s=Plant.{tag}.OprHi",
        # General controller telemetry
        "ControllerStatus":     "ns=2;s=Controller.Status",
        "ApplicationCycle":     "ns=2;s=Controller.Cycle",
        "AlgorithmRunCount":    "ns=2;s=Controller.RunCount",
        "AlgorithmFailureCount":"ns=2;s=Controller.FailCount",
        "AbortIndicator":       "ns=2;s=Controller.Abort",
        "MasterOnOffRequest":   "ns=2;s=Controller.OnOffRequest",
        "MasterOnOffStatus":    "ns=2;s=Controller.OnOffStatus",
        "WatchdogCounter":      "ns=2;s=Controller.Watchdog",
        "AvgPredictionError":   "ns=2;s=Controller.AvgPredError",
        "ActualMoves":          "ns=2;s=Controller.ActualMoves",
    },
    # Honeywell-style: prefix and suffix used as separate dotted segments
    "honeywell": {
        "Measurement":        "ns=2;s={prefix}.{interface_point}.PV{suffix}",
        "SetPoint":           "ns=2;s={prefix}.{interface_point}.SP{suffix}",
        "SetPointFeedback":   "ns=2;s={prefix}.{interface_point}.SP{suffix}",
        "ManualMode":         "ns=2;s={prefix}.{interface_point}.MODE{suffix}",
        "OprLowLimit":        "ns=2;s={prefix}.{interface_point}.LOLM{suffix}",
        "OprHighLimit":       "ns=2;s={prefix}.{interface_point}.HILM{suffix}",
    },
}


def expand_template(
    template_name: str, parameter: str, *, tag: str,
    prefix: str = "", suffix: str = "", interface_point: str = "",
) -> str:
    """Expand a template pattern for a single parameter into a NodeId string."""
    tmpl = TAG_TEMPLATES.get(template_name) or TAG_TEMPLATES["default"]
    pattern = tmpl.get(parameter)
    if not pattern:
        # Fall back to default-template's pattern, or a generic last-resort
        pattern = TAG_TEMPLATES["default"].get(
            parameter, "ns=2;s=Plant.{tag}.{param}")
    return pattern.format(
        tag=tag, prefix=prefix, suffix=suffix,
        interface_point=interface_point or tag, param=parameter,
    )


def generate_io_tags(
    variable_tag: str, var_type: VarType, *, template: str = "default",
    prefix: str = "", suffix: str = "", interface_point: str = "",
    io_source: str = "OPCUA",
) -> List[IOTag]:
    """Build the full list of IOTag rows for one variable using a template."""
    rows: List[IOTag] = []
    for p in default_parameters_for(var_type):
        node = expand_template(
            template, p["name"], tag=variable_tag,
            prefix=prefix, suffix=suffix, interface_point=interface_point,
        )
        rows.append(IOTag(
            parameter=p["name"],
            role=p["role"],
            io_source=io_source,
            node_id=node,
            datatype=p["dtype"],
            auto_generated=True,
        ))
    return rows
