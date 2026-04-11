"""Deployment data model -- mirrors DMC3 IO Tags + Online Settings.

Reference: D:/office_documents02162026/dev/AspenTechAPC/HtmlHelp_DMC3/Content/html/views/
  view_deployment_io_tags.htm
  view_deployment_online_settings.htm
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class VarType(str, Enum):
    """Application-level variable type (DMC3 'Type' column in Tag Generator)."""
    INPUT = "Input"        # CV measurement read from the plant
    OUTPUT = "Output"      # MV setpoint written to the plant
    DISTURBANCE = "Disturbance"
    GENERAL = "General"    # controller-wide telemetry (ControllerStatus, etc.)


class ParamRole(str, Enum):
    """How a parameter is used at runtime by the deployment loop."""
    READ = "Read"          # plant -> engine (CV measurement, DV value)
    WRITE = "Write"        # engine -> plant (MV setpoint, controller status)
    READ_WRITE = "ReadWrite"  # bidirectional (e.g. SetPoint with feedback)
    DIAGNOSTIC = "Diagnostic"  # informational only, not on the cycle path


@dataclass
class IOTag:
    """One row of the Variable Detail table -- a single OPC UA endpoint.

    Mirrors columns: Parameter, IO Source, IO Tag, IO Datatype, String
    Length, Test Value.
    """
    parameter: str = ""              # e.g. "Measurement", "SetPoint"
    role: ParamRole = ParamRole.READ
    io_source: str = "OPCUA"         # logical name of the OPC UA server binding
    node_id: str = ""                # OPC UA NodeId, e.g. "ns=2;s=Plant.TI-201.PV"
    datatype: str = "Real"           # Real | Integer | Boolean | String
    string_length: int = 0           # only when datatype == String
    last_test_value: str = ""        # populated by Test Connections
    last_test_ok: Optional[bool] = None
    last_test_error: str = ""

    # Builder bookkeeping (set by Generate Tags)
    auto_generated: bool = False


@dataclass
class ValidationLimits:
    """One row of the Input/Output Validation Limits table.

    DMC3 nests three envelopes:
      [validity_lo .. engineer_lo .. operator_lo .. operator_hi .. engineer_hi .. validity_hi]
    Validity rejects readings outright; engineer/operator are optimizer
    constraints. Timeout treats stale reads as failed.
    """
    validity_lo: float = -1e20
    validity_hi: float = 1e20
    engineer_lo: float = -1e20
    engineer_hi: float = 1e20
    operator_lo: float = -1e20
    operator_hi: float = 1e20
    timeout_sec: float = 30.0


@dataclass
class VariableDeployment:
    """A single row of the Tag Generator table + its expanded IO tags.

    Wraps the application variable (CV/MV/DV by tag) with all the
    deployment-time configuration: template inputs, generated IO tags,
    validation envelope, and per-cycle counters.
    """
    variable_tag: str                # the CV/MV/DV tag from SimConfig
    var_type: VarType = VarType.INPUT
    measurement_prefix: str = ""
    measurement_suffix: str = ""
    interface_point: str = ""
    template_name: str = "default"
    generate_tags_enabled: bool = True

    io_tags: List[IOTag] = field(default_factory=list)
    validation: ValidationLimits = field(default_factory=ValidationLimits)

    # Runtime counters (updated by DeploymentRuntime)
    read_failure_count: int = 0
    write_failure_count: int = 0
    last_good_value: Optional[float] = None
    last_status: str = "READY"       # READY | OK | BAD | TIMEOUT | OFFLINE


@dataclass
class GeneralSettings:
    """The Online Settings > General Settings table (single row)."""
    watchdog_sec: float = 30.0
    cycle_offset_sec: float = 0.0
    setpoint_extended_validation: bool = True
    write_failure_limit: int = 3
    read_failure_limit: int = 3
    pad_io_tag_length: int = 0       # 0 = no padding


@dataclass
class DeploymentConfig:
    """The full deployment configuration for one application.

    This is everything the Deployment tab edits and persists alongside
    the rest of the SimConfig.
    """
    server_url: str = "opc.tcp://localhost:4840/azeoapc/server/"
    server_username: str = ""
    server_password: str = ""
    auto_reconnect: bool = True

    general_settings: GeneralSettings = field(default_factory=GeneralSettings)
    variables: List[VariableDeployment] = field(default_factory=list)

    # Default template + IO source (Tag Generator ribbon)
    default_template: str = "default"
    default_io_source: str = "OPCUA"

    def find(self, variable_tag: str) -> Optional[VariableDeployment]:
        for v in self.variables:
            if v.variable_tag == variable_tag:
                return v
        return None
