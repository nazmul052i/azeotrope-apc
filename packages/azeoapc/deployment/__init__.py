"""Deployment subsystem: OPC UA bridge between SimEngine and the plant.

Mirrors the Aspen DMC3 Deployment stage:
  - Online Settings: watchdog, cycle offset, read/write failure limits, etc.
  - Input/Output Validation Limits: per-variable validity envelope.
  - IO Tags: per-variable parameter -> OPC UA NodeId map.
  - Tag Generator: template-driven bulk creation of OPC NodeIds from
    measurement prefix/suffix + interface point.
  - DeploymentRuntime: QThread that reads PVs, runs the engine cycle,
    and writes MV setpoints back to the plant.

Also ships an embedded OPC UA test server that publishes the simulator's
own plant model as nodes -- lets the user point the deployment loop at
themselves and exercise the full read/cycle/write loop without any
external infrastructure.
"""
from .tag_model import (
    IOTag, VariableDeployment, GeneralSettings, ValidationLimits,
    DeploymentConfig, VarType, ParamRole,
)
from .tag_templates import (
    BUILTIN_PARAMETERS, TAG_TEMPLATES, expand_template, default_parameters_for,
)
from .yaml_io import deployment_to_dict, deployment_from_dict

__all__ = [
    "IOTag", "VariableDeployment", "GeneralSettings", "ValidationLimits",
    "DeploymentConfig", "VarType", "ParamRole",
    "BUILTIN_PARAMETERS", "TAG_TEMPLATES", "expand_template",
    "default_parameters_for",
    "deployment_to_dict", "deployment_from_dict",
]
