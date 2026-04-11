"""DeploymentConfig <-> dict serialization for YAML I/O.

Lives next to the data model so the controller config loader can pull it
in without circular imports. ``server_password`` is intentionally never
written to disk; the architect prompts for it at connect time instead.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .tag_model import (
    DeploymentConfig, GeneralSettings, IOTag, ParamRole,
    ValidationLimits, VarType, VariableDeployment,
)


# ---------------------------------------------------------------------------
# DeploymentConfig -> dict
# ---------------------------------------------------------------------------
def deployment_to_dict(dep: DeploymentConfig) -> Dict[str, Any]:
    """Render a DeploymentConfig as a YAML-safe dict (no numpy, no enums)."""
    return {
        "server_url": dep.server_url,
        "server_username": dep.server_username,
        "auto_reconnect": dep.auto_reconnect,
        "default_template": dep.default_template,
        "default_io_source": dep.default_io_source,
        "general_settings": _gs_to_dict(dep.general_settings),
        "variables": [_var_to_dict(v) for v in dep.variables],
    }


def _gs_to_dict(gs: GeneralSettings) -> Dict[str, Any]:
    return {
        "watchdog_sec": float(gs.watchdog_sec),
        "cycle_offset_sec": float(gs.cycle_offset_sec),
        "setpoint_extended_validation": bool(gs.setpoint_extended_validation),
        "write_failure_limit": int(gs.write_failure_limit),
        "read_failure_limit": int(gs.read_failure_limit),
        "pad_io_tag_length": int(gs.pad_io_tag_length),
    }


def _var_to_dict(v: VariableDeployment) -> Dict[str, Any]:
    return {
        "variable_tag": v.variable_tag,
        "var_type": v.var_type.value,
        "measurement_prefix": v.measurement_prefix,
        "measurement_suffix": v.measurement_suffix,
        "interface_point": v.interface_point,
        "template_name": v.template_name,
        "generate_tags_enabled": bool(v.generate_tags_enabled),
        "validation": _val_to_dict(v.validation),
        "io_tags": [_iotag_to_dict(t) for t in v.io_tags],
    }


def _val_to_dict(v: ValidationLimits) -> Dict[str, Any]:
    return {
        "validity_lo": float(v.validity_lo),
        "validity_hi": float(v.validity_hi),
        "engineer_lo": float(v.engineer_lo),
        "engineer_hi": float(v.engineer_hi),
        "operator_lo": float(v.operator_lo),
        "operator_hi": float(v.operator_hi),
        "timeout_sec": float(v.timeout_sec),
    }


def _iotag_to_dict(t: IOTag) -> Dict[str, Any]:
    return {
        "parameter": t.parameter,
        "role": t.role.value,
        "io_source": t.io_source,
        "node_id": t.node_id,
        "datatype": t.datatype,
        "string_length": int(t.string_length),
        "auto_generated": bool(t.auto_generated),
    }


# ---------------------------------------------------------------------------
# dict -> DeploymentConfig
# ---------------------------------------------------------------------------
def deployment_from_dict(d: Dict[str, Any]) -> DeploymentConfig:
    """Reconstruct a DeploymentConfig from a previously-saved dict."""
    dep = DeploymentConfig()
    dep.server_url = d.get("server_url", dep.server_url)
    dep.server_username = d.get("server_username", "")
    dep.auto_reconnect = d.get("auto_reconnect", True)
    dep.default_template = d.get("default_template", "default")
    dep.default_io_source = d.get("default_io_source", "OPCUA")
    dep.general_settings = _gs_from_dict(d.get("general_settings", {}))
    dep.variables = [_var_from_dict(v) for v in d.get("variables", [])]
    return dep


def _gs_from_dict(d: Dict[str, Any]) -> GeneralSettings:
    return GeneralSettings(
        watchdog_sec=float(d.get("watchdog_sec", 30.0)),
        cycle_offset_sec=float(d.get("cycle_offset_sec", 0.0)),
        setpoint_extended_validation=bool(d.get("setpoint_extended_validation", True)),
        write_failure_limit=int(d.get("write_failure_limit", 3)),
        read_failure_limit=int(d.get("read_failure_limit", 3)),
        pad_io_tag_length=int(d.get("pad_io_tag_length", 0)),
    )


def _var_from_dict(d: Dict[str, Any]) -> VariableDeployment:
    return VariableDeployment(
        variable_tag=d["variable_tag"],
        var_type=VarType(d.get("var_type", "Input")),
        measurement_prefix=d.get("measurement_prefix", ""),
        measurement_suffix=d.get("measurement_suffix", ""),
        interface_point=d.get("interface_point", ""),
        template_name=d.get("template_name", "default"),
        generate_tags_enabled=bool(d.get("generate_tags_enabled", True)),
        validation=_val_from_dict(d.get("validation", {})),
        io_tags=[_iotag_from_dict(t) for t in d.get("io_tags", [])],
    )


def _val_from_dict(d: Dict[str, Any]) -> ValidationLimits:
    return ValidationLimits(
        validity_lo=float(d.get("validity_lo", -1e20)),
        validity_hi=float(d.get("validity_hi", 1e20)),
        engineer_lo=float(d.get("engineer_lo", -1e20)),
        engineer_hi=float(d.get("engineer_hi", 1e20)),
        operator_lo=float(d.get("operator_lo", -1e20)),
        operator_hi=float(d.get("operator_hi", 1e20)),
        timeout_sec=float(d.get("timeout_sec", 30.0)),
    )


def _iotag_from_dict(d: Dict[str, Any]) -> IOTag:
    return IOTag(
        parameter=d.get("parameter", ""),
        role=ParamRole(d.get("role", "Read")),
        io_source=d.get("io_source", "OPCUA"),
        node_id=d.get("node_id", ""),
        datatype=d.get("datatype", "Real"),
        string_length=int(d.get("string_length", 0)),
        auto_generated=bool(d.get("auto_generated", False)),
    )
